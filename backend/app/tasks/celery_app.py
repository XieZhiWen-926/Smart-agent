"""
Celery 应用实例。
- broker / backend 统一从 settings 读取（Redis）
- 序列化用 JSON，时区为 Asia/Shanghai
- include 显式注册任务模块，worker 启动时自动发现

【Celery 是干什么的？】
把"CSV 导入、记忆抽取"这种耗时重活丢给后台 worker 进程慢慢做，
Web 请求立刻返回，不被拖慢（削峰填谷）。本文件创建 Celery 应用本体，
真正的任务定义在同目录的 dataset_tasks.py / memory_tasks.py。
"""
from celery import Celery

from app.config import settings

celery = Celery(
    "smart_agent",
    broker=settings.celery_broker_url,       # 任务队列放哪（Redis db1）
    backend=settings.celery_result_backend,  # 任务结果存哪（Redis db2）
    include=["app.tasks.dataset_tasks", "app.tasks.memory_tasks"],
)

celery.conf.update(
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],      # 只接受 JSON 格式的消息，防止恶意序列化攻击
    task_track_started=True,      # 记录任务"已开始"状态，前端能区分排队/执行中
    # 任务超时与重试的基础配置
    task_time_limit=600,          # 硬超时 600s：到点强杀，防止任务跑飞
    task_soft_time_limit=540,     # 软超时 540s：先抛异常给任务一个收尾机会
)
