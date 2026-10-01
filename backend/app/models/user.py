"""系统用户表：后台管理登录用。

上游：api/auth.py 登录、注册时查询本表；下游：对应 MySQL 的 users 表。

【SQLAlchemy 2.0 新写法速记】
- `Mapped[int]`：声明这个属性对应表里的一列，类型是 int；
- `mapped_column(...)`：描述列的细节（主键/长度/默认值/注释）。
等价于旧版的 `Column(Integer, primary_key=True)`，但带类型提示，IDE 能自动补全。
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """系统用户（管理员/客服坐席）"""
    __tablename__ = "users"

    # primary_key=True 主键；autoincrement=True 自增，插入时不用手动给值
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="用户ID")
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="用户名")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希（bcrypt）")
    full_name: Mapped[str] = mapped_column(String(64), default="", comment="真实姓名")
    role: Mapped[str] = mapped_column(String(32), default="admin", comment="角色：admin/operator")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
