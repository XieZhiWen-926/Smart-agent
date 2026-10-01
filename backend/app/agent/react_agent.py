"""
ReAct 智能体核心（本项目的"大脑"）
=====================================================================
【这个文件是干什么的】
接收用户一句大白话提问，驱动 LangChain Agent 循环
"思考 -> 选工具 -> 执行工具 -> 观察结果 -> 组织回答"（这就是 ReAct 模式），
并以流式（打字机）方式把回答一段一段吐给前端。

【关键设计决策】
- 【为什么每次请求都 new 一个 SmartAgent？】
  因为本类不持有任何跨请求的可变状态（每次都重新 build），
  多请求并发时互不干扰，用完即丢，简单安全。
- 【为什么模型/记忆管理器做成模块级单例？】
  chat_model / embed_model / memory_manager 是"重对象"（底层是网络连接），
  全局只建一次，避免每个请求都重建连接，见 app/model/factory.py。
- 长期记忆在每轮收到 query 后实时召回，注入 system prompt；
- 使用 LangChain 新版 create_agent（中间件风格），不用旧 initialize_agent。

【和哪些文件联动】
- 上游调用方：app/services/chat_service.py（先 build(db) 再 execute_stream(...)）
- 工具来源：app/agent/tools/dynamic_tools.py 的 tool_registry
- 记忆读写：app/agent/memory/long_term_memory.py 的 memory_manager
- 观测日志：app/agent/tools/middleware.py 的两个中间件
"""
import asyncio
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.model.factory import get_chat_model
from app.models.customer import Customer
from app.agent.memory.long_term_memory import memory_manager
from app.repositories.conversation_repo import ConversationRepository
from app.utils.logger import logger

# 新版 agent 构造入口（langchain 0.3.21+ / 中间件风格）
from langchain.agents import create_agent  # noqa: E402
# AIMessageChunk：流式输出时大模型返回的"文本增量"消息类型，
# 用于在 stream_mode="messages" 下过滤出真正的回答内容
from langchain_core.messages import AIMessageChunk  # noqa: E402

# ---- 工具注册表与观测中间件：由兄弟模块提供，缺失时优雅降级为空 ----
try:
    from app.agent.tools.dynamic_tools import tool_registry  # type: ignore
except ImportError:  # pragma: no cover - 工具模块尚未就绪时先空跑
    logger.warning("[agent] 未找到 app.agent.tools.dynamic_tools.tool_registry，工具列表为空")
    tool_registry = []

try:
    from app.agent.tools.middleware import monitor_tool, log_before_model  # type: ignore
except ImportError:  # pragma: no cover
    logger.warning("[agent] 未找到观测中间件 monitor_tool/log_before_model，使用空中间件")
    monitor_tool = None
    log_before_model = None


_BASE_ROLE = "你是智扫通扫地机器人智能客服"

# 后台任务引用集合（修复说明见 execute_stream 第 6 步）：
# asyncio.create_task 创建的任务如果只"点火不管"（不保存返回值），
# Python 的垃圾回收可能在任务跑完前就把 Task 对象回收掉，导致任务被悄悄取消。
# 所以把任务放进这个集合里"按住"，跑完后通过回调自动移除。
_BACKGROUND_TASKS: set[asyncio.Task] = set()


