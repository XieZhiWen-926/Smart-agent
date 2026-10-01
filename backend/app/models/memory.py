"""长期记忆表：从对话中抽取的事实/偏好/摘要，跨会话持久化。

上游：repositories/memory_repo.py、services/memory_service.py、agent/memory/ 里的记忆管理器；
下游：MySQL long_term_memories 表。
"""
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LongTermMemory(Base):
    """
    长期记忆表。
    记忆类型：
    - fact: 事实性记忆（如"客户购买了X型号扫地机器人"）
    - preference: 偏好记忆（如"客户喜欢简洁回答"）
    - summary: 滚动摘要（对一段对话的压缩总结）
    """
    __tablename__ = "long_term_memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="记忆ID")
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True, comment="关联客户ID")
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="记忆类型：fact/preference/summary")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="记忆内容")
    importance: Mapped[int] = mapped_column(Integer, default=5, comment="重要性评分1-10，影响召回排序")
    # embedding 向量存 JSON 数组（float列表），单客户记忆量有界时用 Python 余弦计算
    # 高规模时应迁移到 MySQL 9 VECTOR 类型或 Milvus 专用向量库
    embedding: Mapped[list] = mapped_column(JSON, nullable=True, comment="内容的向量嵌入（JSON数组）")
    source_message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=True, comment="来源消息ID")
    last_used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后被召回使用的时间")
    use_count: Mapped[int] = mapped_column(Integer, default=0, comment="被召回使用次数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
