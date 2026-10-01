"""
FastAPI 依赖注入集中处：
- get_db：直接复用 database.py 的请求级异步 session
- get_current_user：从 Bearer Token 解析 JWT 并查出当前用户

【什么是 Depends 依赖注入】路由参数里写 `db: AsyncSession = Depends(get_db)`，
FastAPI 就会在调用路由前先执行 get_db()，把它的返回值塞进 db 参数。
依赖还能嵌套：get_current_user 自己也依赖 oauth2_scheme 和 get_db，
FastAPI 会自动按顺序"串"起来执行——路由函数只管用，不用关心怎么来的。
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db  # noqa: F401  (对外 re-export)
from app.models.user import User
from app.utils.security import decode_access_token

# OAuth2 密码流：tokenUrl 指向登录接口，Swagger 会据此弹出登录框
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    依赖：校验 JWT 并返回当前登录用户。
    任何环节失败都抛 401，要求前端重新登录。
    """
    credential_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未认证或凭证已失效",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credential_exception

    username = payload.get("sub")
    if not username:
        raise credential_exception

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credential_exception

    return user


# 别名：语义上等价，路由里写哪个都行
async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """当前活跃用户（与 get_current_user 等价，保留别名便于语义阅读）"""
    return current_user
