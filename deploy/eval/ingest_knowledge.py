"""
知识库入库脚本（在 backend 容器内运行）
=======================================
【为什么需要它】
项目里 data/ 下放着 6 份知识文档，但代码中**没有任何 TXT/PDF 切片入库的实现**：
rag_service / vector_store 只提供"写入"能力，没人调用；data/chroma_db 也不存在。
结果是 Chroma 集合为空 → rag_summarize 永远返回"未找到相关信息" → 召回率无从谈起。

本脚本补齐这条链路：TXT/PDF → 分块 → 向量化 → 写入 Chroma。

【运行方式】见 deploy/eval/README.md
【可重复执行】每次运行会先清空集合再重新入库，不会产生重复片段。
"""
import asyncio
import sys
from pathlib import Path

# 容器 WORKDIR=/app，代码在 /app/app，确保能 import app.*
sys.path.insert(0, "/app")

from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402

from app.rag.vector_store import get_vector_store  # noqa: E402
from app.utils.logger import logger  # noqa: E402

DATA_DIR = Path("/app/data")
CHUNK_SIZE = 500        # 每个片段 500 字：太小丢上下文，太大稀释语义
CHUNK_OVERLAP = 80      # 相邻片段重叠 80 字，避免答案被切断在边界

# 中文文档优先按「段落 → 换行 → 句号 → 分号 → 空格」逐级切分，
# 比默认的英文分隔符（\n\n \n " "）更贴合中文排版
SEPARATORS = ["\n\n", "\n", "。", "；", "！", "？", "，", " ", ""]


def load_txt(path: Path) -> str:
    """读取纯文本，容忍混合编码（知识库里部分文件有 UTF-8/GBK 混杂残留）"""
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    # 兜底：忽略无法解码的字节，保证入库流程不中断
    logger.warning(f"{path.name} 编码异常，已按 utf-8/ignore 读取（可能丢失少量字符）")
    return path.read_text(encoding="utf-8", errors="ignore")


def load_pdf(path: Path) -> str:
    """用 pypdf 抽取 PDF 文本（依赖已在 requirements.txt 中：pypdf==5.1.0）"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    logger.info(f"{path.name} 解析完成，共 {len(pages)} 页")
    return "\n\n".join(pages)


async def main() -> None:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=SEPARATORS,
        length_function=len,
    )

    files = sorted(
        [p for p in DATA_DIR.glob("*") if p.suffix.lower() in (".txt", ".pdf")]
    )
    if not files:
        logger.error(f"{DATA_DIR} 下没有找到 .txt / .pdf 文件")
        return

    vs = get_vector_store()

    # 清空已有片段，保证脚本可重复执行。
    #
    # 【★ 为什么不用 reset_collection()？★】
    # reset_collection() 会「删除整个 collection 再重建」。此时其它进程
    # （例如正在运行的后端 uvicorn worker）手里已经持有的 collection 句柄
    # 会指向一个已不存在的集合，之后它们的检索一律返回空——
    # 现象极具迷惑性：入库日志显示成功、单独跑脚本也能检索到，
    # 但走 HTTP 问 Agent 却回答"根据现有知识库未找到相关信息"。
    # 这里改为按 id 逐条删除，collection 本身保持不变，其它进程无需重启。
    removed = 0
    while True:
        existing = vs._store.get(limit=500)  # noqa: SLF001 - 评测脚本内部使用
        ids = existing.get("ids") or []
        if not ids:
            break
        vs._store.delete(ids=ids)  # noqa: SLF001
        removed += len(ids)
    logger.info(f"已清空 {removed} 条旧片段（保留 collection，不影响运行中的后端）")

    total_chunks = 0
    for path in files:
        try:
            text = load_pdf(path) if path.suffix.lower() == ".pdf" else load_txt(path)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"解析失败，跳过 {path.name}: {exc}")
            continue

        if not text.strip():
            logger.warning(f"{path.name} 解析后为空，跳过")
            continue

        chunks = splitter.split_text(text)
        # metadata.source 是召回率评测的判定依据，必须写入文件名
        metadatas = [
            {"source": path.name, "chunk_index": i, "doc_type": path.suffix.lstrip(".")}
            for i in range(len(chunks))
        ]

        await vs.add_documents(chunks, metadatas)
        total_chunks += len(chunks)
        logger.info(f"入库 {path.name}：{len(text)} 字 → {len(chunks)} 个片段")

    logger.info(f"知识库入库完成：{len(files)} 个文件，共 {total_chunks} 个片段")

    # 自检：用一条明确的问题验证检索链路真的通了
    probe = await vs.similarity_search("扫地机器人开机没有反应怎么办", k=3)
    logger.info(f"入库自检：检索到 {len(probe)} 条片段")
    for doc in probe:
        logger.info(f"  - 来源={doc.metadata.get('source')} 片段={doc.page_content[:40]!r}")


if __name__ == "__main__":
    asyncio.run(main())
