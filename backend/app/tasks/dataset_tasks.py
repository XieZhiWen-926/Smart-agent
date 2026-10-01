"""
CSV 数据集导入的 Celery 任务。

注意：Celery worker 运行在同步上下文中，不能直接复用 FastAPI 的请求级 session
和 await。这里的做法是：
1. 任务函数本身是同步的（@celery.task 装饰）；
2. 内部用 asyncio.run() 驱动一个 async 协程；
3. 协程里手动 `async with AsyncSessionLocal() as db:` 拿到独立 session；
4. 同时把任务进度回写 async_tasks 表，供前端轮询。
"""
import asyncio
from typing import Any, Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.async_task import AsyncTask
from app.services.dataset_service import DatasetService
from app.tasks.celery_app import celery
from app.utils.logger import logger


async def _update_task_status(
    celery_task_id: str,
    status: str,
    progress: Optional[int] = None,
    result: Optional[dict] = None,
    error_msg: str = "",
) -> None:
    """更新 async_tasks 表中的任务状态（按 Celery task_id 匹配）"""
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(select(AsyncTask).where(AsyncTask.task_id == celery_task_id))
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = status
        if progress is not None:
            row.progress = progress
        if result is not None:
            row.result = result
        row.error_msg = error_msg
        await db.commit()


async def _import_csv(celery_task_id: str, dataset_id: int, file_path: str) -> dict[str, Any]:
    """真正的异步导入逻辑：调 DatasetService 完成 CSV 解析与物理表建表"""
    await _update_task_status(celery_task_id, status="processing", progress=5)
    try:
        async with AsyncSessionLocal() as db:
            result = await DatasetService.import_csv_task(db, dataset_id, file_path)
        await _update_task_status(
            celery_task_id, status="completed", progress=100, result={"dataset_id": dataset_id}
        )
        logger.info(f"CSV 导入完成 dataset_id={dataset_id}")
        return {"dataset_id": dataset_id, "status": "completed", "result": result}
    except Exception as e:  # noqa: BLE001
        logger.exception(f"CSV 导入失败 dataset_id={dataset_id}")
        await _update_task_status(
            celery_task_id, status="failed", error_msg=str(e)
        )
        return {"dataset_id": dataset_id, "status": "failed", "error": str(e)}


@celery.task(bind=True, name="import_csv")
def import_csv_task(self, dataset_id: int, file_path: str) -> dict[str, Any]:
    """
    Celery 入口（同步）。
    self.request.id 即本次任务的 Celery task_id，与上传时落库的 async_tasks.task_id 对应。

    【为什么同步函数里能跑异步代码？】
    Celery worker 是同步环境，不能直接 await。asyncio.run() 会临时开一个
    事件循环，把异步协程跑完再关掉——这是"同步包异步"的标准做法。
    bind=True 让 Celery 把任务自身作为第一个参数 self 传进来，方便取 task_id。
    """
    return asyncio.run(_import_csv(self.request.id, dataset_id, file_path))
