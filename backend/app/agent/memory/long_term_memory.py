"""
长期记忆系统核心（模块B）
=====================================================================

【为什么自己造长期记忆，而不是用 LangGraph Store？】
LangGraph 里有两个容易混淆的概念，先讲清楚边界：

1. Checkpointer（线程内 / 单次运行的短期状态）
   - 作用对象：一个 thread_id 对应的"当前这轮对话"中间状态
   - 生命周期：跟一次 agent 执行绑定，用来断点续跑、恢复工具调用栈
   - 特点：线程内、临时、面向"图执行状态机"，不跨会话做客户画像

2. Store（跨线程的长期记忆）
   - LangGraph 的 BaseStore 确实支持跨 thread 存命名空间记忆，
     但它的语义是"键值 + 可选向量"，和我们要做的
     "客户级事实/偏好画像 + 重要性加权召回"不是一回事。

本项目的选择：
- 以 MySQL（long_term_memories 表）作为唯一事实源；
- 召回发生在"单个客户自己的记忆集合"内，用 Python 端算余弦相似度，
  不依赖 LangGraph Store，也不依赖 checkpointer；
- checkpointer 只负责单次 agent 运行的短期状态，长期画像一律走这里。

【为什么把 embedding 存在 MySQL JSON 里、在 Python 端算余弦？】
- 单客户记忆量有界（几十~几百条），全量取出后 numpy/纯 Python 余弦足够快；
- 省掉一套向量库基础设施，MVP 阶段最稳。

【高规模升级路径（写在这里备查）】
- 第一步：MySQL 9 的 VECTOR 类型 + 距离函数，把余弦下推到 SQL；
- 第二步：记忆量涨到十万级以上，迁到 Milvus / pgvector / Chroma，
  按 customer_id 做分区/命名空间，召回走 ANN 索引；
- 本类的 retrieve_relevant 是唯一召回入口，换底层只改这一处。
"""
import json
import math
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.model.factory import get_chat_model, get_embed_model
from app.models.conversation import Message
from app.models.memory import LongTermMemory
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.memory_repo import MemoryRepository
from app.utils.logger import logger


# 记忆抽取的 Prompt：强约束模型只输出 JSON，不允许废话
_EXTRACT_PROMPT_TEMPLATE = """你是一个客户画像抽取器。下面是某扫地机器人客户与客服的最近对话。
请从中抽取关于该客户的【事实】和【偏好】，只输出 JSON，不要输出任何解释或 markdown。

输出格式必须严格为：
{{"facts": ["事实1", "事实2"], "preferences": ["偏好1", "偏好2"]}}

字段说明：
- facts：客观事实，如购买型号、住址城市、设备故障、订单情况
- preferences：主观偏好，如喜欢简洁回答、偏好电话回访、在意价格

如果没有可抽取内容，对应列表留空 []。每条记忆用一句简短陈述句表达。

最近对话：
{transcript}
"""

# 滚动摘要的 Prompt
_SUMMARY_PROMPT_TEMPLATE = """请把下面这段客服对话压缩成一段不超过150字的滚动摘要，
保留：客户意图、已确认事实、待跟进事项。直接输出摘要正文，不要前缀。

对话：
{transcript}
"""


