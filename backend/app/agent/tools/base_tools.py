"""
内置工具集：RAG 知识库摘要、客户信息查询等业务内置工具。
- 与 map_tools 同层，供 DynamicToolRegistry 按 name 反射查找。

【小白科普：@tool 装饰器是干什么的？】
@tool 是 LangChain 提供的装饰器，加在一个普通函数上，就把它变成
"大模型可以调用的工具"：函数的 docstring 会被当成工具说明书给大模型看，
大模型据此决定什么时候调用、传什么参数。所以 docstring 一定要写清楚！
"""
from langchain_core.tools import tool
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.utils.logger import logger


# RAG 服务单例延迟导入：rag_service 模块可能尚未初始化向量库，
# 这里用 try/except 包住，避免启动期 import 失败拖垮整个 Agent。
# 【为什么不在文件顶部直接 import？】这叫"延迟导入"——用到时才 import，
# 既避免循环依赖，又能在 RAG 模块出问题时优雅降级而不是启动崩溃。
def _get_rag_service():
    """惰性获取 RAG 服务单例；未初始化或异常时返回 None。"""
    try:
        from app.rag.rag_service import get_rag_service  # 延迟导入
        svc = get_rag_service()
        if svc is None:
            return None
        return svc
    except Exception as e:  # noqa: BLE001
        logger.warning(f"RAG 服务不可用：{e}")
        return None


@tool
async def rag_summarize(query: str) -> str:
    """从企业知识库中检索与问题相关的文档片段，并由大模型生成摘要回答。

    参数:
        query: 用户问题或检索关键词
    """
    svc = _get_rag_service()
    if svc is None:
        return "知识库暂不可用。"

    try:
        # 调用 RAG 服务单例的 rag_summarize 方法
        result = await svc.rag_summarize(query)
        return result if isinstance(result, str) else str(result)
    except Exception as e:  # noqa: BLE001
        logger.exception("RAG 摘要调用失败")
        return f"知识库检索失败：{e}"


@tool
async def get_customer_info(customer_id: int) -> str:
    """根据客户ID查询客户档案信息（姓名、手机号、城市、地址、会员等级、购买型号等）。

    参数:
        customer_id: 客户主键 ID
    """
    try:
        # 工具调用不在 FastAPI 请求作用域内，手动开一个 session
        # async with：用完自动关闭 session，防止数据库连接泄漏
        async with AsyncSessionLocal() as db:
            stmt = select(Customer).where(Customer.id == customer_id)
            result = await db.execute(stmt)
            cust = result.scalar_one_or_none()
    except Exception as e:  # noqa: BLE001
        # 【为什么返回错误字符串而不是抛异常？】工具抛异常会中断 Agent 的
        # 思考循环；返回错误描述，大模型能"看到失败"并换种方式回答用户。
        logger.exception(f"查询客户信息失败 id={customer_id}")
        return f"客户信息查询失败：{e}"

    if cust is None:
        return f"未找到客户ID={customer_id} 的档案。"

    purchase_date = cust.purchase_date.strftime("%Y-%m-%d") if cust.purchase_date else "未知"
    return (
        f"客户档案：\n"
        f"- ID：{cust.id}\n"
        f"- 姓名：{cust.name}\n"
        f"- 手机号：{cust.phone}\n"
        f"- 城市：{cust.city}\n"
        f"- 地址：{cust.address}\n"
        f"- 会员等级：{cust.member_level}\n"
        f"- 产品型号：{cust.product_model}\n"
        f"- 购买日期：{purchase_date}\n"
        f"- 备注：{cust.remark or '无'}"
    )


__all__ = ["rag_summarize", "get_customer_info"]
