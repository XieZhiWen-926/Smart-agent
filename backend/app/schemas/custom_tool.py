"""
自定义工具的 Pydantic Schema（v2 风格），供 api/tools.py 使用。
- Create / Update / Response / Test 请求响应模型。
- Response 用 from_attributes=True 直接从 ORM 对象转换。
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomToolCreate(BaseModel):
    """创建自定义工具请求体"""
    name: str = Field(..., max_length=128, description="工具名称（英文，唯一，作为函数名）")
    description: str = Field(..., description="工具描述（告诉 LLM 何时使用）")
    tool_type: str = Field(
        ...,
        description="工具类型：builtin / map_amap / map_baidu / python_func / http_api",
    )
    parameters_schema: dict[str, Any] = Field(..., description="参数 JSON Schema")
    config: Optional[dict[str, Any]] = Field(default=None, description="工具配置，不同类型含义不同")
    is_enabled: bool = Field(default=True, description="是否启用")


class CustomToolUpdate(BaseModel):
    """更新自定义工具请求体：所有字段可选，部分更新"""
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = None
    tool_type: Optional[str] = None
    parameters_schema: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None


class CustomToolResponse(BaseModel):
    """自定义工具响应体（ORM -> Schema）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    tool_type: str
    parameters_schema: dict[str, Any]
    config: Optional[dict[str, Any]]
    is_enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ToolTestRequest(BaseModel):
    """工具在线测试请求

    【注意】tool_id 是可选的，且**通常不需要传**。
    因为路由已经是 POST /api/tools/{tool_id}/test，ID 已经在 URL 路径里了。
    这里保留该字段只是为了兼容老调用方；如果把它写成必填，
    用 Swagger 测试时就必须在 body 里重复填一遍 ID，否则报 422，
    对使用者非常不友好。
    正确的请求体示例：
        { "params": { "city": "北京" } }
    """

    tool_id: int = Field(default=0, description="要测试的工具 ID（可省略，以 URL 路径为准）")
    params: dict[str, Any] = Field(default_factory=dict, description="调用参数")


class ToolTestResponse(BaseModel):
    """工具在线测试响应"""
    success: bool
    result: str
    error: Optional[str] = None


__all__ = [
    "CustomToolCreate",
    "CustomToolUpdate",
    "CustomToolResponse",
    "ToolTestRequest",
    "ToolTestResponse",
]
