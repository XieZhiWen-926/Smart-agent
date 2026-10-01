#!/usr/bin/env bash
# ============================================================
# 智扫通 v2 评测一键脚本（在项目根目录或任意位置执行均可）
#
#   bash deploy/eval/run_eval.sh ingest     # 1) 知识库入库（必须先做）
#   bash deploy/eval/run_eval.sh retrieval  # 2) 召回率
#   bash deploy/eval/run_eval.sh agent      # 3) 问答准确率 + 工具调用成功率
#   bash deploy/eval/run_eval.sh all        # 依次执行全部
#
# 【为什么脚本要拷进容器跑？】
# 召回率要直接访问 Chroma 向量库、工具日志在容器 /app/logs 下、
# 大模型 SDK 与依赖也都装在容器里，在容器内执行最省事。
# ============================================================
set -e

CONTAINER=smart_agent_backend
STEP="${1:-all}"

# 切到项目根目录（本脚本位于 deploy/eval/）
cd "$(dirname "$0")/../.."

# 【关键】Git Bash 会把 /tmp/eval 这类绝对路径改写成 Windows 路径，
# 导致 docker cp / docker exec 找不到目标目录，必须关掉路径转换。
export MSYS_NO_PATHCONV=1

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "[ERROR] 容器 ${CONTAINER} 未在运行，请先执行：docker compose up -d"
  exit 1
fi

echo ">>> 拷贝评测脚本到容器 /tmp/eval"
# 【先删旧目录】docker cp 在目标目录已存在时，会把源目录「嵌套」进去
# （变成 /tmp/eval/eval），于是容器里跑的仍是上一次的旧脚本 —— 极其隐蔽。
docker exec "${CONTAINER}" rm -rf /tmp/eval
docker cp deploy/eval "${CONTAINER}:/tmp/eval"

run_py() {
  echo ""
  echo "==================== $1 ===================="
  docker exec -w /app -e PYTHONPATH=/app "${CONTAINER}" python "$2"
}

case "$STEP" in
  ingest)    run_py "知识库入库" /tmp/eval/ingest_knowledge.py ;;
  retrieval) run_py "召回率评测" /tmp/eval/eval_retrieval.py ;;
  agent)     run_py "端到端评测" /tmp/eval/eval_agent.py ;;
  all)
    run_py "知识库入库" /tmp/eval/ingest_knowledge.py
    run_py "召回率评测" /tmp/eval/eval_retrieval.py
    run_py "端到端评测" /tmp/eval/eval_agent.py
    ;;
  *)
    echo "用法: bash deploy/eval/run_eval.sh [ingest|retrieval|agent|all]"
    exit 1
    ;;
esac

echo ""
echo ">>> 完成"
