# 项目长期记忆 — 智扫通智能客服 v2

## 技术栈与版本基线（勿随意升级）
- Python 3.11 + FastAPI 0.115.6 + SQLAlchemy 2.0.36(异步/aiomysql) + Pydantic 2.13.5
- **LangChain 1.x 全家桶（必须同源，改任一版本前先跑 `pip install --dry-run -r requirements.txt`）**：
  langchain 1.4.2 / langchain-core 1.6.5 / langchain-community 0.4.2 / langchain-classic 1.0.8 /
  langgraph 1.2.12 / langchain-chroma 1.1.0 / langchain-text-splitters 1.1.2 / chromadb 1.5.9
- pydantic-settings 必须 >= 2.10.1（langchain-community 0.4.2 的硬约束）
- Vue 3 + Vite + Element Plus；MySQL 8.0；Redis 7；Celery 5.4

## 架构约定
- 后端分层：`api/`（HTTP）→ `services/`（业务）→ `repositories/`（SQL）→ `models/`（ORM）
- Agent：`app/agent/react_agent.py`（每请求一个 SmartAgent 实例，模型走 `app/model/factory.py` 单例）
- 工具：`app/agent/tools/{base_tools,map_tools,dynamic_tools}.py`，DB 里的 custom_tools 动态加载
- 配置统一从 `app/config.py` 的 `settings` 读，禁止硬编码

## 踩坑记录（重要，改代码前先看）
1. **`create_agent` 只在 langchain 1.x 存在**。装成 0.3.x 会 `ImportError`，且 Docker 构建仍会成功 → 已在 backend/Dockerfile 加构建期自检。
2. **`before_model` 中间件钩子必须接收 `(state, runtime)` 两个参数**。写成一个参数时 `create_agent()` 不报错，只在执行时报 `TypeError`。
3. **`ToolCallRequest` 的工具信息在 `request.tool_call` 里**（dict：name/args/id），不是 `request.tool_name`。
4. **`callable(BaseTool实例)` 在 LangChain 1.x 返回 False**。判断工具对象请用 `isinstance(obj, BaseTool)`，否则工具索引会变空。
5. **连接串里的密码必须 `quote_plus` 编码**。本项目 MySQL 密码含 `@`，不编码会导致主机名被解析成 `@mysql`。
6. **容器内不要写死 `127.0.0.1`**（Redis/MySQL 都是别的容器）。celery broker 已改为按 `REDIS_HOST` 自动推导。
7. **所有 Response Schema 必须有 `model_config = ConfigDict(from_attributes=True)`**，否则 `model_validate(ORM对象)` 报 `model_type` 错误。
8. **SSE 流式必须用 `stream_mode="messages"`**。用 `"values"` 会变成整段返回（无打字机效果），还会把用户提问/工具输出混进答案。
9. **`sql/init.sql` 里的 `SET NAMES utf8mb4;` 不能删**，否则中文入库变乱码。
10. **管理员账号由后端启动时创建**（不在 init.sql），后端不健康就登录不了。
11. **用于 `FROM` 的 `ARG` 必须写在第一个 `FROM` 之前**（全局作用域）。写在两个 `FROM` 之间会变成上一阶段的局部变量，后续 `FROM` 读不到 → `base name (...) should not be blank`。`frontend/Dockerfile` 曾踩此坑。
12. **改 Dockerfile 后必须跑完整的 `docker compose build`**，不能只构建单个 target —— 后端只有一个 FROM，ARG 位置恰好合法，掩盖了前端多阶段构建的问题。
13. **`.env` 的优先级高于 `config.py` 与 compose 的默认值**。排查"模型不存在/连错地址"类问题，第一站就是 `.env`。曾出现 `CHAT_MODEL_NAME=qwen3.8-max` 这种无效模型名覆盖了正确默认值。
14. **`docker compose up -d --build` 不一定重建镜像已变的前端容器**。要核对 `docker inspect <容器> --format '{{.Image}}'` 与 `docker image inspect <tag> --format '{{.Id}}'` 是否一致，不一致就 `--force-recreate`。
15. **接口契约**：登录 `POST /api/auth/login` 是 **form-encoded**（非 JSON）；聊天 `POST /api/chat/stream` 必填 `query` + `customer_id`（不是 `message`）。
16. **Git Bash 下 `docker exec` 里的绝对路径会被转换破坏**，需前置 `MSYS_NO_PATHCONV=1`。
17. **前端 SSE 必须显式处理 `error` 帧**。后端出错时推 `{"error":"..."}`（无 `content` 字段），若前端只读 `parsed.content`，该帧会被静默丢弃 → 错误帧后紧跟的 `[DONE]` 触发 `onDone` 把 `isStreaming` 置 false → **留下一个空白气泡，用户看到"毫无反应"**。这类"错误没进错误分支"的缺陷静态读代码极难发现。
18. **重启 `backend` 后必须紧接着 `docker compose restart nginx_gateway`**，否则网关 502（Nginx 启动时缓存了上游 `backend` 的 IP，容器重启后 IP 变了）。
19. **前端代码是 build 进镜像的**，改完要 `build frontend` + `up -d --force-recreate frontend`；后端是卷挂载，`restart backend` 即可。
20. **Swagger 鉴权是 OAuth2 密码模式**（`OAuth2PasswordBearer(tokenUrl="/api/auth/login")`，OpenAPI 里 `type: oauth2` + `flows.password`）。点 **Authorize** 后填的是 **username/password**（admin/admin123），Swagger 自己去换 token。**弹窗里没有粘贴 token 的位置**，不要写"填 `Bearer xxx`"这类说明，会让用户卡死。
21. **`POST /api/tools/{id}/test` 的请求体是 `{"params": {...}}`**，必须再包一层 `params`，直接写工具参数会 422。工具 id 基线：1 rag_summarize / 2 amap_geocode / 3 amap_regeocode / **4 amap_weather** / 5 amap_around_search / 6 baidu_geocode / 7 baidu_weather。
22. **工具直测（5.1 节）不经过大模型**，所以大模型欠费时它照样能通过 —— 用它来区分"工具坏了"还是"大模型不会选工具"。
23. **`config.py` 的 `PROJECT_ROOT` 在容器内会越界**：宿主机布局 `backend/app/config.py` 上溯三级正确；
    容器内是 `/app/app/config.py`（Dockerfile `COPY app/ ./app/`），上溯三级得到 `/`，
    于是 `chroma_persist_dir`/`UPLOAD_DIR`/`LOG_DIR` 全指向**未挂载**目录，向量库/上传/日志容器重建即丢。
    已改为探测式判定（上溯三级若无 `docker-compose.yml`/`backend/` 则回退两级）。**改路径相关代码前先确认 PROJECT_ROOT 的值**。
