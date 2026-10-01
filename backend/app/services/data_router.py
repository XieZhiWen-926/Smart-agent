"""
智能问题路由器
================
根据用户问题自动选择回答路径：
    语义匹配数据集 → Text2SQL 查询 → RAG 知识库兜底 → 澄清告知

四级分支：
    1. text2sql: 语义匹配度高，直接查结构化数据
    2. rag:      结构化数据查不到，退回到知识库向量检索
    3. clarify:  两者都没命中，礼貌告知并引导
    4. tool:      预留（后续接业务工具调用）

上游：api/datasets.py 的 /query 接口；下游：services/text2sql_service.py、rag/rag_service.py。
"""
from __future__ import annotations

import math
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.model.factory import get_embed_model
from app.models.dataset import Dataset
from app.repositories.dataset_repo import DatasetRepository
from app.rag.rag_service import get_rag_service
from app.services.text2sql_service import Text2SQLService
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# 工具函数：余弦相似度
# ---------------------------------------------------------------------------
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class DataRouter:
    """智能问题路由器"""

    # ------------------------------------------------------------------
    # 可用数据集列表
    # ------------------------------------------------------------------
    @staticmethod
    async def list_available_datasets(db: AsyncSession) -> list[Dataset]:
        """获取所有已完成导入的数据集（供语义匹配用）"""
        return await DatasetRepository.get_all(db, status="completed")

    # ------------------------------------------------------------------
    # 语义匹配：找到最相关的数据集
    # ------------------------------------------------------------------
    @staticmethod
    async def _match_dataset(
        query: str,
        datasets: list[Dataset],
    ) -> tuple[Optional[Dataset], float]:
        """
        将用户问题与每个数据集的描述做 embedding 余弦匹配。

        :return: (最匹配的数据集, 相似度分数 0~1)
        """
        if not datasets:
            return None, 0.0

        embed = get_embed_model()

        # 构建每个数据集的匹配文本：名称 + 描述 + 列名
        texts = []
        for ds in datasets:
            col_names = ", ".join(
                cm.get("original_name", cm.get("physical_name", ""))
                for cm in (ds.columns_meta or [])
            )
            text = f"数据集: {ds.name}\n描述: {ds.description}\n列: {col_names}"
            texts.append(text)

        # 批量 embedding：把文本变成向量（一串浮点数），语义相近的文本向量也相近，
        # 于是可以用余弦相似度衡量"问题和数据集描述有多相关"
        ds_vectors = await embed.aembed_documents(texts)
        query_vector = (await embed.aembed_documents([query]))[0]

        # 计算余弦相似度，取最高分
        best_score = -1.0
        best_idx = -1
        for i, dv in enumerate(ds_vectors):
            score = _cosine_similarity(query_vector, dv)
            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx < 0:
            return None, 0.0

        logger.info(
            f"语义匹配: query='{query[:30]}...' -> "
            f"dataset='{datasets[best_idx].name}' score={best_score:.4f}"
        )
        return datasets[best_idx], best_score

    # ------------------------------------------------------------------
    # 主路由入口
    # ------------------------------------------------------------------
    async def route(
        self,
        db: AsyncSession,
        query: str,
        customer_id: Optional[int] = None,
    ) -> dict:
        """
        路由用户问题，返回统一格式的回答。

        :param query: 用户自然语言问题
        :param customer_id: 客户 ID（预留，用于个性化）
        :return: {
            "route": "text2sql|rag|clarify|tool",
            "answer": str,
            "source": str,
            "confidence": float,
        }
        """
        # ---- 获取可用数据集 ----
        datasets = await self.list_available_datasets(db)

        # ---- 阶段 1：语义匹配 ----
        matched_ds, match_score = await self._match_dataset(query, datasets)

        # ---- 阶段 2：Text2SQL 分支 ----
        if matched_ds and match_score >= settings.text2sql_confidence_threshold:
            try:
                sql, gen_conf = await Text2SQLService.generate_sql(db, query, matched_ds)
                results = await Text2SQLService.execute_sql(db, sql, matched_ds)

                if results:
                    answer = await Text2SQLService.results_to_natural_language(
                        query, sql, results
                    )
                    return {
                        "route": "text2sql",
                        "answer": answer,
                        "source": matched_ds.name,
                        "confidence": min(match_score, gen_conf),
                        "sql": sql,
                        "results": results,
                    }
                else:
                    logger.info(
                        f"Text2SQL 无结果，回退 RAG。dataset={matched_ds.name}"
                    )
            except Exception as e:
                logger.warning(f"Text2SQL 执行失败，回退 RAG: {e}")

        # ---- 阶段 3：RAG 回退分支 ----
        try:
            rag = get_rag_service()
            rag_answer = await rag.rag_summarize(query)

            # 判断 RAG 是否返回了有意义内容
            if rag_answer and "未找到" not in rag_answer and len(rag_answer) > 5:
                return {
                    "route": "rag",
                    "answer": rag_answer,
                    "source": "知识库",
                    "confidence": 0.5,
                }
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")

        # ---- 阶段 4：澄清/告知分支 ----
        return {
            "route": "clarify",
            "answer": (
                "抱歉，当前知识库和数据集中没有找到与您问题相关的信息。"
                "您可以尝试：\n"
                "1. 换一种问法重新描述问题\n"
                "2. 上传相关 CSV 数据集后再查询\n"
                "3. 联系人工客服协助处理"
            ),
            "source": "",
            "confidence": 0.0,
        }
