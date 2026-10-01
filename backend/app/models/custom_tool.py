"""自定义工具表：工具定义存 MySQL，后端动态加载注册给 Agent。

上游：repositories/tool_repo.py、services/tool_service.py，agent/tools/dynamic_tools.py 读取本表构建 LangChain 工具；
下游：MySQL custom_tools 表。
"""
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CustomTool(Base):
    """
    自定义工具定义表。
    工具类型白名单：
    - builtin: 内置工具（代码中写死的，如 rag_summarize）
    - map_amap: 高德地图工具
    - map_baidu: 百度地图工具
    - python_func: Python 函数工具（有安全风险，需严格约束）
    - http_api: 通用 HTTP API 调用工具
    """
    __tablename__ = "custom_tools"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="工具ID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True, comment="工具名称（英文，作为函数名）")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="工具描述（告诉LLM什么时候用这个工具）")
    tool_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="工具类型：builtin/map_amap/map_baidu/python_func/http_api")
    # 参数 JSON Schema，例如：
    # {"type": "object", "properties": {"city": {"type": "string", "description": "城市名"}}, "required": ["city"]}
    parameters_schema: Mapped[dict] = mapped_column(JSON, nullable=False, comment="参数JSON Schema")
    # 工具配置，不同类型含义不同：
    # map_amap: {"api_endpoint": "geocoding/geo", "extra_params": {...}}
    # map_baidu: {"api_endpoint": "geocoder/v2/", "extra_params": {...}}
    # python_func: {"code": "def run(city): ...", "timeout": 5}
    # http_api: {"url": "https://...", "method": "GET", "headers": {...}}
    config: Mapped[dict] = mapped_column(JSON, nullable=True, comment="工具配置JSON")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, comment="是否启用")
    version: Mapped[int] = mapped_column(default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
