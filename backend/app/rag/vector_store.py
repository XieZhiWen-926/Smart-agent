"""
Chroma 向量库管理
==================
【这个文件是干什么的】
负责知识文档与 CSV 数据行的"向量化存储与检索"：
把文本通过 embedding 模型转成一串数字（向量），存进 Chroma；
查询时把问题也转成向量，找出"距离最近"（语义最像）的文本片段。
使用 langchain_chroma.Chroma 持久化到本地磁盘（重启不丢数据）。

【和哪些文件联动】
- embedding 模型来自 app/model/factory.py 的 get_embed_model()
- 被 app/rag/rag_service.py（RAG 问答）和
  app/services/dataset_service.py（CSV 行入库）调用
"""
from __future__ import annotations

import asyncio
from typing import Optional

import pandas as pd
from langchain_core.documents import Document

from app.config import settings
from app.model.factory import get_embed_model
from app.utils.logger import logger


class VectorStoreManager:
    """Chroma 向量库封装（单例使用）"""

    def __init__(self) -> None:
        """
        初始化持久化向量库。
        - persist_directory: Chroma 数据落盘目录
        - collection_name: 集合名
        - embedding_function: 使用通义 text-embedding-v4
        """
        from langchain_chroma import Chroma

        logger.info(
            f"初始化 Chroma 向量库: dir={settings.chroma_persist_dir}, "
            f"collection={settings.chroma_collection}"
        )
        self._store = Chroma(
            persist_directory=settings.chroma_persist_dir,
            collection_name=settings.chroma_collection,
            embedding_function=get_embed_model(),
        )

    # ------------------------------------------------------------------
    # 文档写入
    # ------------------------------------------------------------------
    async def add_documents(
        self,
        texts: list[str],
        metadatas: Optional[list[dict]] = None,
    ) -> None:
        """
        添加文本片段到向量库。

        :param texts: 文本内容列表
        :param metadatas: 与 texts 一一对应的元数据（如来源文件名、分类）
        """
        if not texts:
            return

        docs = [Document(page_content=t, metadata=m or {}) for t, m in zip(texts, metadatas or [{}] * len(texts))]
        # Chroma 的 add_documents 是同步方法，直接 await 会卡住整个事件循环；
        # asyncio.to_thread 把它丢到子线程里跑，主线程还能处理其他请求
        await asyncio.to_thread(self._store.add_documents, docs)
        logger.info(f"向量化写入 {len(texts)} 条文档片段")

    # ------------------------------------------------------------------
    # 相似度检索
    # ------------------------------------------------------------------
    async def similarity_search(
        self,
        query: str,
        k: Optional[int] = None,
    ) -> list[Document]:
        """
        相似度检索 top-k 文档。

        :param query: 查询文本
        :param k: 返回条数，默认取 settings.rag_top_k
        :return: Document 列表（含 page_content 和 metadata）
        """
        k = k or settings.rag_top_k
        # 同理，检索也是同步方法，用 to_thread 避免阻塞事件循环
        docs = await asyncio.to_thread(self._store.similarity_search, query, k=k)
        logger.debug(f"检索 query='{query[:30]}...' 返回 {len(docs)} 条")
        return docs

    # ------------------------------------------------------------------
    # CSV 行向量化（供语义兜底）
    # ------------------------------------------------------------------
    async def add_csv_rows(self, df: pd.DataFrame, dataset_name: str) -> None:
        """
        将 CSV 每行数据转为自然语言文本，向量化存入 Chroma。

        用途：当 Text2SQL 查不到结果时，RAG 可以直接从这些行向量里
        找到语义最相近的记录作为兜底回答。

        文本格式示例：
            [数据集:用户使用记录] 用户ID:001 | 用户名:张三 | 注册时间:2024-01-01

        :param df: 已重命名为物理列名的 DataFrame
        :param dataset_name: 数据集名称（写入 metadata）
        """
        texts: list[str] = []
        metas: list[dict] = []

        for _, row in df.iterrows():
            parts = [f"{col}:{row[col]}" for col in df.columns if pd.notna(row[col])]
            line = f"[数据集:{dataset_name}] " + " | ".join(parts)
            texts.append(line)
            metas.append({"source": "csv_row", "dataset_name": dataset_name})

        if texts:
            await self.add_documents(texts, metas)
            logger.info(f"数据集 '{dataset_name}' 的 {len(texts)} 行已向量化入库")


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------
_vector_store: Optional[VectorStoreManager] = None


def get_vector_store() -> VectorStoreManager:
    """获取向量库单例（进程内唯一）"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStoreManager()
    return _vector_store
