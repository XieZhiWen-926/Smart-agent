"""
工具数据访问层（Repository）：封装对 custom_tools 表的所有 SQL 操作。
- SQLAlchemy 2.0 异步风格：select() / await db.execute()
- 不写业务规则，只做 CRUD；业务校验在 service 层（services/tool_service.py）。
"""
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_tool import CustomTool


class ToolRepository:
    """custom_tools 表的数据访问对象"""

    @staticmethod
    async def get_all(db: AsyncSession, enabled_only: bool = False) -> list[CustomTool]:
        """查询全部工具；enabled_only=True 时只返回启用的。"""
        stmt = select(CustomTool).order_by(CustomTool.id.desc())
        if enabled_only:
            stmt = stmt.where(CustomTool.is_enabled.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, tool_id: int) -> Optional[CustomTool]:
        """按主键查询单个工具"""
        stmt = select(CustomTool).where(CustomTool.id == tool_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(db: AsyncSession, name: str) -> Optional[CustomTool]:
        """按工具名查询（用于创建/更新时的唯一性校验）"""
        stmt = select(CustomTool).where(CustomTool.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, obj_in: dict[str, Any]) -> CustomTool:
        """插入一条新工具记录，obj_in 为字段字典"""
        obj = CustomTool(**obj_in)
        db.add(obj)
        await db.flush()          # 拿到自增 id，但不 commit（事务由外层控制）
        await db.refresh(obj)
        return obj

    @staticmethod
    async def update(db: AsyncSession, tool_id: int, obj_in: dict[str, Any]) -> Optional[CustomTool]:
        """按主键部分更新；只更新 obj_in 中显式传入的字段。"""
        obj = await ToolRepository.get_by_id(db, tool_id)
        if obj is None:
            return None
        for k, v in obj_in.items():
            if v is not None and hasattr(obj, k):
                setattr(obj, k, v)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def delete(db: AsyncSession, tool_id: int) -> bool:
        """按主键删除；返回是否真的删到了行。"""
        obj = await ToolRepository.get_by_id(db, tool_id)
        if obj is None:
            return False
        await db.delete(obj)
        await db.flush()
        return True


__all__ = ["ToolRepository"]
