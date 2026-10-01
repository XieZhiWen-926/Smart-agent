"""
长期记忆抽取的 Celery 任务。
- 由路由或其它系统在需要时异步触发
- worker 内同样用 asyncio.run 驱动 async 的 MemoryService
"""
import asyncio
from typing import Any

from app.database import AsyncSessionLocal
from app.services.memory_service import MemoryService
from app.tasks.celery_app import celery
from app.utils.logger import logger


async def _extract(customer_id: int, conversation_id: int) -> dict[str, Any]:
    """异步执行记忆抽取"""
    async with AsyncSessionLocal() as db:
        await MemoryService.trigger_extraction(db, customer_id, conversation_id)
    logger.info(f"记忆抽取完成 customer_id={customer_id} conversation_id={conversation_id}")
    return {"customer_id": customer_id, "conversation_id": conversation_id}


@celery.task(name="extract_memory")
def extract_memory_task(customer_id: int, conversation_id: int) -> dict[str, Any]:
    """Celery 入口（同步）：asyncio.run 临时开事件循环驱动异步抽取逻辑"""
    try:
        return asyncio.run(_extract(customer_id, conversation_id))
    except Exception as e:  # noqa: BLE001
        # 任务失败不能让 worker 崩溃：记日志并把错误作为结果返回
        logger.exception("记忆抽取任务失败")
        return {"customer_id": customer_id, "conversation_id": conversation_id, "error": str(e)}
