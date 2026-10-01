"""客户管理相关 Pydantic 模型，供 api/customers.py 使用。

命名约定：XxxBase 公共字段 -> XxxCreate 创建请求（继承 Base）-> XxxUpdate 更新请求（全字段可选）-> XxxResponse 响应。
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomerBase(BaseModel):
    """客户公共字段"""

    name: str = Field(..., max_length=64, description="客户姓名")
    phone: str = Field(..., max_length=20, description="手机号")
    city: str = Field(default="", max_length=64, description="所在城市")
    address: str = Field(default="", max_length=255, description="详细地址")
    member_level: str = Field(default="普通", description="会员等级：普通/银卡/金卡/钻石")
    product_model: str = Field(default="", max_length=64, description="购买的产品型号")
    remark: str = Field(default="", description="备注")


class CustomerCreate(CustomerBase):
    """创建客户请求"""

    pass


class CustomerUpdate(BaseModel):
    """更新客户请求：全部字段可选，只传需要改的字段"""

    name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    member_level: Optional[str] = None
    product_model: Optional[str] = None
    remark: Optional[str] = None


class CustomerResponse(BaseModel):
    """客户信息响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    city: str
    address: str
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    member_level: str
    product_model: str
    purchase_date: Optional[datetime] = None
    remark: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CustomerListResponse(BaseModel):
    """客户列表响应"""

    items: List[CustomerResponse]
    total: int
