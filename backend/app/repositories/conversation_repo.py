"""会话与消息数据访问层：封装对 conversations / messages 表的所有 SQL 操作。

上游：services/chat_service.py、services/memory_service.py；下游：models/conversation.py 定义的两张表。

【SQLAlchemy 2.0 异步查询三件套】
1. `select(模型类)` 构造查询（旧版是 session.query(模型类)）；
2. `await db.execute(stmt)` 异步执行，拿到 Result；
3. 从 Result 取数据：
   - `result.scalars().all()`      多行，返回 ORM 对象列表；
   - `result.scalar_one_or_none()` 单行或 None（查不到不报错）。
"""
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


class ConversationRepository:
    """会话表 CRUD + 消息追加/读取"""

    @staticmethod
    async def create(
        db: AsyncSession,
        customer_id: int,
        title: str = "新会话",
    ) -> Conversation:
        """新建一个会话"""
        conv = Conversation(customer_id=customer_id, title=title)
        db.add(conv)
        await db.flush()
        await db.refresh(conv)
        return conv

    @staticmethod
    async def get_by_id(db: AsyncSession, conv_id: int) -> Optional[Conversation]:
        """按主键取会话"""
        return await db.get(Conversation, conv_id)

    @staticmethod
    async def list_by_customer(db: AsyncSession, customer_id: int) -> list[Conversation]:
        """列出某客户的全部会话，按最近活跃倒序"""
        stmt = (
            select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(Conversation.updated_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def add_message(
        db: AsyncSession,
        conversation_id: int,
        role: str,
        content: str,
        token_count: int = 0,
        tool_name: Optional[str] = None,
    ) -> Message:
        """向会话追加一条消息（user/assistant/tool/system）"""
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            token_count=token_count,
            tool_name=tool_name,
        )
        db.add(msg)
        await db.flush()
        await db.refresh(msg)
        return msg

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        conversation_id: int,
        limit: Optional[int] = None,
    ) -> list[Message]:
        """
        取会话消息，按时间正序返回。
        - limit 不传则返回全部
        - 注意 SQL 层先按 created_at desc 取 limit 条，再反序还原时间线
        """
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        msgs = list(result.scalars().all())
        msgs.reverse()  # 还原为正序
        return msgs

    @staticmethod
    async def delete(db: AsyncSession, conv_id: int) -> None:
        """
        删除会话及其全部消息。

        【bug 修复说明】原实现只发了 `delete(Conversation)` 一条 SQL：
        - 这种"批量 DELETE 语句"不会触发 ORM 的 cascade="all, delete-orphan"
          （级联只在 session.delete(orm对象) 时生效）；
        - init.sql 建表时也没有声明外键 ON DELETE CASCADE；
        结果就是会话删了、消息成孤儿残留。这里先显式删消息再删会话。
        """
        await db.execute(delete(Message).where(Message.conversation_id == conv_id))
        await db.execute(delete(Conversation).where(Conversation.id == conv_id))
