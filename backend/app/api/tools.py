"""自定义工具管理路由：业务校验与热加载都在 services/tool_service.py，本层只做 HTTP 收发。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.custom_tool import (
    CustomToolCreate,
    CustomToolResponse,
    CustomToolUpdate,
    ToolTestRequest,
    ToolTestResponse,
)
from app.services.tool_service import ToolService

router = APIRouter()


@router.get("")
async def list_tools(
    enabled_only: bool = Query(default=False, description="只返回已启用的工具"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """工具列表"""
    items = await ToolService.list_tools(db, enabled_only=enabled_only)
    return ApiResponse(data=[CustomToolResponse.model_validate(t) for t in items])


@router.get("/{tool_id}", response_model=ApiResponse[CustomToolResponse])
async def get_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """工具详情"""
    # bug 修复：原实现绕过 service 层直接 db.get(CustomTool, ...)，
    # 与其他接口分层不一致；改为走 ToolService.get_tool。
    tool = await ToolService.get_tool(db, tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")
    return ApiResponse(data=CustomToolResponse.model_validate(tool))


@router.post("", response_model=ApiResponse[CustomToolResponse], status_code=status.HTTP_201_CREATED)
async def create_tool(
    obj: CustomToolCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建工具定义"""
    # bug 修复：原实现传 obj.model_dump()（dict），而 service 需要 Schema 对象
    # （内部要访问 obj_in.tool_type 等属性），传 dict 会直接 AttributeError 崩溃。
    try:
        tool = await ToolService.create_tool(db, obj)
    except ValueError as e:
        # service 层业务校验失败（重名/非法类型等）统一转成 400
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ApiResponse(data=CustomToolResponse.model_validate(tool), message="创建成功")


@router.put("/{tool_id}", response_model=ApiResponse[CustomToolResponse])
async def update_tool(
    tool_id: int,
    obj: CustomToolUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新工具定义"""
    # bug 修复：同 create_tool，service 需要 Schema 对象而非 dict；
    # 且原实现未捕获 ValueError，重名等校验失败会变成 500，这里补 400。
    try:
        tool = await ToolService.update_tool(db, tool_id, obj)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")
    return ApiResponse(data=CustomToolResponse.model_validate(tool), message="更新成功")


@router.delete("/{tool_id}", response_model=ApiResponse)
async def delete_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除工具"""
    ok = await ToolService.delete_tool(db, tool_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")
    return ApiResponse(message="删除成功")


@router.post("/{tool_id}/test", response_model=ApiResponse[ToolTestResponse])
async def test_tool(
    tool_id: int,
    body: ToolTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """在线测试工具：用给定参数真实执行一次"""
    # bug 修复：ToolService.test_tool 返回的就是 ToolTestResponse，
    # 原实现又包了一层 ToolTestResponse(success=True, result=str(result))，
    # 导致：1) result 变成 repr 字符串而非真实结果；2) 工具失败时 success 仍恒为 True。
    # service 内部已捕获全部异常并填好 success/result/error，直接透传即可。
    result = await ToolService.test_tool(db, tool_id, body.params)
    return ApiResponse(
        data=result,
        message="测试完成" if result.success else "测试失败",
    )
