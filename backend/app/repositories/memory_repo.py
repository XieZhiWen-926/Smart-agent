"""长期记忆数据访问层：封装对 long_term_memories 表的所有 SQL 操作。
业务层只允许通过本仓库读写记忆表，禁止在 service/agent 里散落 SQL。

上游：services/memory_service.py、agent/memory/long_term_memory.py；下游：models/memory.py。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import LongTermMemory


class MemoryRepository:
    """长期记忆表 CRUD（全部为无状态静态方法，便于单元测试替换）"""

    @staticmethod
    async def get_by_customer(
        db: AsyncSession,
        customer_id: int,
        memory_type: Optional[str] = None,
    ) -> list[LongTermMemory]:
        """
        按客户取出记忆。
        - memory_type 不传则取该客户全部记忆（fact/preference/summary）
        - 单客户记忆量有界（几十~几百条），全量取出后在 Python 端做余弦召回
        """
        stmt = select(LongTermMemory).where(LongTermMemory.customer_id == customer_id)
        if memory_type:
            stmt = stmt.where(LongTermMemory.memory_type == memory_type)
        stmt = stmt.order_by(LongTermMemory.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, memory_id: int) -> Optional[LongTermMemory]:
        """按主键取单条记忆"""
        return await db.get(LongTermMemory, memory_id)

    @staticmethod
    async def create(db: AsyncSession, obj: LongTermMemory) -> LongTermMemory:
        """插入一条记忆并刷新拿到自增 id"""
        db.add(obj)
        await db.flush()          # 先 flush 拿到 id，由调用方决定何时 commit
        await db.refresh(obj)
        return obj

    @staticmethod
    async def update_usage(db: AsyncSession, memory_id: int) -> None:
        """命中召回后：累加使用次数 + 刷新最后使用时间"""
        obj = await db.get(LongTermMemory, memory_id)
        if obj is None:
            return
        obj.use_count = (obj.use_count or 0) + 1
        obj.last_used_at = datetime.utcnow()

    @staticmethod
    async def delete(db: AsyncSession, memory_id: int) -> None:
        """删除单条记忆"""
        await db.execute(delete(LongTermMemory).where(LongTermMemory.id == memory_id))

    @staticmethod
    async def delete_by_customer(db: AsyncSession, customer_id: int) -> None:
        """清空某客户的全部长期记忆（注销/隐私合规用）"""
        await db.execute(
            delete(LongTermMemory).where(LongTermMemory.customer_id == customer_id)
        )
