"""
FastAPI 应用入口：
- 创建应用实例、配置 CORS
- 注册全部业务路由
- 启动时建表 + 加载数据库动态工具
- 健康检查与全局异常兜底

【这个文件在整个项目中的位置】
启动命令 `uvicorn app.main:app` 指向的就是本文件的 app 对象。
所有 HTTP 请求都从这里进入，再分发到 app/api/ 下的各个路由。
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.customers import router as customers_router
from app.api.datasets import router as datasets_router
from app.api.memory import router as memory_router
from app.api.tasks import router as tasks_router
from app.api.tools import router as tools_router
from app.database import init_db, AsyncSessionLocal
from app.utils.logger import logger

app = FastAPI(
    title="智扫通智能客服 v2",
    version="2.0.0",
    description="扫地机器人智能客服后端：客户管理 / 流式对话 / 自定义工具 / 数据集问答 / 长期记忆",
)

# CORS：跨域资源共享。浏览器默认禁止前端页面调用"别的域名"的接口，
# 这里开发环境放开全部来源便于前端联调；
# 生产环境必须改为明确的前端域名列表，例如 ["https://your-domain.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册业务路由（统一 /api 前缀，与前端/Nginx 网关约定一致）
app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
app.include_router(chat_router, prefix="/api/chat", tags=["聊天"])
app.include_router(customers_router, prefix="/api/customers", tags=["客户管理"])
app.include_router(tools_router, prefix="/api/tools", tags=["自定义工具"])
app.include_router(datasets_router, prefix="/api/datasets", tags=["数据集"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["异步任务"])
app.include_router(memory_router, prefix="/api/memory", tags=["长期记忆"])


@app.on_event("startup")
async def on_startup() -> None:
    """启动时：建表 + 创建默认管理员 + 加载数据库中的自定义工具到 Agent 注册表"""
    await init_db()
    logger.info("数据库表结构检查完成")

    # 创建默认管理员（如果不存在），用真实 bcrypt 哈希
    try:
        from app.models.user import User
        from app.utils.security import hash_password
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.username == "admin"))
            if result.scalar_one_or_none() is None:
                admin = User(
                    username="admin",
                    hashed_password=hash_password("admin123"),
                    full_name="系统管理员",
                    role="admin",
                )
                db.add(admin)
                await db.commit()
                logger.info("默认管理员 admin/admin123 已创建（请尽快修改密码）")
            else:
                logger.info("默认管理员已存在，跳过创建")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"默认管理员创建失败：{e}")

    # dynamic_tools 由并行模块提供，启动期可能尚未就绪，做容错避免拖垮整个服务
    # 【为什么 try/except 包住？】工具加载失败（比如 MySQL 里数据异常）不应该
    # 让后端起不来——降级为"没有动态工具"，聊天主功能仍可用。
    try:
        from app.agent.tools.dynamic_tools import tool_registry

        await tool_registry.load_from_db()
        logger.info("动态工具注册表加载完成")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"动态工具加载失败（并行模块未就绪可忽略）：{e}")


@app.get("/health", tags=["运维"])
async def health_check() -> dict:
    """健康检查"""
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局未处理异常兜底：记录日志并返回统一 500 结构"""
    logger.exception(f"未处理异常 path={request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误", "data": None},
    )