class SmartAgent:
    """
    轻量智能体：每请求一个实例。
    注意：本类不持有任何跨请求可变状态，重模型走单例，因此可以放心地
    "build 一次、执行一次、丢弃"。
    """

    def __init__(self, customer_id: int, conversation_id: Optional[int] = None):
        self.customer_id = customer_id
        self.conversation_id = conversation_id

        # 构建产物（build 后填充）
        self.agent = None
        self.customer: Optional[Customer] = None
        self.recent_messages: list[dict] = []
        self.tools: list = []
        self._assembled: bool = False

    # ------------------------------------------------------------------ #
    async def build(self, db: AsyncSession) -> "SmartAgent":
        """
        异步构建：
        1. 加载客户基本信息；
        2. 加载最近 N 轮短期上下文；
        3. 取工具列表；
        4. 创建 LangChain 新版 agent（轻量编译，不带记忆——记忆在运行时注入）。
        """
        # 1) 客户信息
        self.customer = await db.get(Customer, self.customer_id)

        # 2) 短期对话窗口
        if self.conversation_id:
            self.recent_messages = await memory_manager.get_recent_messages(
                db, self.conversation_id
            )

        # 3) 工具列表：DynamicToolRegistry 提供 get_tools() 方法
        if hasattr(tool_registry, "get_tools") and callable(getattr(tool_registry, "get_tools")):
            self.tools = tool_registry.get_tools()
        elif hasattr(tool_registry, "tools"):
            self.tools = list(tool_registry.tools)
        else:
            self.tools = list(tool_registry or [])

        # 4) 组装中间件（去掉 None——上面 try/except 降级时中间件可能是 None）
        middleware = [m for m in (monitor_tool, log_before_model) if m is not None]

        # 5) 用新版 create_agent 构建（model/tool 单例，不传旧 executor）
        self.agent = create_agent(
            model=get_chat_model(),
            tools=self.tools,
            middleware=middleware,
        )
        self._assembled = True
        logger.info(
            f"[agent] build完成 customer={self.customer_id} "
            f"conv={self.conversation_id} tools={len(self.tools)} "
            f"recent_msgs={len(self.recent_messages)}"
        )
        return self

    # ------------------------------------------------------------------ #
    def _build_system_prompt(self, memories: list[str]) -> str:
        """组装 system prompt：角色 + 客户信息 + 长期记忆注入"""
        # 客户基本信息
        if self.customer is not None:
            c = self.customer
            customer_line = (
                f"客户信息：姓名={c.name}，城市={c.city}，"
                f"会员等级={c.member_level}，设备型号={c.product_model or '未知'}。"
            )
        else:
            customer_line = "客户信息：暂无档案。"

        # 长期记忆注入（明确告知模型不要提及记忆来源）
        if memories:
            mem_block = "以下是该客户的历史记忆（仅供参考，不要主动提及记忆来源）：\n" + "\n".join(
                f"- {m}" for m in memories
            )
        else:
            mem_block = "以下是该客户的历史记忆（仅供参考，不要主动提及记忆来源）：\n（暂无）"

        return (
            f"{_BASE_ROLE}。{customer_line}\n"
            "回答要简洁、专业，涉及订单/设备问题时优先调用工具核实，不要编造。\n"
            "【工具使用铁律】\n"
            "1) 只要调用了 rag_summarize，就必须以它的返回为准。"
            "若它返回“根据现有知识库未找到相关信息”，必须如实告知用户"
            "“知识库中没有查到相关内容”，绝对不允许再用你自己的知识补全细节。\n"
            "2) 调用 rag_summarize 时，query 直接用用户的原话关键词，"
            "不要自行添加型号、品牌等用户没提到的限定词。\n"
            "3) 调用 amap_around_search 前，必须先调用 amap_geocode 把地名转成经纬度，"
            "并把该经纬度作为 location 传入；不要自己编造坐标。\n"
            f"{mem_block}"
        )

    # ------------------------------------------------------------------ #
    async def execute_stream(
        self,
        query: str,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """
        流式执行：逐段 yield 助手回复文本。

        【小白科普：什么是 async generator（异步生成器）？】
        带 yield 的 async 函数就是异步生成器。它不会一次性返回完整结果，
        而是每 yield 一次就把一小段文本"递"给调用方，然后自己暂停。
        前端因此能像看打字机一样逐字看到回答，而不用等全部生成完。

        SSE / DB session 注意事项（重要）：
        - 本生成器是 SSE 响应的源头，调用方（chat_service / 路由）必须保证
          传入的 db session 在整个生成器耗尽之前不要 close()；
          若用 FastAPI 依赖注入 get_db，需让依赖的生命周期覆盖整个流式响应。
        - 用户消息在流开始前落库，助手消息在流结束后落库；
          中途异常也要保证 session 回滚，不能让连接泄漏。
        - 记忆抽取用 asyncio.create_task 后台跑，且必须自建独立 session
          （本请求的 db 在 SSE 结束后可能被关闭，不能跨协程复用）。
        """
        if not self._assembled:
            raise RuntimeError("SmartAgent 尚未 build，请先 await agent.build(db)")

        # 1) 保存用户消息
        if self.conversation_id:
            await ConversationRepository.add_message(
                db, self.conversation_id, "user", query
            )
            await db.commit()

        # 2) 召回长期记忆（带 query，按相似度*importance）
        # 【为什么 try/except？】记忆召回依赖 embedding 服务，它挂了不应该
        # 让聊天主流程崩溃——降级为"没有记忆"继续回答即可。
        try:
            memories = await memory_manager.retrieve_relevant(
                db, self.customer_id, query
            )
        except Exception as e:
            logger.warning(f"[agent] 长期记忆召回失败，降级为空: {e}")
            memories = []

        # 3) 组装 system prompt + 用户输入
        system_prompt = self._build_system_prompt(memories)
        input_dict = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ]
        }

        # 4) 流式执行，逐段累积助手文本
        collected: list[str] = []
        try:
            # 【★ 为什么必须用 stream_mode="messages"？★】
            # 这里踩过一个很隐蔽的坑，改代码前务必看懂：
            #
            #   stream_mode="values"  —— 每跑完一个"图节点"就返回一次「全量状态」。
            #       也就是说，要等模型把整段话都生成完，才吐出来一次。
            #       结果是：分片数通常只有 1~3 个，全部在同一毫秒到达，
            #       前端看到的不是"打字机"，而是"憋半天一次性蹦出一大段"。
            #       而且这个全量状态里包含 HumanMessage（用户提问）和
            #       ToolMessage（工具结果），做 diff 时很容易把用户的问题、
            #       知识库原文一起混进回答里。
            #
            #   stream_mode="messages" —— 大模型每生成一个 token 就吐一次，
            #       返回 (消息增量, 元数据) 二元组。这才是"打字机效果"的来源。
            #
            # 另外用 metadata["langgraph_node"] == "model" 做过滤：
            # 本项目 rag_summarize 工具内部会再调一次大模型，若不按节点过滤，
            # 那次内部调用的输出也会被一并推给用户，造成答案重复/串味。
            async for chunk, metadata in self.agent.astream(
                input_dict, stream_mode="messages"
            ):
                node = (metadata or {}).get("langgraph_node")
                # 只保留主模型节点（create_agent 里该节点名为 "model"）的输出；
                # node 取不到时（老版本无该字段）不做过滤，保证兼容性
                if node is not None and node != "model":
                    continue
                # 只取 AI 文本增量：工具调用增量（tool_calls）的 content 是空的，
                # 会被下面的 content 判空自然过滤掉
                if not isinstance(chunk, AIMessageChunk):
                    continue
                content = chunk.content
                if isinstance(content, str) and content:
                    collected.append(content)
                    yield content
        except Exception as e:
            logger.exception(f"[agent] 流式执行异常: {e}")
            raise

        # 5) 流结束：保存助手消息
        assistant_text = "".join(collected).strip()
        if self.conversation_id and assistant_text:
            await ConversationRepository.add_message(
                db, self.conversation_id, "assistant", assistant_text
            )
            await db.commit()

        # 6) 后台异步触发记忆抽取（不阻塞响应）
        if self.conversation_id and assistant_text:
            # 【bug 修复】原代码 asyncio.create_task(...) 的返回值直接被丢弃：
            # 没有地方持有 Task 引用时，Python GC 可能在任务完成前回收它，
            # 导致记忆抽取被静默取消。这里把任务存进模块级集合，
            # 并用 done_callback 在完成后自动移除，防止集合无限增大。
            task = asyncio.create_task(
                self._background_extract(self.customer_id, self.conversation_id)
            )
            _BACKGROUND_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_TASKS.discard)

    # ------------------------------------------------------------------ #
    @staticmethod
    async def _background_extract(customer_id: int, conversation_id: int) -> None:
        """
        后台记忆抽取：必须自建独立 DB session。
        请求级 db session 在 SSE 响应结束后会被关闭，不能跨协程复用。
        任何异常只记日志，绝不影响用户已收到的响应。
        """
        from app.database import AsyncSessionLocal  # 延迟导入避免循环依赖

        try:
            async with AsyncSessionLocal() as db:
                recent = await memory_manager.get_recent_messages(db, conversation_id)
                # 只抽最近 window 内的 user/assistant 对，避免重复抽取
                await memory_manager.extract_and_store(db, customer_id, recent)
        except Exception as e:
            logger.warning(f"[agent] 后台记忆抽取失败 customer={customer_id}: {e}")
