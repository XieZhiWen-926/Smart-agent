"""安全工具：JWT 令牌生成/验证 + 密码哈希
被 app/api/auth.py（登录注册）和 app/api/deps.py（鉴权依赖）使用。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# 密码哈希上下文（bcrypt 算法）。
# 【为什么不明文/MD5 存密码？】数据库泄露时明文=直接完蛋，MD5 易被彩虹表破解；
# bcrypt 自带盐且计算慢，专门抗暴力破解。
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """明文密码 -> bcrypt 哈希（每次结果不同，因为盐是随机的，但仍可校验）"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    生成 JWT 访问令牌。
    data 中放入 {"sub": username} 等声明。

    【JWT 是什么？】一段经过签名的字符串，服务端用它证明"你登录过"。
    无状态：服务端不用存 session，天然支持多实例水平扩展。
    """
    to_encode = data.copy()
    # exp = 过期时间（UTC），超时后令牌自动失效
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    """
    验证并解码 JWT 令牌。
    失败返回 None，调用方据此返回 401。
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        # 签名不对、过期、格式错误都会落到 JWTError，统一按"未登录"处理
        return None
