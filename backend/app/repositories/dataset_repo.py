"""
数据集 Repository 层
=====================
封装对 datasets 表的所有数据库操作，Service 层只调用这里，不直接写 SQL。

上游：services/dataset_service.py、services/data_router.py；下游：models/dataset.py。
注意本类方法只 flush 不 commit，事务提交由外层（service/Celery 任务）控制。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset


class DatasetRepository:
    """数据集 ORM 操作封装"""

    @staticmethod
    async def get_all(db: AsyncSession, status: Optional[str] = None) -> list[Dataset]:
        """
        查询全部数据集，可按状态过滤。

        :param db: 异步数据库会话
        :param status: 可选状态过滤（pending/processing/completed/failed）
        :return: Dataset 列表
        """
        stmt = select(Dataset).order_by(Dataset.created_at.desc())
        if status:
            stmt = stmt.where(Dataset.status == status)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, dataset_id: int) -> Optional[Dataset]:
        """按主键 ID 查询数据集"""
        return await db.get(Dataset, dataset_id)

    @staticmethod
    async def get_by_table_name(db: AsyncSession, table_name: str) -> Optional[Dataset]:
        """按物理表名查询数据集"""
        stmt = select(Dataset).where(Dataset.table_name == table_name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, obj_in: dict) -> Dataset:
        """
        创建一条数据集记录。

        :param obj_in: 字段字典，如 {"name": ..., "table_name": ..., ...}
        :return: 新建的 Dataset 对象
        """
        obj = Dataset(**obj_in)
        db.add(obj)
        await db.flush()          # 拿到自增 id
        await db.refresh(obj)
        return obj

    @staticmethod
    async def update_status(
        db: AsyncSession,
        dataset_id: int,
        status: str,
        error_msg: Optional[str] = None,
    ) -> Optional[Dataset]:
        """
        更新数据集状态（Celery 任务进度回调用）。

        :param status: pending/processing/completed/failed
        :param error_msg: 失败时的错误信息
        """
        obj = await db.get(Dataset, dataset_id)
        if not obj:
            return None
        obj.status = status
        if error_msg is not None:
            obj.error_msg = error_msg
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def update(db: AsyncSession, dataset_id: int, **kwargs) -> Optional[Dataset]:
        """
        通用字段更新。

        :param kwargs: 要更新的字段，如 row_count=100, columns_meta=[...]
        """
        obj = await db.get(Dataset, dataset_id)
        if not obj:
            return None
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def delete(db: AsyncSession, dataset_id: int) -> bool:
        """删除数据集元数据记录（物理表的 DROP 由 Service 层负责）"""
        obj = await db.get(Dataset, dataset_id)
        if not obj:
            return False
        await db.delete(obj)
        await db.flush()
        return True
