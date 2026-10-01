"""
应用配置管理
============
【这个文件是干什么的】
使用 pydantic-settings 从环境变量 / .env 文件读取配置，
所有模块统一 `from app.config import settings` 取配置，禁止散落各处硬编码。

【好处】改配置不用改代码：本地开发、Docker、生产环境各用一份 .env 即可；
字段类型自动校验（比如端口必须是整数），写错会在启动时立刻报错。
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus  # 连接串里的用户名/密码需要 URL 编码

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_project_root() -> Path:
    """推断项目根目录。

    【★ 为什么不能简单地上溯三级？★】
    两种运行布局下，本文件的层级深度是不一样的：

      宿主机：<root>/backend/app/config.py   → 上溯三级 = <root>   ✅
      容器内：/app/app/config.py             → 上溯三级 = "/"      ❌ 越界
              （Dockerfile 用 `COPY app/ ./app/`，容器里没有 backend/ 这一层）

    越界的后果是 chroma_persist_dir / UPLOAD_DIR / LOG_DIR 全部指向容器根目录：
      /data/chroma_db（未挂载）→ 向量库不落盘，容器一重建知识库全丢
      /data/uploads            → 上传的 CSV 不落盘
      /logs                    → 日志不落盘，宿主机 logs/ 目录永远为空

    所以先判断上溯三级是不是真正的项目根（含 docker-compose.yml 或 backend/），
    不是则回退到上溯两级（即容器内的 /app）。
    """
    here = Path(__file__).resolve()
    candidate = here.parent.parent.parent
    if (candidate / "docker-compose.yml").exists() or (candidate / "backend").is_dir():
        return candidate
    return here.parent.parent  # 容器内：/app/app/config.py -> /app


PROJECT_ROOT = _detect_project_root()


class Settings(BaseSettings):
    """全局配置，字段名与 .env 中的变量名一一对应（不区分大小写）"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中未定义的字段
    )

    # ---------- 应用 ----------
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    log_level: str = "INFO"

    # ---------- MySQL ----------
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "smart_agent_v2"

    # ---------- Redis（缓存 / 限流计数 / Celery 消息队列）----------
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # ---------- 大模型（阿里通义千问 DashScope）----------
    dashscope_api_key: str = ""           # 必填！不填聊天/向量功能不可用
    chat_model_name: str = "qwen3-max"
    embedding_model_name: str = "text-embedding-v4"

    # ---------- 高德地图（地理编码/天气/周边搜索工具用）----------
    amap_key: str = ""
    amap_security_code: str = ""

    # ---------- 百度地图（可选备用）----------
    baidu_map_ak: str = ""
    baidu_map_sk: str = ""

    # ---------- JWT（登录令牌；生产环境必须改 jwt_secret_key！）----------
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    # ---------- 向量库 ----------
    chroma_persist_dir: str = "./data/chroma_db"
    chroma_collection: str = "agent_knowledge"

    # ---------- Celery ----------
    # 【★ 为什么默认留空、而不是写死 redis://127.0.0.1:6379/1？★】
    # 容器里的 127.0.0.1 指向容器"自己"，而 Redis 跑在另一个容器里，
    # 所以写死 127.0.0.1 会导致 Celery 启动即报：
    #     consumer: Cannot connect to redis://127.0.0.1:6379/1: Connection refused
    # 留空后，由下面的 _derive_celery_urls 自动按 REDIS_HOST/REDIS_PORT 推导，
    # 容器内会得到 redis://redis:6379/1，本机开发则得到 redis://127.0.0.1:6379/1。
    # 需要自定义时，在 .env 里显式写 CELERY_BROKER_URL / CELERY_RESULT_BACKEND 即可。
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ---------- 业务参数 ----------
    memory_recent_window: int = 10          # 短期记忆取最近N轮
    memory_top_k: int = 5                   # 长期记忆召回条数
    memory_similarity_threshold: float = 0.7  # 长期记忆相似度阈值
    text2sql_confidence_threshold: float = 0.6  # Text2SQL置信度阈值
    rag_top_k: int = 3                      # RAG召回条数

    @property
    def async_database_url(self) -> str:
        """异步 SQLAlchemy 连接串（aiomysql 驱动）
        @property 让这个"方法"用起来像普通属性：settings.async_database_url
        不用加括号，每次访问时现场拼出连接串。

        【★ 为什么用户名/密码必须 quote_plus 编码？★】
        连接串是"URL 格式"，其中 @ : / ? # 等字符有特殊含义。
        如果密码里含 @（例如 REPLACED_MYSQL_PASSWORD），不编码就会拼成：
            mysql+aiomysql://root:REPLACED_MYSQL_PASSWORD@mysql:3306/db
        解析器会把第一个 @ 当作用户名与主机的分隔符，
        于是主机名被错认成 "@mysql"，报错：
            Can't connect to MySQL server on '@mysql'
        quote_plus 会把 @ 转义成 %40，从根上避免这类问题。
        """
        return (
            f"mysql+aiomysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        """同步 SQLAlchemy 连接串（Alembic 迁移 / 初始化用）。
        用户名/密码同样需要编码，原因见 async_database_url 的说明。"""
        return (
            f"mysql+pymysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """Redis 连接串。密码同样做编码，避免特殊字符破坏 URL 结构。"""
        auth = f":{quote_plus(self.redis_password)}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @field_validator("chroma_persist_dir")
    @classmethod
    def resolve_chroma_dir(cls, v: str) -> str:
        """字段校验器：配置加载时自动对 chroma_persist_dir 做一次加工——
        将相对路径解析为基于项目根的绝对路径（防止因工作目录不同而写错位置）"""
        p = Path(v)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return str(p)

    @model_validator(mode="after")
    def _derive_celery_urls(self) -> "Settings":
        """Celery 的 broker/结果库地址留空时，自动按 Redis 配置推导。

        【为什么需要这一步？】
        docker-compose 只给容器注入了 REDIS_HOST=redis / REDIS_PORT=6379，
        并没有注入 CELERY_BROKER_URL。若这两个字段写死默认值 127.0.0.1，
        容器里的 Celery 就会连自己的 127.0.0.1 而失败：
            Cannot connect to redis://127.0.0.1:6379/1: Connection refused
        这里用 model_validator(mode="after")：等所有字段都从环境变量/.env
        读完之后再统一兜底，既尊重用户显式配置，又能自动适配容器网络。
        """
        auth = f":{quote_plus(self.redis_password)}@" if self.redis_password else ""
        base = f"redis://{auth}{self.redis_host}:{self.redis_port}"
        if not self.celery_broker_url:
            self.celery_broker_url = f"{base}/1"        # 任务队列用 db1
        if not self.celery_result_backend:
            self.celery_result_backend = f"{base}/2"    # 任务结果用 db2
        return self


# @lru_cache：给函数加"记忆"，同样的调用直接返回上次结果，
# 保证 Settings 全局只被读取/创建一次（单例效果）
@lru_cache
def get_settings() -> Settings:
    """单例获取配置（带缓存，避免重复读 .env）"""
    return Settings()


settings = get_settings()
