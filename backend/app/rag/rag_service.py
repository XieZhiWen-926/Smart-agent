"""
RAG 服务
=========
【这个文件是干什么的】
RAG = 检索增强生成（Retrieval-Augmented Generation）。回答用户问题时，
先从 Chroma 向量库里"查资料"（召回最相关的文档片段），再让大模型
"看着资料回答"，而不是凭记忆瞎编——这是减少大模型幻觉的经典手段。

【和哪些文件联动】
- 向量检索底层：app/rag/vector_store.py（VectorStoreManager）
- 大模型来源：app/model/factory.py 的 get_chat_model()
- 调用方：app/agent/tools/base_tools.py 的 rag_summarize 工具
  （Agent 在需要查知识库时调用）
"""
from __future__ import annotations

from typing import Optional

from app.model.factory import get_chat_model
from app.rag.vector_store import get_vector_store
from app.utils.logger import logger


class RagService:
    """RAG 问答服务"""

    def __init__(self) -> None:
        self._vector_store = get_vector_store()

    async def rag_summarize(self, query: str) -> str:
        """
        基于知识库回答用户问题。

        流程：
            1. 从向量库检索 top_k 相关片段
            2. 将片段拼接为上下文，构建 Prompt
            3. 调用 ChatModel 生成回答
            4. 如果检索结果为空，直接返回"未找到"

        :param query: 用户问题
        :return: 自然语言回答
        """
        # ---- 1. 检索 ----
        docs = await self._vector_store.similarity_search(query)
        if not docs:
            return "根据现有知识库未找到相关信息"

        # ---- 2. 拼接上下文：用分隔线把多个片段拼成一整段"参考资料" ----
        context = "\n---\n".join(d.page_content for d in docs)
        logger.debug(f"RAG 检索到 {len(docs)} 条片段，上下文长度={len(context)}")

        # ---- 3. 构建 Prompt 并调用 LLM ----
        prompt = (
            "请根据以下参考资料回答用户问题。"
            "如果资料中没有相关信息，请回答'根据现有知识库未找到相关信息'，不要编造。\n\n"
            f"参考资料：\n{context}\n\n"
            f"问题：{query}"
        )

        chat = get_chat_model()
        # ChatTongyi 的 ainvoke 是异步方法（a 前缀 = async），
        # await 等待大模型返回完整回答
        response = await chat.ainvoke(prompt)
        answer = response.content if hasattr(response, "content") else str(response)

        return answer.strip()


# ---------------------------------------------------------------------------
# 模块级单例
# 【单例模式】整个进程只创建一个 RagService（它内部持有向量库连接），
# 用模块级私有变量 + 全局函数实现；global 关键字用于在函数内修改模块变量
# ---------------------------------------------------------------------------
_rag_service: Optional[RagService] = None


def get_rag_service() -> RagService:
    """获取 RAG 服务单例（第一次调用时才创建，即"懒加载"）"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RagService()
    return _rag_service
