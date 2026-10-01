# ==============================================
# 后端 Dockerfile - FastAPI + Uvicorn
# ==============================================
# 【基础镜像为什么要用 ARG 传参？】
# 国内直连 Docker Hub（registry-1.docker.io）经常超时拉不动。
# 把基础镜像名做成构建参数 BASE_IMAGE 后，可以在 .env 里配置
# DOCKER_MIRROR，用国内加速源（如 docker.m.daocloud.io）来拉，
# 而不用改动本文件。默认值仍是官方镜像名，不改也能正常构建。
# ==============================================

ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

WORKDIR /app

# 安装系统依赖（aiomysql/pandas 编译需要）
# libgomp1 是 onnxruntime（chromadb 的底层依赖）运行必装的库，
# python:3.11-slim 默认不带，漏装会在后端 import chromadb 时直接报
# "ImportError: libgomp.so.1: cannot open shared object file"
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用 Docker 缓存层）
COPY requirements.txt .
# 国内网络访问 pypi.org 极慢易超时，这里指定清华镜像源，并放宽超时/重试
#   -i            : 改用清华 PyPI 镜像
#   --timeout 120 : 单个包下载超时从默认 15s 提到 120s
#   --retries 5   : 失败最多重试 5 次（网络抖动时很关键）
# 注意：requirements.txt 里锁定的是一组经 pip 解析验证过的自洽版本，
# 千万不要随手改成 >= 区间，否则会触发 ResolutionImpossible 构建失败。
RUN python -m pip install --no-cache-dir --upgrade pip \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 5 \
    && python -m pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 5 -r requirements.txt

# 复制应用代码
COPY app/ ./app/

# 【构建期自检 · 关键】在镜像里直接验证 Agent 的 API 契约。
# 这一步让"依赖装错了版本"在 docker build 阶段就报错失败，
# 而不是等容器跑起来才崩溃重启（那种问题极难排查，后端会一直 unhealthy）。
# 校验内容：
#   1) create_agent 存在 —— 必须装 langchain 1.x（0.3.x 没有这个函数）
#   2) ChatTongyi / DashScopeEmbeddings 存在 —— 必须装 langchain-community
RUN python - <<'PY'
import sys

failures = []

# 1) LangChain 1.x 的新版 Agent 入口
try:
    from langchain.agents import create_agent  # noqa: F401
    import langchain
    print(f"[OK] langchain {langchain.__version__} -> create_agent 可用")
except Exception as e:
    failures.append(f"create_agent 导入失败（多半是 langchain 装成了 0.3.x）：{e}")

# 2) 通义千问 对话/向量模型集成
try:
    from langchain_community.chat_models.tongyi import ChatTongyi  # noqa: F401
    from langchain_community.embeddings import DashScopeEmbeddings  # noqa: F401
    print("[OK] langchain-community -> ChatTongyi / DashScopeEmbeddings 可用")
except Exception as e:
    failures.append(f"langchain-community 集成导入失败：{e}")

# 3) 向量库封装
try:
    from langchain_chroma import Chroma  # noqa: F401
    print("[OK] langchain-chroma -> Chroma 可用")
except Exception as e:
    failures.append(f"langchain-chroma 导入失败：{e}")

# 4) 中间件 API（react_agent 依赖）
try:
    from langchain.agents.middleware import before_model, wrap_tool_call  # noqa: F401
    print("[OK] langchain.agents.middleware -> before_model / wrap_tool_call 可用")
except Exception as e:
    failures.append(f"Agent 中间件 API 导入失败：{e}")

if failures:
    print("\n===== 依赖自检未通过，构建中止 =====", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)

print("===== 依赖自检全部通过 =====")
PY

# 创建数据和日志目录
RUN mkdir -p /app/data /app/logs

# 健康检查（改用 TCP 端口探活，比 HTTP 更稳；start-period 给到 120s 容纳 langchain+chromadb 慢热）
HEALTHCHECK --interval=15s --timeout=10s --start-period=120s --retries=10 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', 8000))" || exit 1

EXPOSE 8000

# 默认启动命令（可被 docker-compose 覆盖为多 worker）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
