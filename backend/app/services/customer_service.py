"""
客户业务服务：在 Repository 之上做业务规则校验。
- 手机号格式校验
- 手机号唯一性校验
- 对外方法签名与并行模块约定的契约保持一致

上游：api/customers.py 路由；下游：repositories/customer_repo.py。
约定：业务校验失败抛 ValueError，由路由层捕获转成 HTTP 400。
"""
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.repositories.customer_repo import CustomerRepository

# 中国大陆手机号简单正则：1 开头，第二位 3-9，共 11 位
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class CustomerService:
    """客户领域服务"""

    def __init__(self):
        self.repo = CustomerRepository()

    async def list_customers(self, db: AsyncSession, keyword: str | None = None) -> list[Customer]:
        """客户列表，支持关键词搜索"""
        return await self.repo.get_all(db, keyword=keyword)

    async def get_customer(self, db: AsyncSession, customer_id: int) -> Customer | None:
        """查询单个客户"""
        return await self.repo.get_by_id(db, customer_id)

    async def create_customer(self, db: AsyncSession, obj_in: dict) -> Customer:
        """
        新建客户。
        业务校验失败抛 ValueError，由路由层捕获转成 400。
        """
        phone = (obj_in.get("phone") or "").strip()
        if not _PHONE_RE.match(phone):
            raise ValueError("手机号格式不正确，应为 11 位大陆手机号")
        if await self.repo.get_by_phone(db, phone):
            raise ValueError("该手机号已存在客户档案")
        obj_in["phone"] = phone
        return await self.repo.create(db, obj_in)

    async def update_customer(self, db: AsyncSession, customer_id: int, obj_in: dict) -> Customer | None:
        """更新客户：若传了新手机号则做格式与唯一性校验"""
        if "phone" in obj_in and obj_in["phone"]:
            phone = obj_in["phone"].strip()
            if not _PHONE_RE.match(phone):
                raise ValueError("手机号格式不正确，应为 11 位大陆手机号")
            existing = await self.repo.get_by_phone(db, phone)
            if existing and existing.id != customer_id:
                raise ValueError("该手机号已被其他客户使用")
            obj_in["phone"] = phone
        return await self.repo.update(db, customer_id, obj_in)

    async def delete_customer(self, db: AsyncSession, customer_id: int) -> bool:
        """删除客户，返回是否删除成功"""
        return await self.repo.delete(db, customer_id)
