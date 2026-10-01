"""长期记忆管理路由：查看 / 删除 / 手动触发抽取，业务逻辑在 services/memory_service.py。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.memory import ExtractionRequest, MemoryListResponse, MemoryResponse
from app.services.memory_service import MemoryService

router = APIRouter()


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    customer_id: int = Query(..., description="客户ID"),
    memory_type: Optional[str] = Query(default=None, description="记忆类型：fact/preference/summary"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按客户列出长期记忆，可按类型过滤"""
    items = await MemoryService.list_memories(db, customer_id, memory_type=memory_type)
    return MemoryListResponse(
        items=[MemoryResponse.model_validate(m) for m in items],
        total=len(items),
    )


@router.delete("/{memory_id}", response_model=ApiResponse)
async def delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除单条记忆"""
    await MemoryService.delete_memory(db, memory_id)
    return ApiResponse(message="删除成功")


@router.post("/extract", response_model=ApiResponse)
async def trigger_extraction(
    body: ExtractionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发从指定会话抽取长期记忆"""
    await MemoryService.trigger_extraction(db, body.customer_id, body.conversation_id)
    return ApiResponse(message="记忆抽取已触发")
