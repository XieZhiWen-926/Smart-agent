"""
Redis 异步客户端 + 简单限流器。
- get_redis() 返回全局单例 redis.asyncio.Redis
- RateLimiter 基于固定窗口计数做接口限流
"""
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings
from app.utils.logger import logger

# 全局单例连接
_redis_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    """获取全局 Redis 异步客户端单例"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


class RateLimiter:
    """
    基于 Redis 的固定窗口限流器。
    is_allowed(key, limit, window)：window 秒内最多放行 limit 次。
    Redis 不可用时降级为放行（fail-open），避免缓存故障拖垮主流程。
    """

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self._r = redis_client or get_redis()

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """
        :param key: 限流维度键，例如 "chat:user:{user_id}"
        :param limit: 窗口内最大请求数
        :param window: 窗口大小（秒）
        :return: True 放行 / False 限流

        原理（固定窗口计数）：
        incr 每次访问给计数器 +1；第一次访问时顺便设置过期时间（即窗口长度）。
        窗口内计数超过 limit 就拒绝。窗口到期后 key 自动过期，计数清零重来。
        """
        rkey = f"ratelimit:{key}"
        try:
            current = await self._r.incr(rkey)
            if current == 1:
                # 第一次访问时设置过期时间，开启新窗口
                await self._r.expire(rkey, window)
            return current <= limit
        except Exception as e:  # noqa: BLE001
            # fail-open（失败放行）：Redis 挂了时宁可不限流，也不能让全站不可用
            logger.warning(f"Redis 限流检查失败，降级放行：{e}")
            return True
