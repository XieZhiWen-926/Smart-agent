"""异步任务表：Celery 后台任务的状态追踪。

上游：api/datasets.py 上传时写入记录、api/tasks.py 供前端轮询、tasks/ 里的 Celery worker 回写进度；
下游：MySQL async_tasks 表。
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AsyncTask(Base):
    """
    异步任务状态表。
    用于前端轮询 CSV 入库、向量化、报告生成等耗时任务的进度。
    """
    __tablename__ = "async_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="任务ID")
    task_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True, comment="Celery任务ID")
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="任务类型：csv_import/vectorize/report")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, comment="状态：pending/processing/completed/failed")
    progress: Mapped[int] = mapped_column(default=0, comment="进度百分比0-100")
    result: Mapped[dict] = mapped_column(JSON, nullable=True, comment="任务结果")
    error_msg: Mapped[str] = mapped_column(Text, default="", comment="失败原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
