"""聊天业务逻辑：会话管理 + 流式对话编排。

上游：api/chat.py 路由；下游：repositories/conversation_repo.py 存取会话/消息，
agent/react_agent.py 的 SmartAgent 负责真正的"思考->调工具->回答"。
"""
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.react_agent import SmartAgent
from app.models.conversation import Conversation, Message
from app.repositories.conversation_repo import ConversationRepository
from app.utils.logger import logger


class ChatService:
    """会话与聊天的业务入口，路由层只调这里，不直接碰 repo/agent"""

    @staticmethod
    async def create_conversation(
        db: AsyncSession,
        customer_id: int,
        title: str = "新会话",
    ) -> Conversation:
        """新建会话并提交"""
        conv = await ConversationRepository.create(db, customer_id, title)
        await db.commit()
        logger.info(f"[chat] 新建会话 id={conv.id} customer={customer_id}")
        return conv

    @staticmethod
    async def list_conversations(
        db: AsyncSession, customer_id: int
    ) -> list[Conversation]:
        """列出某客户全部会话"""
        return await ConversationRepository.list_by_customer(db, customer_id)

    @staticmethod
    async def get_conversation_messages(
        db: AsyncSession, conversation_id: int
    ) -> list[Message]:
        """取某会话的全部历史消息（正序）"""
        return await ConversationRepository.get_messages(db, conversation_id)

    @staticmethod
    async def stream_chat(
        db: AsyncSession,
        conversation_id: Optional[int],
        customer_id: int,
        query: str,
    ) -> AsyncGenerator[str, None]:
        """
        流式对话主流程。

        【什么是异步生成器】`async def` + `yield` 的函数不会一次性返回全部结果，
        而是每 yield 一次就向调用方"吐"一小段，调用方用 `async for` 逐段接收——
        这就是"打字机"式流式输出的实现原理。

        重要（SSE 与 DB session 生命周期）：
        - 本方法是一个异步生成器，FastAPI 路由会把它直接包成 SSE 响应；
        - 传入的 db session 必须覆盖整个生成器的执行周期——
          即在所有 chunk yield 完之前，get_db 的 finally 不能 close()；
        - 因此路由层不要用"普通依赖注入 + 请求结束即关 session"的写法，
          而应在生成器内部持有 session，或保证依赖作用域等于流生命周期。
        """
        # 1) 会话不存在则新建（conversation_id 为空 / 查不到都视为新建）
        conv: Optional[Conversation] = None
        if conversation_id:
            conv = await ConversationRepository.get_by_id(db, conversation_id)
        if conv is None:
            conv = await ConversationRepository.create(db, customer_id)
            await db.commit()
            logger.info(f"[chat] 自动新建会话 id={conv.id} customer={customer_id}")

        # 2) 轻量构建 agent（每请求一个新实例，不共享状态）
        agent = SmartAgent(customer_id=customer_id, conversation_id=conv.id)
        await agent.build(db)

        # 3) 流式执行并逐段透传
        async for chunk in agent.execute_stream(query, db):
            yield chunk

    @staticmethod
    async def delete_conversation(db: AsyncSession, conversation_id: int) -> None:
        """删除会话（repo 层已先删消息再删会话，避免孤儿消息，详见 conversation_repo.delete）"""
        await ConversationRepository.delete(db, conversation_id)
        await db.commit()
        logger.info(f"[chat] 删除会话 id={conversation_id}")
