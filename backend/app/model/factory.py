"""
模型工厂（单例模式）
====================
【这个文件是干什么的】
统一创建并保管两个"重对象"：对话大模型（ChatModel）和向量模型（Embeddings）。
全项目任何需要大模型的地方都从这里拿，不允许各自 new。

【为什么要单例？】
这两个对象底层都维护着到阿里云 DashScope 的网络连接/会话。
每来一次请求就新建一次，既慢又费连接资源；做成模块级单例，
整个进程只初始化一次，之后所有人复用同一个。

【和哪些文件联动】
被 react_agent / long_term_memory / rag_service / vector_store 等模块调用。
"""
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings

from app.config import settings
from app.utils.logger import logger

# 全局单例（模块级变量，进程内唯一；None 表示"还没初始化"）
_chat_model = None
_embed_model = None


def get_chat_model():
    """获取通义千问 ChatModel 单例（第一次调用时才真正创建，即懒加载）"""
    global _chat_model  # global：声明要修改的是模块级变量，而不是新建局部变量
    if _chat_model is None:
        logger.info(f"初始化 ChatModel: {settings.chat_model_name}")
        _chat_model = ChatTongyi(
            model=settings.chat_model_name,
            dashscope_api_key=settings.dashscope_api_key,
            temperature=0.3,   # 越低回答越稳，客服场景不需要太多"发挥"
            streaming=True,    # 开启流式输出，配合打字机效果
        )
    return _chat_model


def get_embed_model():
    """获取通义千问 Embeddings 单例（把文本转向量，供 RAG / 长期记忆用）"""
    global _embed_model
    if _embed_model is None:
        logger.info(f"初始化 Embeddings: {settings.embedding_model_name}")
        _embed_model = DashScopeEmbeddings(
            model=settings.embedding_model_name,
            dashscope_api_key=settings.dashscope_api_key,
        )
    return _embed_model