class LongTermMemoryManager:
    """长期记忆读写管理器（模块级单例 memory_manager）"""

    # ------------------------------------------------------------------ #
    # 写入侧
    # ------------------------------------------------------------------ #
    async def extract_and_store(
        self,
        db: AsyncSession,
        customer_id: int,
        messages: list[dict],
    ) -> int:
        """
        从最近一轮对话中用 LLM 抽取事实/偏好，生成 embedding 后落库。

        :param messages: [{"role": "user"/"assistant", "content": "..."}, ...]
        :return: 本次新写入的记忆条数
        """
        if not messages:
            return 0

        # 1) 拼对话文本
        transcript = "\n".join(
            f"{'客户' if m.get('role') == 'user' else '客服'}：{m.get('content', '').strip()}"
            for m in messages if m.get("content")
        )
        if not transcript.strip():
            return 0

        # 2) 调 LLM 抽取
        raw = ""
        try:
            resp = await get_chat_model().ainvoke(
                _EXTRACT_PROMPT_TEMPLATE.format(transcript=transcript)
            )
            raw = getattr(resp, "content", str(resp)) or ""
        except Exception as e:  # 网络/模型异常不能拖垮主流程
            logger.warning(f"[memory] 抽取LLM调用失败 customer={customer_id}: {e}")
            return 0

        # 3) 容错解析 JSON（模型偶尔会包 ```json ... ```）
        parsed = self._parse_json_lenient(raw)
        if parsed is None:
            logger.warning(
                f"[memory] 抽取结果JSON解析失败 customer={customer_id}, raw={raw[:200]}"
            )
            return 0

        facts = parsed.get("facts") or []
        preferences = parsed.get("preferences") or []
        if not isinstance(facts, list) or not isinstance(preferences, list):
            logger.warning(f"[memory] 抽取JSON结构不符预期 customer={customer_id}")
            return 0

        # 4) 逐条生成 embedding 并落库
        # _store_one 返回是否真的写入成功（空内容或 embedding 失败会跳过），
        # 只统计真实写入的条数
        written = 0
        embed_model = get_embed_model()
        for content in facts:
            if await self._store_one(
                db, customer_id, "fact", str(content), embed_model
            ):
                written += 1
        for content in preferences:
            if await self._store_one(
                db, customer_id, "preference", str(content), embed_model
            ):
                written += 1

        if written:
            await db.commit()
            logger.info(f"[memory] customer={customer_id} 新写入 {written} 条长期记忆")
        return written

    async def store_summary(
        self,
        db: AsyncSession,
        customer_id: int,
        conversation_id: int,
    ) -> Optional[LongTermMemory]:
        """对一段会话生成滚动摘要并落库（memory_type=summary）"""
        msgs = await ConversationRepository.get_messages(db, conversation_id)
        if not msgs:
            return None

        transcript = "\n".join(
            f"{'客户' if m.role == 'user' else '客服'}：{m.content}" for m in msgs
        )
        try:
            resp = await get_chat_model().ainvoke(
                _SUMMARY_PROMPT_TEMPLATE.format(transcript=transcript)
            )
            summary = (getattr(resp, "content", str(resp)) or "").strip()
        except Exception as e:
            logger.warning(f"[memory] 摘要生成失败 conv={conversation_id}: {e}")
            return None

        if not summary:
            return None

        emb = get_embed_model().embed_query(summary)
        obj = LongTermMemory(
            customer_id=customer_id,
            memory_type="summary",
            content=summary,
            importance=5,
            embedding=emb,
        )
        await MemoryRepository.create(db, obj)
        await db.commit()
        logger.info(f"[memory] customer={customer_id} 会话{conversation_id}摘要已落库")
        return obj

    # ------------------------------------------------------------------ #
    # 读取侧
    # ------------------------------------------------------------------ #
    async def retrieve_relevant(
        self,
        db: AsyncSession,
        customer_id: int,
        query: str,
        top_k: Optional[int] = None,
    ) -> list[str]:
        """
        召回与 query 相关的长期记忆内容列表。

        流程：
        1. 对 query 生成 embedding；
        2. 全量取出该客户记忆（有界）；
        3. Python 端算余弦，过滤 > settings.memory_similarity_threshold；
        4. 按 余弦相似度 * importance 加权排序，取 top_k；
        5. 更新命中记忆的 last_used_at / use_count；
        6. 返回记忆正文字符串列表。
        """
        top_k = top_k or settings.memory_top_k
        if not query or not query.strip():
            return []

        # 1) query 向量化
        try:
            query_emb = get_embed_model().embed_query(query)
        except Exception as e:
            logger.warning(f"[memory] query向量化失败: {e}")
            return []

        # 2) 全量取该客户记忆
        memories = await MemoryRepository.get_by_customer(db, customer_id)
        if not memories:
            return []

        # 3) 算相似度并过滤
        scored: list[tuple[float, LongTermMemory]] = []
        for m in memories:
            if not m.embedding:
                continue
            sim = self._cosine_similarity(query_emb, m.embedding)
            if sim is None or sim <= settings.memory_similarity_threshold:
                continue
            scored.append((sim, m))

        if not scored:
            return []

        # 4) 相似度 * importance 加权排序
        scored.sort(key=lambda x: x[0] * (x[1].importance or 5), reverse=True)
        hits = scored[:top_k]

        # 5) 更新命中记忆的使用情况
        for _, m in hits:
            await MemoryRepository.update_usage(db, m.id)
        await db.commit()

        # 6) 返回正文
        return [m.content for _, m in hits]

    async def get_recent_messages(
        self,
        db: AsyncSession,
        conversation_id: int,
        n: Optional[int] = None,
    ) -> list[dict]:
        """
        取最近 N 轮对话（短期上下文窗口）。
        SQL 层按 created_at desc 取 N 条，再反序还原时间线。
        """
        n = n or settings.memory_recent_window
        msgs: list[Message] = await ConversationRepository.get_messages(
            db, conversation_id, limit=n
        )
        return [
            {"role": m.role, "content": m.content}
            for m in msgs
            if m.role in ("user", "assistant")
        ]

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> Optional[float]:
        """
        余弦相似度 = dot(a,b) / (||a|| * ||b||)。
        维度不一致或任一范数为 0 时返回 None。
        用纯 Python 实现，避免对 numpy 的强依赖。
        """
        if not a or not b or len(a) != len(b):
            return None
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return None
        return dot / (norm_a * norm_b)

    @staticmethod
    def _parse_json_lenient(raw: str) -> Optional[dict]:
        """容忍模型输出里的 ```json 代码块包裹，提取第一个 JSON 对象"""
        if not raw:
            return None
        text = raw.strip()
        # 正则解释：``` 开头、可选的 json 字样、中间任意内容（re.DOTALL 让
        # 小数点也能匹配换行）、再以 ``` 结尾——把 markdown 代码围栏剥掉
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        # 直接解析
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            pass
        # 兜底：截取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
                return obj if isinstance(obj, dict) else None
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    async def _store_one(
        self,
        db: AsyncSession,
        customer_id: int,
        memory_type: str,
        content: str,
        embed_model,
    ) -> bool:
        """单条记忆：生成 embedding 并插入（不 commit，由批量调用方统一提交）

        :return: True 表示真实写入；False 表示内容为空或 embedding 失败被跳过
        """
        content = content.strip()
        if not content:
            return False
        try:
            emb = embed_model.embed_query(content)
        except Exception as e:
            logger.warning(f"[memory] embedding生成失败 content={content[:30]}: {e}")
            return False
        obj = LongTermMemory(
            customer_id=customer_id,
            memory_type=memory_type,
            content=content,
            importance=5,
            embedding=emb,
        )
        await MemoryRepository.create(db, obj)
        return True


# 模块级单例：全局复用，无状态可安全共享
memory_manager = LongTermMemoryManager()
