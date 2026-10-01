"""认证路由：登录 / 注册 / 获取当前用户信息。

说明：users 表目前只有这三个简单操作，项目里尚未单建 UserService/UserRepository，
故本文件直接写了少量查询；其他业务模块（客户/工具/数据集…）都走标准四层分层。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import UserCreate, UserResponse
from app.schemas.common import ApiResponse
from app.utils.security import create_access_token, hash_password, verify_password

router = APIRouter()


@router.post("/login")
async def login(
    # OAuth2PasswordRequestForm：FastAPI 内置的表单解析器，
    # 自动从请求表单里取 username / password 两个字段
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    OAuth2 密码模式登录：表单字段 username / password。
    成功返回 access_token（bearer）。
    """
    # SQLAlchemy 2.0：select() 构造查询 + await db.execute 执行 + scalar_one_or_none 取单行
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register", response_model=ApiResponse[UserResponse], status_code=status.HTTP_201_CREATED)
async def register(
    obj: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新用户（管理员使用，需登录；首个管理员由初始化脚本/种子数据创建）"""
    exists = await db.execute(select(User).where(User.username == obj.username))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    user = User(
        username=obj.username,
        hashed_password=hash_password(obj.password),
        full_name=obj.full_name,
        role=obj.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ApiResponse(data=UserResponse.model_validate(user), message="注册成功")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserResponse.model_validate(current_user)
