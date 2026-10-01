"""
数据集相关 Pydantic Schema
===========================
请求 / 响应的数据校验模型，供 api/datasets.py 使用。
"""
# `from __future__ import annotations`：让类型注解延迟求值，
# 可以使用 list[dict] 这种新写法而不用担心旧版本兼容问题。
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 请求 Schema
# ---------------------------------------------------------------------------
class DatasetCreate(BaseModel):
    """创建数据集（上传 CSV 后调用）"""
    name: str = Field(..., max_length=128, description="数据集名称")
    description: str = Field(default="", description="数据集描述（用于语义匹配）")
    source_file: str = Field(..., description="原始 CSV 文件名（服务器端路径）")


class DatasetQueryRequest(BaseModel):
    """对数据集发起自然语言查询"""
    query: str = Field(..., description="用户自然语言问题")
    dataset_id: Optional[int] = Field(
        default=None,
        description="指定数据集 ID；不传则由路由器自动选择最合适的数据集",
    )


# ---------------------------------------------------------------------------
# 响应 Schema
# ---------------------------------------------------------------------------
class DatasetResponse(BaseModel):
    """数据集元数据响应"""
    id: int
    name: str
    description: str
    table_name: str
    source_file: str
    row_count: int
    column_count: int
    columns_meta: list[dict]
    status: str
    error_msg: str
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DatasetQueryResponse(BaseModel):
    """自然语言查询的统一响应"""
    answer: str = Field(..., description="自然语言回答")
    route: str = Field(..., description="路由结果：text2sql / rag / clarify / tool")
    source: str = Field(default="", description="数据来源（数据集名或知识库）")
    confidence: float = Field(default=0.0, description="置信度 0~1")
    sql: Optional[str] = Field(default=None, description="Text2SQL 生成的 SQL（调试用）")
    results: Optional[list[dict]] = Field(default=None, description="原始查询结果行")


class UploadResponse(BaseModel):
    """CSV 上传后的响应"""
    dataset_id: int
    task_id: str = Field(..., description="Celery 任务 ID，前端轮询用")
    message: str = "文件已上传，正在后台导入数据集"
