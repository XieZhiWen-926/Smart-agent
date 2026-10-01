"""
召回率评测脚本（在 backend 容器内运行）
======================================
【测什么】
只测「检索」这一段，不经过大模型。原因：召回率是检索器的固有属性，
混进大模型后你无法区分「没检索到」和「检索到了但模型没说」。

【指标口径】
- Hit@K  ：top-K 结果中是否出现期望来源文档。命中记 1，否则 0。
           这是业界常说的「召回率」，严格叫法是 Hit Rate / Recall@K（文档级）。
- MRR@K  ：第一条命中结果的排名倒数（第 1 名得 1.0，第 2 名得 0.5…）。
           它比 Hit@K 更严格——命中但排在很后面，说明排序质量差。
- 分块级召回：只要命中的片段里包含参考答案关键词即算命中（更宽松，仅供参考）。

【注意】本脚本用文件名做判定，依赖入库时写入的 metadata.source。
       因此必须先用 ingest_knowledge.py 入库。
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from app.config import settings  # noqa: E402
from app.rag.vector_store import get_vector_store  # noqa: E402

GOLDEN_PATH = Path("/tmp/eval/golden_set.json")
KS = [1, 3, 5]  # 3 = 线上 rag_top_k 的实际取值，1/5 用于观察排序质量与提升空间


async def main() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    samples = golden["retrieval"]
    if not samples:
        print("黄金集 retrieval 段为空")
        return

    vs = get_vector_store()
    max_k = max(KS)

    # hit[k] = 命中数；rr[k] = 倒数排名之和
    hit = {k: 0 for k in KS}
    rr = {k: 0.0 for k in KS}
    details = []

    print("=" * 78)
    print(f"召回率评测   样本数={len(samples)}   线上 rag_top_k={settings.rag_top_k}")
    print("=" * 78)

    for s in samples:
        docs = await vs.similarity_search(s["query"], k=max_k)
        sources = [d.metadata.get("source", "<无source>") for d in docs]
        expected = set(s["expected_sources"])

        # 找到第一条命中的排名（从 1 开始）
        rank = next((i + 1 for i, src in enumerate(sources) if src in expected), None)

        for k in KS:
            if rank is not None and rank <= k:
                hit[k] += 1
                rr[k] += 1.0 / rank

        details.append({"id": s["id"], "query": s["query"], "rank": rank, "top": sources})

        flag = "[HIT ]" if rank else "[MISS]"
        rank_txt = f"首个命中 rank={rank}" if rank else "未命中"
        print(f"\n{flag} {s['id']}  {s['query']}")
        print(f"       期望来源: {sorted(expected)}")
        print(f"       实际返回: {sources}   ({rank_txt})")

    n = len(samples)
    print("\n" + "=" * 78)
    print("汇总")
    print("=" * 78)
    print(f"{'K':<4}{'命中数':<10}{'召回率(Recall@K)':<22}{'MRR@K':<12}")
    for k in KS:
        print(f"{k:<4}{hit[k]:<10}{hit[k] / n * 100:>8.1f}%{'':<12}{rr[k] / n:>8.3f}")

    miss = [d for d in details if d["rank"] is None]
    if miss:
        print(f"\n未命中样本（{len(miss)} 条，优先排查这几条）：")
        for d in miss:
            print(f"  {d['id']}  {d['query']}")
            print(f"        实际 top3 = {d['top']}")

    print("\n[提示] 召回率低时按此顺序排查：")
    print("  1) 该知识点是否真的在库里（用 ingest_knowledge.py 的入库日志核对片段数）")
    print("  2) 语料是否有乱码（乱码会直接破坏 embedding 语义）")
    print("  3) chunk_size 是否过大（500 字以上容易稀释语义，可试 300）")
    print("  4) 是否需要加查询改写 / 混合检索（BM25 + 向量）")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
