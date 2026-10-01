"""
基础 Repository：封装通用的 ORM CRUD 模板方法。
- 所有具体 Repository 继承本类，聚焦自己特有的查询。
- 统一提交/刷新策略，避免业务层散落 commit。
"""
from typing import Any, Generic, Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

# 泛型类型占位：bound=Base 表示 ModelType 只能是 Base 的 ORM 子类，
# 这样 BaseRepository[Customer] 里的返回值就自动是 Customer 类型，IDE 有提示。
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """泛型基础仓储，子类传入具体 ORM 模型即可获得通用方法"""

    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, obj_id: Any) -> Optional[ModelType]:
        """按主键查询单条记录"""
        return await db.get(self.model, obj_id)

    async def create(self, db: AsyncSession, obj_in: dict[str, Any]) -> ModelType:
        """新增记录并提交，返回带主键的对象"""
        obj = self.model(**obj_in)   # **obj_in 把字典展开成关键字参数，等价于 Model(name=..., phone=...)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)        # refresh：重新从库里读一遍，拿到自增 id 和数据库默认值
        return obj

    async def update(self, db: AsyncSession, obj: ModelType, obj_in: dict[str, Any]) -> ModelType:
        """对已查出的对象做部分字段更新并提交"""
        for field, value in obj_in.items():
            setattr(obj, field, value)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def delete(self, db: AsyncSession, obj: ModelType) -> None:
        """删除指定对象并提交"""
        await db.delete(obj)
        await db.commit()
