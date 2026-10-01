"""长期记忆相关的 Pydantic 请求与响应模型（对外 API 契约），供 api/memory.py 使用。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MemoryResponse(BaseModel):
    """单条长期记忆响应（包含模型全部字段）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    memory_type: str            # fact / preference / summary
    content: str
    importance: int
    embedding: Optional[list[float]] = None   # 向量体积较大，前端一般可忽略
    source_message_id: Optional[int] = None
    last_used_at: Optional[datetime] = None
    use_count: int
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    """记忆列表响应"""
    items: list[MemoryResponse]
    total: int = 0


class ExtractionRequest(BaseModel):
    """手动触发记忆抽取请求"""
    customer_id: int = Field(..., description="客户ID")
    conversation_id: int = Field(..., description="待抽取记忆的会话ID")
