"""客户仓储：封装 customers 表的具体查询。

上游：services/customer_service.py；下游：models/customer.py 的 Customer 表。
通用增删改继承自 base.BaseRepository，本类只补充客户特有的查询。
"""
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    """客户表数据访问层"""

    def __init__(self):
        super().__init__(Customer)

    async def get_all(self, db: AsyncSession, keyword: Optional[str] = None) -> list[Customer]:
        """
        列表查询：支持按姓名/手机号/城市模糊搜索，按主键倒序返回。
        """
        stmt = select(Customer).order_by(Customer.id.desc())
        if keyword:
            # % 是 SQL 通配符："%张%" 表示"包含'张'"；or_ 表示多个条件满足其一即可
            like = f"%{keyword}%"
            stmt = (
                select(Customer)
                .where(
                    or_(
                        Customer.name.like(like),
                        Customer.phone.like(like),
                        Customer.city.like(like),
                    )
                )
                .order_by(Customer.id.desc())
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, db: AsyncSession, cid: int) -> Optional[Customer]:
        """按主键查客户"""
        return await db.get(Customer, cid)

    async def get_by_phone(self, db: AsyncSession, phone: str) -> Optional[Customer]:
        """按手机号查客户（用于唯一性校验）"""
        result = await db.execute(select(Customer).where(Customer.phone == phone))
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, obj_in: dict) -> Customer:
        """新增客户"""
        return await super().create(db, obj_in)

    async def update(self, db: AsyncSession, cid: int, obj_in: dict) -> Optional[Customer]:
        """按主键部分更新客户，记录不存在返回 None"""
        obj = await self.get_by_id(db, cid)
        if obj is None:
            return None
        return await super().update(db, obj, obj_in)

    async def delete(self, db: AsyncSession, cid: int) -> bool:
        """按主键删除客户，不存在返回 False"""
        obj = await self.get_by_id(db, cid)
        if obj is None:
            return False
        await super().delete(db, obj)
        return True
