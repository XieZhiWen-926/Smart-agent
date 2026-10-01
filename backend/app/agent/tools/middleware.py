"""
Agent 中间件：用新版 LangChain 1.x 中间件 API 做工具调用监控与模型调用日志。

【中间件是什么？】类似"切面/拦截器"：在 Agent 每次调工具、每次调大模型
的前后插入我们自定义的逻辑（这里主要是打日志、异常兜底），
不用改动 Agent 本身的代码。在 react_agent.py 的 build() 里被装配进去。

【★ 版本适配说明（改这个文件前必读）★】
LangChain 1.x 对中间件钩子的签名有硬性要求，写错会在"聊天时"才报
TypeError（构建 agent 时不报，非常难查）。两个坑：

  1) before_model 钩子必须接收「两个」参数：state 和 runtime。
     def log_before_model(state, runtime)      ✅ 正确
     def log_before_model(state)               ❌ TypeError:
        log_before_model() takes 1 positional argument but 2 were given

  2) wrap_tool_call 钩子接收 (request, handler)，工具名/参数/调用ID
     不在 request 上直接暴露，而是放在 request.tool_call 这个 dict 里：
     request.tool_call["name"] / ["args"] / ["id"]
     老写法 request.tool_name 取不到值，日志会一直是 <unknown>。

下面两个函数已按 1.x 规范写好，请勿"简化"回单参数版本。
"""
from typing import Any
import re
from langchain.agents.middleware import before_model, wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage

from app.utils.logger import logger


# ------------------------------------------------------------
# 工具调用监控中间件
# ------------------------------------------------------------
@wrap_tool_call
async def monitor_tool(request: ToolCallRequest, handler) -> ToolMessage:
    """包裹每一次工具调用：记录工具名、入参，并捕获异常兜底返回。

    参数:
        request: ToolCallRequest，工具信息在 request.tool_call 里
                 （结构：{"name": 工具名, "args": 参数字典, "id": 调用ID}）
        handler: 被包裹的下游执行器，调用 await handler(request) 真正执行工具
    返回:
        ToolMessage
    """
    # 兼容取值：优先读 request.tool_call（LangChain 1.x 的正确位置），
    # 取不到再退回老字段，保证升级/降级都不会让这里抛异常。
    tool_call = getattr(request, "tool_call", None)
    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name", "<unknown>")
        tool_args = tool_call.get("args", {}) or {}
        tool_call_id = tool_call.get("id", "")
    else:  # pragma: no cover - 老版本字段兜底
        tool_name = getattr(request, "tool_name", "<unknown>")
        tool_args = getattr(request, "args", {}) or {}
        tool_call_id = getattr(request, "tool_call_id", "")

    # 参数可能很长，截断避免日志爆炸
    args_preview = str(tool_args)
    if len(args_preview) > 500:
        args_preview = args_preview[:500] + "..."

    logger.info(f"[ToolCall] -> {tool_name} args={args_preview}")

    try:
        # await handler(request) 才真正执行工具；这行之前是"前置逻辑"，之后是"后置逻辑"
        result: ToolMessage = await handler(request)
        # 结果也做截断
        content = str(getattr(result, "content", ""))
        if len(content) > 500:
            content = content[:500] + "..."
        logger.info(f"[ToolCall] <- {tool_name} result={content}")
        return result
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[ToolCall] !! {tool_name} 执行异常: {e}")
        # 异常时返回一条错误 ToolMessage，避免中断整个 Agent 循环
        cleaned = re.sub(r"\{[^{}]*\}", "…", str(e))
        cleaned = " ".join(cleaned.split())[:200] or "未知错误"
        return ToolMessage(
            content=f"工具 {tool_name} 调用失败：{cleaned}。请修正参数后重试。",
            tool_call_id=tool_call_id,
            status="error",
        )


# ------------------------------------------------------------
# 模型调用前日志中间件
# ------------------------------------------------------------
@before_model
async def log_before_model(state: Any, runtime: Any = None) -> dict:
    """每次调用 LLM 前打印当前消息队列长度，便于排查上下文堆积。

    参数:
        state:   AgentState，含 messages 列表
        runtime: LangGraph 运行时上下文（框架会传进来；本函数用不到，
                 但签名里必须留着，否则框架调用时会报参数数量不匹配）
    返回:
        dict：新版中间件要求返回一个 patch dict（这里返回空 dict，不修改 state）
    """
    messages = getattr(state, "messages", None)
    if messages is None and isinstance(state, dict):
        messages = state.get("messages", [])
    msg_count = len(messages) if messages is not None else 0
    logger.info(f"[BeforeModel] 当前消息数 = {msg_count}")
    return {}


__all__ = ["monitor_tool", "log_before_model"]
