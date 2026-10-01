"""ORM 模型层（分层架构最底层）：用 Python 类描述 MySQL 表结构。

【什么是 ORM】ORM（对象关系映射）让我们用 Python 类操作数据库：
一个类 = 一张表，一个对象 = 一行数据，属性 = 列。
这样业务代码就不用拼 SQL 字符串，由 SQLAlchemy 自动生成。

【在分层中的位置】
    api(路由) -> services(业务) -> repositories(数据访问) -> models(本层) -> MySQL
本层只定义"表长什么样"，不写任何查询逻辑；
查询统一放在 repositories 层，业务规则放在 services 层。

【本文件作用】把所有模型类汇总导出。init_db 建表时只需 import 本文件，
SQLAlchemy 就能通过 Base.metadata 找到所有表定义。
"""
from app.database import Base
from app.models.customer import Customer
from app.models.custom_tool import CustomTool
from app.models.conversation import Conversation, Message
from app.models.memory import LongTermMemory
from app.models.dataset import Dataset
from app.models.user import User
from app.models.async_task import AsyncTask

__all__ = [
    "Base",
    "Customer",
    "CustomTool",
    "Conversation",
    "Message",
    "LongTermMemory",
    "Dataset",
    "User",
    "AsyncTask",
]