24. **给 Chroma 入库不要用 `reset_collection()`**：它会删除并重建 collection，让**运行中的后端 worker**
    手里已持有的句柄失效，之后走 HTTP 问 Agent 一律答"未找到"，而单独跑脚本却检索正常 —— 极具迷惑性。
    改用按 id 逐条 `delete(ids=...)`，collection 不变，无需重启后端。
25. **`docker cp` 目标目录已存在时会把源目录嵌套进去**（`deploy/eval` → `/tmp/eval/eval`），
    于是容器里跑的仍是上一次的旧脚本。**必须先 `docker exec <容器> rm -rf /tmp/eval`**。
26. **"工具调用成功率"是会骗人的指标**：中间件 `monitor_tool` 把工具异常兜底成 error ToolMessage 后正常返回，
    日志记的是 `<-` 而不是 `!!`，所以该指标恒为 100%。真实质量要看**工具结果有效率**（结果里是否含
    `Error invoking tool`/`API调用失败`/`未找到相关信息` 等无数据标记）。
27. **错误消息回灌给模型会让 SSE 流整个中断**（已定位根因，待修）：`middleware.py` 把 LangChain 异常原文
    塞进 error ToolMessage，而异常文本内嵌 Python 字面量 `{'keyword': '公园'}`（单引号）→ 模型下一轮
    模仿该格式生成 tool_call → DashScope 400 `The "function.arguments" parameter ... must be in JSON format`
    → `astream` 抛异常 → 用户拿到半截对话。修法：回灌前 `re.sub(r"\{[^{}]*\}", "…", str(e))` 剔除花括号片段。
28. **DB 的 `custom_tools.description` 对 builtin/map 工具不生效**：`dynamic_tools.py::_build_tool()`
    对 `builtin`/`map_amap`/`map_baidu` 三类**直接返回代码里的 `@tool` 对象**，描述取的是**代码 docstring**。
    改工具说明要改 `map_tools.py`/`base_tools.py`，改数据库那句是白费功夫。
29. **别把"终端显示乱码"当成"文件乱码"**：Git Bash 输出中文时可能显示 `ã€`，实际文件是干净的 UTF-8。
    用 Python 逐文件统计可疑字符数才能确认。曾据此误报过一次。

## 运行与验证
- 启动：`docker compose up -d`（首次构建约 5~15 分钟）
- 入口：http://localhost （网关）｜ http://localhost:8000/docs （Swagger）
- 测试账号：admin / admin123
- 验证脚本：`python deploy\verify_e2e.py`（接口+数据，7 项）、`python deploy\verify_chat.py`（大模型流式）
  - 本机用 `C:/PyCharm/Anaconda3/python.exe` 执行
- 效果评测（召回率/问答准确率/工具成功率）：`bash deploy/eval/run_eval.sh [ingest|retrieval|agent|all]`
  - 脚本会被拷进 backend 容器执行（向量库、日志、SDK 都在容器内）
  - 首次必须先跑 `ingest`（项目原本没有知识库入库链路，Chroma 是空的）
  - 基线实测：Recall@1 60% / Recall@3 80% / Recall@5 86.7%；工具选择 100%；工具结果有效率 54.5%；问答准确率约 50%（波动大）
- 国内镜像加速：`deploy/docker/setup-docker-mirror.ps1`，或 `.env` 里设 `DOCKER_MIRROR`

## 文档
- `docs/高并发技术方案.md` — 原有高并发设计文档
