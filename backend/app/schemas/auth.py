"""认证相关 Pydantic 模型（Pydantic v2 风格）。

供 api/auth.py 使用：注册请求体 UserCreate、用户响应 UserResponse、登录令牌 TokenResponse。

【Field 是什么】Field(...) 给字段附加校验规则和文档说明。
第一个位置参数是默认值：`...` 表示"必填"；写成 default=xxx 或不写则可选。
校验不通过时 FastAPI 自动返回 422，不会进到路由函数里。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    """注册新用户（管理员/坐席）"""

    # ... 表示必填；min_length/max_length 是字符串长度校验
    username: str = Field(..., min_length=3, max_length=64, description="登录用户名")
    password: str = Field(..., min_length=6, max_length=128, description="明文密码")
    full_name: str = Field(default="", max_length=64, description="真实姓名")
    role: str = Field(default="admin", description="角色：admin/operator")


class UserResponse(BaseModel):
    """用户信息响应（不返回密码哈希）

    【★ 为什么必须有 from_attributes=True？★】
    路由里是这样用的：UserResponse.model_validate(user_orm对象)
    默认情况下 pydantic 只接受 dict 或本模型实例，直接传 SQLAlchemy 的
    ORM 对象会报错：
        ValidationError: 1 validation error for UserResponse
        Input should be a valid dictionary or instance of UserResponse [type=model_type]
    加上 from_attributes=True 后，pydantic 会按"属性名"从任意对象取值，
    才能直接从 ORM 对象转换。本项目其他 Response 模型都带这个配置，
    唯独这里漏了，会导致 /api/auth/me 和 /api/auth/register 返回 500。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    """登录成功返回的 JWT 令牌"""

    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    """登录请求体（备用，实际登录走 OAuth2PasswordRequestForm 表单）"""

    username: str
    password: str
