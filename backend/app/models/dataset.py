"""数据集表：CSV 上传后的元数据与列映射。

上游：repositories/dataset_repo.py、services/dataset_service.py（CSV 导入）、services/data_router.py（语义匹配选数据集）；
下游：MySQL datasets 表（元数据）+ 每个数据集一张动态生成的物理数据表。
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Dataset(Base):
    """
    数据集元数据表。
    每个上传的 CSV 对应一条记录，实际数据写入一张物理表（table_name 字段记录）。
    """
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="数据集ID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="数据集名称")
    description: Mapped[str] = mapped_column(Text, default="", comment="数据集描述（用于语义匹配）")
    table_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="实际存储的MySQL表名（英文合规名）")
    source_file: Mapped[str] = mapped_column(String(255), default="", comment="原始CSV文件名")
    row_count: Mapped[int] = mapped_column(Integer, default=0, comment="数据行数")
    column_count: Mapped[int] = mapped_column(Integer, default=0, comment="列数")
    # 列元数据：[{"physical_name": "col_1", "original_name": "用户ID", "dtype": "string", "description": ""}, ...]
    columns_meta: Mapped[list] = mapped_column(JSON, nullable=False, comment="列元数据（含中文列名映射）")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, comment="状态：pending/processing/completed/failed")
    error_msg: Mapped[str] = mapped_column(Text, default="", comment="失败原因")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True, comment="上传者用户ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
