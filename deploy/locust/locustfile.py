# -*- coding: utf-8 -*-
"""
=====================================================================
智扫通智能客服 v2 —— Locust 高并发压测脚本
=====================================================================

【压测命令】（在 deploy/locust 目录下执行）

    # 1) 安装依赖
    pip install -r requirements.txt

    # 2) 无头模式跑 5 分钟，100 并发用户，每秒爬升 10 个，生成 HTML 报告
    locust -f locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10 --run-time=5m --headless --html=report.html

    # 说明：
    #   --host   被压地址。走 Nginx 网关就填 http://localhost（80 端口）；
    #            直连后端就填 http://localhost:8000。
    #   --users  并发虚拟用户数（同时在线的“人”）。
    #   --spawn-rate 每秒新拉起多少用户（爬升速率）。
    #   --run-time   压测时长，到时自动停止。
    #   --headless   不开 Web UI，命令行直接跑。
    #   --html       跑完导出 HTML 报告（含每个接口的 P50/P95/P99）。
    #
    # 想边压边看曲线：去掉 --headless --run-time --html，直接 locust -f locustfile.py
    # 然后浏览器打开 http://localhost:8089 ，在网页里填 host / users / spawn-rate。


【容量估算公式】（利特尔法则 Little's Law）

    并发连接数 N ≈ 目标 QPS × 单请求平均耗时 T（秒）

  举例：
    - 普通列表接口平均 0.1s，目标 200 QPS  → 需要并发 ≈ 200 × 0.1 = 20
    - 聊天 SSE 接口（含 LLM 流式）平均 3s，目标 50 QPS → 需要并发 ≈ 50 × 3 = 150

  后端侧总 DB 连接上限估算（与本项目配置对照）：
    - 单进程连接池 = pool_size(20) + max_overflow(30) = 50
    - uvicorn --workers 4 → 后端实例最多占 4 × 50 = 200 个 MySQL 连接
    - docker-compose 里 MySQL max_connections=500，还要给 celery_worker、
      监控、预留连接留余量，因此 200 是安全的；不要盲目把 worker 数或
      pool_size 加到把 MySQL 连接打满（>500 会直接 Too many connections）。

  找拐点：逐步加大 --users（如 50 → 100 → 200 → 300），观察报告里
  “P95 延迟开始陡增”或“失败率 > 1%”的那个点，就是当前配置的容量上限。


【调优顺序（先定位再动手，别一上来乱改参数）】

    CPU  →  连接池  →  DB 慢查询  →  外部 LLM 延迟
     ①       ②          ③              ④

  ① 先看 CPU（top / docker stats）：
     - 现象：后端容器 CPU 长期 > 80%，QPS 却上不去 → 计算/异步没做对。
     - 调整：提高 uvicorn --workers（≈ CPU 核数 × 2 + 1）；
       把 CSV 入库、向量化等重任务丢给 Celery；CPU 密集别用异步硬扛（GIL）。

  ② 再看数据库连接池：
     - 现象：日志出现 “QueuePool limit ... timed out” 或 “TimeoutError”，
       DB 实际连接数却不高、请求都在排队等连接。
     - 调整：适度调大 pool_size / max_overflow，但必须保证
       workers × (pool_size+max_overflow) < MySQL max_connections。

  ③ 再看 DB 慢查询（slow_query_log / EXPLAIN）：
     - 现象：CPU 不高、连接不紧张，但接口 RT 抖动大，DB 进程 IO 高。
     - 调整：给 where/order by 字段加索引，避免全表扫描，必要时读写分离。

  ④ 最后看外部 LLM / 地图 API 延迟：
     - 现象：后端 CPU 很低、DB 很闲，但聊天接口就是慢（秒级）。
     - 原因：瓶颈在 DashScope/高德 等第三方，不在本项目。
     - 调整：对 LLM 结果做缓存、加超时与限流降级、提高异步并发即可，
       不要盲目加后端机器。


【各瓶颈症状速查表】
  症状                                  → 大概率瓶颈      → 先调什么
  ---------------------------------------------------------------------------
  后端 CPU 打满、QPS 封顶               → 计算瓶颈/worker  → 加 worker、重任务下沉 Celery
  QueuePool timeout、请求排队          → 连接池耗尽       → pool_size/max_overflow（注意 MySQL 上限）
  连接不高但 RT 抖动、DB IO 高          → 慢查询           → 加索引、EXPLAIN 优化 SQL
  CPU/DB 都闲，聊天就是慢               → 外部 LLM/地图    → 缓存、超时、限流降级
  Redis 报 OOM / 命中率低               → 缓存策略         → maxmemory-policy、key 设计
  SSE 消息一条一条卡出来、不流式        → Nginx 缓冲       → 确认 proxy_buffering off
  报错 Too many connections             → MySQL 连接数     → 降 worker 或连接池，升 max_connections
=====================================================================
"""

