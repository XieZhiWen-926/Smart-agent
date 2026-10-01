"""会话与消息表：记录每轮对话，是长期记忆的原始数据源。

上游：repositories/conversation_repo.py、services/chat_service.py；
下游：MySQL conversations / messages 两张表（一对多关系）。
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    """会话表：一个客户可以有多个会话"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="会话ID")
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True, comment="关联客户ID")
    title: Mapped[str] = mapped_column(String(255), default="新会话", comment="会话标题（自动取首条消息摘要）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="最后活跃时间")

    # relationship：声明"一对多"关系（不建真实列），conv.messages 即可拿到全部消息
    # back_populates：与 Message.conversation 互相指向，形成双向关联
    # cascade="all, delete-orphan"：通过 ORM 删会话时，其消息一并删除。
    # 注意：这个级联只在"用 ORM 对象删除"（session.delete(conv)）时生效；
    # 直接发 SQL 的 delete(Conversation) 不会触发它（见 conversation_repo.delete 的处理）。
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """消息表：每条用户/助手消息都落库"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="消息ID")
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True, comment="关联会话ID")
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment="角色：user/assistant/tool/system")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    token_count: Mapped[int] = mapped_column(Integer, default=0, comment="消耗token数（估算）")
    tool_name: Mapped[str] = mapped_column(String(128), nullable=True, comment="如果是工具调用，记录工具名")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
