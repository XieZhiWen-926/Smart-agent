"""
端到端评测：问答准确率 + 工具调用成功率（在 backend 容器内运行）
================================================================
【数据来源】
- 问答准确率：走 HTTP SSE 拿最终答案 → 用大模型做裁判（LLM-as-judge）打分
- 工具调用成功率：解析 /app/logs 里的 [ToolCall] 日志（中间件已在埋点）
  · [ToolCall] -> name args=...      = 发起一次调用
  · [ToolCall] <- name result=...    = 执行返回
  · [ToolCall] !! name 执行异常       = 抛出异常（中间件已兜底为 error ToolMessage）

【隔离方式】每条样本提问前记录日志行号，只解析该区间内的新增行，
            因此不会被其它并发流量污染（评测时请保持串行）。

【口径说明】
- 调用成功率  = 未抛异常的调用数 / 总调用数        ← 简历上常说的"工具调用成功率"
- 结果有效率  = 未抛异常 且 结果不含错误关键词 / 总调用数   ← 更贴近"用户真的拿到了数据"
- 选择准确率  = 实际调用的工具集合与期望完全一致的样本占比   ← 衡量"选没选对工具"
这三个是不同的东西，不要混为一谈。
"""
import asyncio
import codecs
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, "/app")

from app.model.factory import get_chat_model  # noqa: E402
from app.utils.logger import logger  # noqa: E402

BASE = "http://localhost:8000"
LOG_DIR = Path("/app/logs")
GOLDEN_PATH = Path("/tmp/eval/golden_set.json")

# 工具调用日志的正则（与 app/agent/tools/middleware.py 的日志文案严格对应）
RE_START = re.compile(r"\[ToolCall\] -> (\S+) args=")
RE_OK = re.compile(r"\[ToolCall\] <- (\S+) result=")
RE_FAIL = re.compile(r"\[ToolCall\] !! (\S+) 执行异常")

# 工具"没拿到可用数据"的判定标记。
#
# 【为什么不用「失败/错误/异常」这类泛化中文词做子串匹配？】
# 实测会大面积误伤：RAG 返回的维修知识里天然含"异常"（异响属异常现象），
# 天气工具返回里含"错误"等词，结果把正常结果判成失败，
# 导致"工具结果有效率"从真实值掉到 54%——指标失真比不测更危险。
# 因此只匹配工具自己产出的、含义明确的错误/空结果标记。
NO_DATA_MARKS = (
    "Error invoking tool",   # LangChain 参数校验失败（如漏传必填参数）
    "API调用失败",            # 工具内部捕获的网络/接口异常
    "API未配置",              # 缺少 Key
    "返回错误",               # 上游接口返回非成功状态
    "未找到相关信息",          # RAG 检索未命中
    "未找到「",               # 周边搜索无 POI
    "未查询到城市",            # 天气无该城市数据
    "未收到返回",              # 中间件：调用未完成
    "抛出异常",               # 中间件：工具抛异常
)


# --------------------------------------------------------------------------- #
# 日志工具
# --------------------------------------------------------------------------- #
def latest_log() -> Path:
    files = sorted(LOG_DIR.glob("app_*.log"))
    if not files:
        raise SystemExit(f"{LOG_DIR} 下没有日志文件，后端是否已启动过？")
    return files[-1]


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)


