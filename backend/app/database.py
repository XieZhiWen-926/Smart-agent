"""
数据库异步会话管理
==================
【这个文件是干什么的】
- 创建 SQLAlchemy 2.0 异步引擎（aiomysql 驱动）与连接池；
- 提供 get_db 依赖注入：每个请求一个 session，请求结束自动关闭；
- 定义所有 ORM 模型的基类 Base；
- 连接池参数针对高并发调优。

【和哪些文件联动】
被所有 repositories / services 使用；main.py 启动时调用 init_db() 建表。
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# ---------- 异步引擎（带连接池）----------
# 【为什么用连接池？】每来一次请求就新建 TCP 连接非常慢；池子提前建好一批
# 连接反复复用。参数含义：
# pool_size: 常驻连接数
# max_overflow: 峰值时可额外创建的连接数（20+30=最多 50 个并发连接）
# pool_recycle: 连接回收秒数（MySQL 默认 wait_timeout=28800，设小于它避免断连）
# pool_timeout: 获取连接等待秒数
# echo: 是否打印SQL（开发时可开）
engine = create_async_engine(
    settings.async_database_url,
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600,
    pool_timeout=30,
    pool_pre_ping=True,   # 取连接前先 ping，防止使用已断开的连接
    echo=False,
)

# ---------- 异步会话工厂 ----------
# expire_on_commit=False：提交后不使对象过期，避免在异步上下文外访问属性报错
# autoflush=False：不自动 flush，写操作显式 commit 时才落库，行为更可控
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类（models/ 下的每张表都继承它）"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入：每个请求获取一个独立的 DB session。

    【小白科普】带 yield 的函数是"生成器"。FastAPI 的依赖注入约定：
    yield 之前是"进入请求"的准备，yield 之后是"请求结束"的收尾——
    所以 try/finally 能确保无论请求成功还是异常，session 都会被关闭。
    这在 SSE 流式响应中尤其重要：不能在流还没结束时就关闭 session。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()  # 出错回滚：已做的修改全部撤销
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    开发环境一键建表（生产环境应使用 Alembic 迁移）。
    导入所有模型后调用 Base.metadata.create_all。
    """
    # 在这里导入所有模型，确保 metadata 被注册
    from app.models import (  # noqa: F401
        customer, custom_tool, conversation, memory, dataset, user, async_task
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
