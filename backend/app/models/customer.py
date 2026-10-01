"""客户信息表：扫地机器人售后客户档案。

上游：repositories/customer_repo.py 读写本表，services/customer_service.py 做业务校验；
下游：MySQL customers 表。会话(conversations)、长期记忆(long_term_memories) 通过 customer_id 关联本表。
"""
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    """客户表：存储扫地机器人客户的基本信息"""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="客户ID")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="客户姓名")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True, comment="手机号")
    city: Mapped[str] = mapped_column(String(64), default="", comment="所在城市")
    address: Mapped[str] = mapped_column(String(255), default="", comment="详细地址")
    longitude: Mapped[float] = mapped_column(Float, nullable=True, comment="地址经度（高德坐标系）")
    latitude: Mapped[float] = mapped_column(Float, nullable=True, comment="地址纬度（高德坐标系）")
    member_level: Mapped[str] = mapped_column(String(32), default="普通", comment="会员等级：普通/银卡/金卡/钻石")
    product_model: Mapped[str] = mapped_column(String(64), default="", comment="购买的扫地机器人型号")
    purchase_date: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="购买日期")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")
    # default=datetime.utcnow：插入新行时自动填当前时间（注意传的是函数本身，不加括号）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    # onupdate=...：每次 UPDATE 这行时自动刷新为当前时间
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
