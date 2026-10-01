"""长期记忆管理业务逻辑：列表 / 删除 / 清空 / 手动触发抽取。

上游：api/memory.py 路由；下游：repositories/memory_repo.py 读写记忆表，
agent/memory/long_term_memory.py 的 memory_manager 负责调 LLM 做记忆抽取。
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory.long_term_memory import memory_manager
from app.models.memory import LongTermMemory
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.memory_repo import MemoryRepository
from app.utils.logger import logger


class MemoryService:
    """记忆管理的业务入口，供记忆管理 API 调用"""

    @staticmethod
    async def list_memories(
        db: AsyncSession,
        customer_id: int,
        memory_type: Optional[str] = None,
    ) -> list[LongTermMemory]:
        """列出某客户的长期记忆，可按类型过滤（fact/preference/summary）"""
        return await MemoryRepository.get_by_customer(db, customer_id, memory_type)

    @staticmethod
    async def delete_memory(db: AsyncSession, memory_id: int) -> None:
        """删除单条记忆"""
        await MemoryRepository.delete(db, memory_id)
        await db.commit()
        logger.info(f"[memory-service] 删除记忆 id={memory_id}")

    @staticmethod
    async def clear_customer_memories(db: AsyncSession, customer_id: int) -> None:
        """清空某客户全部长期记忆（隐私合规 / 重新画像用）"""
        await MemoryRepository.delete_by_customer(db, customer_id)
        await db.commit()
        logger.info(f"[memory-service] 清空 customer={customer_id} 全部记忆")

    @staticmethod
    async def trigger_extraction(
        db: AsyncSession,
        customer_id: int,
        conversation_id: int,
    ) -> int:
        """
        手动触发记忆抽取：对指定会话的最近窗口跑一次 LLM 抽取。
        返回本次新写入的记忆条数。
        """
        recent = await ConversationRepository.get_messages(db, conversation_id)
        msgs = [
            {"role": m.role, "content": m.content}
            for m in recent
            if m.role in ("user", "assistant")
        ]
        written = await memory_manager.extract_and_store(db, customer_id, msgs)
        logger.info(
            f"[memory-service] 手动抽取 customer={customer_id} "
            f"conv={conversation_id} 写入 {written} 条"
        )
        return written
