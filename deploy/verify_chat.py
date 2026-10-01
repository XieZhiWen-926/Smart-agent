"""验证 SSE 流式聊天：精确测量分片数量与到达时间，判断是否真正"逐字流式" """
import codecs
import json
import time
import urllib.request
import urllib.parse

BASE = "http://localhost:8000"


def login():
    body = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    r = urllib.request.Request(BASE + "/api/auth/login", data=body,
                              headers={"Content-Type": "application/x-www-form-urlencoded"},
                              method="POST")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())["access_token"]


def stream_chat(token, query, customer_id=1):
    payload = json.dumps({"conversation_id": None, "customer_id": customer_id,
                          "query": query}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/stream", data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST")

    chunks = []          # (到达时间, 文本)
    error = None
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        # 增量解码器：正确处理跨分片的多字节 UTF-8 字符
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
                        chunks.append((time.time() - t0, obj["content"]))
    return chunks, error, time.time() - t0


tok = login()
print("=" * 68)
print("SSE 流式聊天精确测量")
print("=" * 68)

for q in ["扫地机器人工作的时候有异响怎么办？", "你好，请简单介绍一下你自己"]:
    print(f"\n>>> 提问：{q}")
    try:
        chunks, err, total = stream_chat(tok, q)
    except Exception as e:
        print(f"    [FAIL] {type(e).__name__}: {e}")
        continue

    if err:
        print(f"    [FAIL] 流中错误：{err}")
        continue
    if not chunks:
        print("    [FAIL] 未收到任何内容")
        continue

    answer = "".join(c[1] for c in chunks)
    print(f"    分片数 = {len(chunks)}   总耗时 = {total:.1f}s   回答长度 = {len(answer)} 字")
    print(f"    首片到达 = {chunks[0][0]:.1f}s   末片到达 = {chunks[-1][0]:.1f}s")

    if len(chunks) >= 10:
        print(f"    [PASS] 分片数 >= 10 → 真正的逐字流式（打字机效果）")
    elif len(chunks) > 1:
        print(f"    [WARN] 只有 {len(chunks)} 个分片 → 是流式但粒度很粗，打字机效果不明显")
    else:
        print(f"    [FAIL] 只有 1 个分片 → 整段一次性返回，没有打字机效果")

    print(f"    回答前 120 字：{answer[:120]!r}")

print("\n" + "=" * 68)
