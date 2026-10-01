"""通用响应包装：统一前后端交互格式，避免每个接口各自定义返回结构。

所有 api 路由的响应基本都包一层 ApiResponse / PaginatedResponse。
"""
from typing import Generic, Optional, Sequence, TypeVar

from pydantic import BaseModel

# TypeVar + Generic 是 Python 的"泛型"写法：
# ApiResponse[UserResponse] 就表示 data 字段是 UserResponse 类型，
# 同一个包装类可以装任意类型的数据，Swagger 文档也能正确显示。
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一接口响应包装：code=0 表示成功，非 0 为业务错误码"""

    code: int = 0
    message: str = "success"
    data: Optional[T] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应包装：items 为当前页数据，total 为总数，page/page_size 为分页参数"""

    items: Sequence[T]
    total: int = 0
    page: int = 1
    page_size: int = 20
