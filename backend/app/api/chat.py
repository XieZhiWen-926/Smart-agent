"""
聊天路由：
- POST /api/chat/stream：SSE 流式对话（核心）
- 会话的增删查、历史消息查询

关键实现要点：
SSE 是长连接流，依赖注入 get_db 的 finally 会在响应函数返回后立即关闭 session，
导致流还没吐完 chunk，ORM session 已被回收。因此流式接口必须在路由函数内
手动 `async with AsyncSessionLocal() as db:`，并把整个流的生成器写在这个上下文里，
保证 session 生命周期覆盖整个流式响应。
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.database import AsyncSessionLocal
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.conversation import (
    ChatRequest,
    ConversationCreate,
    ConversationResponse,
    MessageResponse,
)
from app.services.chat_service import ChatService
from app.utils.logger import logger

router = APIRouter()


def _friendly_error(exc: Exception) -> str:
    """
    把大模型/上游抛出的原始异常翻译成"用户能看懂、能照做"的一句话。

    为什么要做这层翻译：
    上游（DashScope）的报错是给开发者看的，形如
        request_id: xxx status_code: 400 code: Arrearage message: Access denied...
    直接推到前端，用户既看不懂也不知道该怎么办。这里按错误码归类，
    给出可执行的处置建议；未识别的错误再兜底取首行，避免整段长文本糊在气泡里。
    """
    raw = str(exc)
    lowered = raw.lower()

    # 按"最常见 → 最罕见"排序，命中即返回
    if "arrearage" in lowered or "overdue-payment" in lowered:
        return (
            "大模型账户欠费（Arrearage），服务已被停用。"
            "请到阿里云百炼控制台充值，到账后直接重发即可，无需重启服务。"
        )
    if "throttling" in lowered or "rate limit" in lowered:
        return "请求过于频繁，已被大模型服务限流，请稍等几秒后重试。"
    if "invalidapikey" in lowered or "invalid_api_key" in lowered:
        return "DASHSCOPE_API_KEY 无效，请检查根目录 .env 中的配置。"
    if "model not exist" in lowered or "model_not_found" in lowered:
        return "模型名不存在，请检查 .env 中的 CHAT_MODEL_NAME 是否为百炼支持的模型。"
    if "timeout" in lowered or "timed out" in lowered:
        return "调用大模型超时，请稍后重试。"
    if "connection" in lowered or "network" in lowered:
        return "无法连接大模型服务，请检查容器网络与出口连通性。"

    # 兜底：只取第一行，防止把整段堆栈/长文本推给前端
    first_line = raw.strip().splitlines()[0] if raw.strip() else "未知错误"
    return f"模型调用失败：{first_line}"


@router.post("/stream")
async def stream_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """
    SSE 流式对话。
    响应格式：每行 `data: {json}\\n\\n`，结束时发送 `data: [DONE]\\n\\n`。
    """

    async def event_generator():
        # 手动持有 session，整个流式期间不关闭；
        # async with 保证流结束（或异常）后 session 自动关闭回收连接
        async with AsyncSessionLocal() as db:
            try:
                async for chunk in ChatService.stream_chat(
                    db=db,
                    conversation_id=req.conversation_id,
                    customer_id=req.customer_id,
                    query=req.query,
                ):
                    # chunk 是 service 产出的文本片段，包成 JSON 帧
                    payload = json.dumps({"content": chunk}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:  # noqa: BLE001
                # 完整堆栈留在服务端日志里便于排查；
                # 推给前端的是翻译过的、用户能照做的原因
                logger.exception("SSE 流式聊天异常")
                err = json.dumps({"error": _friendly_error(e)}, ensure_ascii=False)
                yield f"data: {err}\n\n"
                yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx 不要缓冲，否则 SSE 会被攒一批再发
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations")
async def list_conversations(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按客户列出会话"""
    items = await ChatService.list_conversations(db, customer_id)
    return ApiResponse(
        data=[ConversationResponse.model_validate(c) for c in items],
        message="success",
    )


@router.post("/conversations", status_code=201)
async def create_conversation(
    obj: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建会话"""
    conv = await ChatService.create_conversation(db, obj.customer_id, obj.title)
    return ApiResponse(data=ConversationResponse.model_validate(conv), message="创建成功")


@router.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询会话历史消息"""
    msgs = await ChatService.get_conversation_messages(db, conv_id)
    return ApiResponse(data=[MessageResponse.model_validate(m) for m in msgs])


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除会话（级联删除消息）"""
    await ChatService.delete_conversation(db, conv_id)
    return ApiResponse(message="删除成功")
