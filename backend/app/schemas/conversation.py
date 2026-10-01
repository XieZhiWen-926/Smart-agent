"""会话 / 消息相关的 Pydantic 请求与响应模型（对外 API 契约）。

供 api/chat.py 使用。Response 类带 `from_attributes=True`，
可以直接 `XxxResponse.model_validate(orm对象)` 把 ORM 行转成响应模型，
不用手写逐字段拷贝。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    """创建会话请求"""
    customer_id: int = Field(..., description="客户ID")
    title: str = Field(default="新会话", description="会话标题")


class ConversationResponse(BaseModel):
    """会话响应"""
    # from_attributes=True：允许从 ORM 对象（按属性名取值）构建本模型，
    # 路由里就能写 ConversationResponse.model_validate(conv)
    model_config = ConfigDict(from_attributes=True)  # 直接从 ORM 对象转换

    id: int
    customer_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """消息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    token_count: int
    tool_name: Optional[str] = None
    created_at: datetime


class ChatRequest(BaseModel):
    """流式对话请求"""
    conversation_id: Optional[int] = Field(
        default=None,
        description="会话ID；不传或传0则新建会话",
    )
    customer_id: int = Field(..., description="客户ID")
    query: str = Field(..., description="用户提问")
