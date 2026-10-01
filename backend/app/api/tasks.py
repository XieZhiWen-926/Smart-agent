"""异步任务状态查询路由：前端轮询 Celery 任务进度。

说明：任务状态只是对 async_tasks 表的简单只读查询，项目里未单建 TaskService，
故本文件直接查询；逻辑如变复杂（权限过滤、任务取消等）应下沉到 service 层。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.async_task import AsyncTask
from app.models.user import User
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按 Celery 任务 ID 查询任务状态"""
    result = await db.execute(select(AsyncTask).where(AsyncTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return ApiResponse(
        data={
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "error_msg": task.error_msg,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
    )


@router.get("")
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """最近任务列表（最多 100 条，按创建时间倒序）"""
    result = await db.execute(
        select(AsyncTask).order_by(AsyncTask.created_at.desc()).limit(100)
    )
    tasks = result.scalars().all()
    return ApiResponse(
        data=[
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "status": t.status,
                "progress": t.progress,
                "error_msg": t.error_msg,
                "created_at": t.created_at,
            }
            for t in tasks
        ]
    )