import random

from locust import HttpUser, between, task, events


# 压测用固定账号（与 sql/init.sql 中种子用户一致）
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin123"


class UserBehavior(HttpUser):
    """模拟一个登录后持续使用客服后台的虚拟用户。"""

    # 每个任务之间随机等待 1~3 秒，模拟真人思考/阅读时间
    wait_time = between(1, 3)

    def on_start(self):
        """
        每个虚拟用户启动时执行一次：登录拿 token，后续请求都带上。
        Locust 默认会把 status>=400 的响应自动记为失败，这里只需取 token。
        """
        # OAuth2 密码模式：必须用 form 表单（application/x-www-form-urlencoded）
        # 传 username / password，不能用 JSON body。
        resp = self.client.post(
            "/api/auth/login",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            name="/api/auth/login",
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")
        else:
            # 登录失败：置空 token，后续鉴权请求会自然打出 401 失败，便于排查
            self.token = ""

    def _auth_headers(self):
        """构造带 Bearer Token 的请求头。"""
        token = getattr(self, "token", "")
        return {"Authorization": f"Bearer {token}"}

    @task(3)
    def chat_stream(self):
        """
        聊天查询（SSE 流式）——权重最高(3)，是系统最核心、最慢的接口。
        关键：stream=True 保持长连接，逐行读取 SSE 帧，不能一次性读完整 body。
        """
        payload = {
            "conversation_id": 1,
            "customer_id": 1,
            "query": random.choice(
                [
                    "扫地机器人怎么保养",
                    "滤网多久换一次",
                    "机器卡住了怎么办",
                    "怎么连接WiFi",
                    "边刷不转了什么原因",
                ]
            ),
        }

        # catch_response=True：手动控制成功/失败标记，方便对流式结果做校验
        with self.client.post(
            "/api/chat/stream",
            json=payload,
            headers=self._auth_headers(),
            stream=True,
            catch_response=True,
            name="/api/chat/stream",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"聊天接口 status={resp.status_code}, body={resp.text[:200]}")
                return

            # 逐行消费 SSE 流（每行可能是 b'data: {...}' 或空行）
            event_count = 0
            try:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    event_count += 1
                    # 这里不解析内容，只验证流能持续吐数据；
                    # 解析业务字段可自行 decode(line) 后处理。
            except Exception as e:  # 网络中断/对端提前关闭
                resp.failure(f"SSE 流读取异常: {e}")
                return

            if event_count == 0:
                resp.failure("SSE 连接成功但没有收到任何数据帧")

    @task(2)
    def list_customers(self):
        """客户列表（普通 GET，带鉴权）——权重 2。"""
        self.client.get(
            "/api/customers",
            headers=self._auth_headers(),
            name="/api/customers",
        )

    @task(1)
    def list_tools(self):
        """工具列表——权重 1。"""
        self.client.get(
            "/api/tools",
            headers=self._auth_headers(),
            name="/api/tools",
        )

    @task(1)
    def list_datasets(self):
        """数据集列表——权重 1。"""
        self.client.get(
            "/api/datasets",
            headers=self._auth_headers(),
            name="/api/datasets",
        )


# 可选：压测结束后打印一行汇总，方便在 CI 里看结果
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats
    total = stats.total
    duration = max((stats.last_request_timestamp or 0) - (stats.start_time or 0), 1)
    p95 = total.get_response_time_percentile(0.95) or 0.0
    print(
        f"\n[压测结束] 总请求={total.num_requests} "
        f"失败={total.num_failures} "
        f"平均RT={total.avg_response_time:.1f}ms "
        f"P95={p95:.1f}ms "
        f"RPS={total.num_requests / duration:.1f}"
    )
