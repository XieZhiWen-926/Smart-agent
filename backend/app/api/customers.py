"""客户管理 CRUD 路由（全部需要登录）。

这是"标准四层写法"的范例：路由只收发 HTTP，业务校验在 CustomerService，
SQL 在 CustomerRepository。每个接口都通过 Depends(get_current_user) 强制登录。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.customer_service import CustomerService

router = APIRouter()
service = CustomerService()  # 模块级单例：service 本身无状态，全局共享一个即可


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    keyword: Optional[str] = Query(default=None, description="姓名/手机号/城市模糊搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """客户列表"""
    items = await service.list_customers(db, keyword=keyword)
    return CustomerListResponse(
        items=[CustomerResponse.model_validate(c) for c in items],
        total=len(items),
    )


@router.get("/{customer_id}", response_model=ApiResponse[CustomerResponse])
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """客户详情"""
    cust = await service.get_customer(db, customer_id)
    if cust is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户不存在")
    return ApiResponse(data=CustomerResponse.model_validate(cust))


@router.post("", response_model=ApiResponse[CustomerResponse], status_code=status.HTTP_201_CREATED)
async def create_customer(
    obj: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建客户"""
    try:
        cust = await service.create_customer(db, obj.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ApiResponse(data=CustomerResponse.model_validate(cust), message="创建成功")


@router.put("/{customer_id}", response_model=ApiResponse[CustomerResponse])
async def update_customer(
    customer_id: int,
    obj: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新客户"""
    try:
        cust = await service.update_customer(db, customer_id, obj.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if cust is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户不存在")
    return ApiResponse(data=CustomerResponse.model_validate(cust), message="更新成功")


@router.delete("/{customer_id}", response_model=ApiResponse)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除客户"""
    ok = await service.delete_customer(db, customer_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户不存在")
    return ApiResponse(message="删除成功")