def read_since(path: Path, offset: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    return lines[offset:]


def parse_tool_calls(lines: list[str]) -> list[dict]:
    """从日志行里还原工具调用序列，按顺序配对 发起/返回/异常"""
    calls: list[dict] = []
    pending: list[dict] = []

    for line in lines:
        m = RE_START.search(line)
        if m:
            rec = {"name": m.group(1), "ok": None, "result": ""}
            calls.append(rec)
            pending.append(rec)
            continue

        m = RE_FAIL.search(line)
        if m and pending:
            rec = pending.pop(0)
            rec["ok"] = False
            rec["result"] = "抛出异常"
            continue

        m = RE_OK.search(line)
        if m and pending:
            rec = pending.pop(0)
            rec["ok"] = True
            rec["result"] = line.split("result=", 1)[1].strip()[:200]

    # 只有发起没有返回 → 视为未完成
    for rec in pending:
        rec["ok"] = False
        rec["result"] = "未收到返回（可能超时或流被中断）"

    return calls


def has_no_data(result: str) -> bool:
    """该次工具调用是否「没拿到可用数据」（异常 / 缺参 / 空结果均计入）"""
    return any(m in result for m in NO_DATA_MARKS)


# --------------------------------------------------------------------------- #
# HTTP：登录 + SSE 流式提问
# --------------------------------------------------------------------------- #
def login() -> str:
    body = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(
        BASE + "/api/auth/login",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["access_token"]


def stream_chat(token: str, query: str, customer_id: int = 1) -> tuple[str, str | None]:
    """返回 (完整答案, 错误信息)"""
    payload = json.dumps(
        {"conversation_id": None, "customer_id": customer_id, "query": query}
    ).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/stream",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )

    parts: list[str] = []
    error: str | None = None
    with urllib.request.urlopen(req, timeout=180) as resp:
        dec = codecs.getincrementaldecoder("utf-8")()
        buf = ""
        while True:
            raw = resp.read(256)
            if not raw:
                break
            buf += dec.decode(raw)
            while "\n\n" in buf:
                event, buf = buf.split("\n\n", 1)
                for line in event.split("\n"):
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    if obj.get("error"):
                        error = obj["error"]
                    if obj.get("content"):
                        parts.append(obj["content"])
    return "".join(parts), error


# --------------------------------------------------------------------------- #
# LLM-as-judge
# --------------------------------------------------------------------------- #
JUDGE_PROMPT = """你是一名严格的技术评测员，正在评估一个智能客服系统的回答质量。

【用户问题】
{query}

【参考答案】
{reference}

【系统回答】
{answer}

请判断【系统回答】与【参考答案】在事实层面是否一致。

评分标准：
- 1 分：核心事实正确、覆盖参考答案的关键要点、没有编造事实
- 0 分：核心事实错误、答非所问、关键要点缺失、或存在明显编造
- 若系统回答表示"未找到相关信息"或为空，记 0 分

只输出一个 JSON 对象，不要输出其它任何内容：
{{"score": 1, "reason": "不超过40字的理由"}}"""


# 规则兜底关键词：系统明确表示"没检索到"时直接判 0，不交给模型裁判。
# 【为什么要这层兜底？】实测中裁判会把"根据现有知识库未找到相关信息"
# 判成 1 分（因为参考答案里的知识点它"读到了"，就误以为回答覆盖了）。
# 这是 LLM-as-judge 的典型失效模式，必须用确定性规则拦住。
EMPTY_HINTS = ("未找到相关信息", "未找到", "没有找到", "暂无相关", "无法回答")


async def judge(chat, query: str, answer: str, reference: str, rag_missed: bool) -> tuple[int, str]:
    text = (answer or "").strip()
    if not text:
        return 0, "系统回答为空"
    if len(text) < 15:
        return 0, f"系统回答过短，疑似未作答（{len(text)}字）"
    if len(text) < 60 and any(h in text for h in EMPTY_HINTS):
        return 0, "系统明确表示未检索到信息"
    # RAG 明确未命中、而回答仍给出具体事实细节 → 这些细节未经知识库验证
    # （模型凭自身知识补全）。本项目评测的是 RAG 系统的准确率，检索没生效就不算通过。
    # 这里只针对 rag_summarize 这一个明确标记做判定，不做泛化关键词匹配。
    if rag_missed:
        return 0, "RAG 检索未命中，回答未经知识库验证"

    prompt = JUDGE_PROMPT.format(query=query, reference=reference, answer=text[:1500])
    try:
        resp = await chat.ainvoke(prompt)
        raw = resp.content if hasattr(resp, "content") else str(resp)
        m = re.search(r"\{.*?\}", str(raw), re.S)
        if not m:
            return 0, f"裁判未返回JSON：{str(raw)[:60]}"
        obj = json.loads(m.group(0))
        return int(obj.get("score", 0)), str(obj.get("reason", ""))[:60]
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"裁判打分失败：{exc}")
        return 0, f"裁判异常：{exc}"


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
async def main() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    samples = golden["agent"]
    if not samples:
        print("黄金集 agent 段为空")
        return

    chat = get_chat_model()
    log_file = latest_log()
    token = login()

    print("=" * 78)
    print(f"端到端评测   样本数={len(samples)}   日志={log_file.name}")
    print("=" * 78)

    rows: list[dict] = []
    total_calls = ok_calls = valid_calls = 0
    tool_match = 0
    judge_pass = 0

    for s in samples:
        offset = count_lines(log_file)

        try:
            answer, err = stream_chat(token, s["query"])
        except Exception as exc:  # noqa: BLE001
            answer, err = "", f"{type(exc).__name__}: {exc}"

        await asyncio.sleep(0.8)  # 等日志异步落盘
        calls = parse_tool_calls(read_since(log_file, offset))

        actual = [c["name"] for c in calls]
        expected = list(s.get("expected_tools", []))

        # --- 工具统计 ---
        for c in calls:
            total_calls += 1
            if c["ok"]:
                ok_calls += 1
                if not has_no_data(c["result"]):
                    valid_calls += 1

        sel_ok = set(actual) == set(expected)
        tool_match += int(sel_ok)

        # --- 答案质量 ---
        # RAG 明确未命中时，回答里的事实细节无从验证，直接判 0
        rag_missed = any(
            c["name"] == "rag_summarize" and "未找到相关信息" in c["result"] for c in calls
        )

        if err:
            score, reason = 0, f"流内错误：{err[:40]}"
        else:
            score, reason = await judge(chat, s["query"], answer, s["reference"], rag_missed)
        judge_pass += score

        rows.append(
            {
                "id": s["id"],
                "query": s["query"],
                "expected": expected,
                "actual": actual,
                "sel_ok": sel_ok,
                "score": score,
                "reason": reason,
                "answer": answer,
            }
        )

        mark = "OK " if (sel_ok and score) else "!! "
        print(f"\n{mark}{s['id']}  {s['query']}")
        print(f"      期望工具: {expected or '（不调用）'}")
        print(f"      实际工具: {actual or '（未调用）'}   选择{'正确' if sel_ok else '不符'}")
        for c in calls:
            tag = "OK  " if c["ok"] and not has_no_data(c["result"]) else "FAIL"
            print(f"        [{tag}] {c['name']}  {c['result'][:70]}")
        print(f"      裁判打分: {score}  ({reason})")

    # ---------------- 汇总 ---------------- #
    n = len(samples)
    print("\n" + "=" * 78)
    print("汇总")
    print("=" * 78)
    print(f"问答准确率（LLM裁判）      : {judge_pass}/{n} = {judge_pass / n * 100:.1f}%")
    print(f"工具选择准确率             : {tool_match}/{n} = {tool_match / n * 100:.1f}%")
    if total_calls:
        print(f"工具调用成功率（无异常）   : {ok_calls}/{total_calls} = {ok_calls / total_calls * 100:.1f}%")
        print(f"工具结果有效率（无异常且有数据）: {valid_calls}/{total_calls} = {valid_calls / total_calls * 100:.1f}%")
    else:
        print("工具调用成功率             : 本次没有任何工具调用（检查黄金集或工具注册表）")

    bad = [r for r in rows if not r["sel_ok"] or not r["score"]]
    if bad:
        print(f"\n待改进样本（{len(bad)} 条）：")
        for r in bad:
            print(f"  {r['id']}  工具 {r['expected']}→{r['actual']}  得分{r['score']}  {r['reason']}")

    out = Path("/app/logs/eval_agent_report.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细已保存：{out}")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
