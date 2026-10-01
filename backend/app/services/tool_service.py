"""
工具业务逻辑层：工具 CRUD + 在线测试。
- 校验 name 唯一性、parameters_schema 合法性；
- 任何写操作（增/改/删）后都调用 tool_registry.reload() 热更新 Agent 工具集；
- test_tool 支持按工具类型真实执行一次，python_func 加超时保护。

上游：api/tools.py 路由；下游：repositories/tool_repo.py、agent/tools/dynamic_tools.py。
约定：create_tool/update_tool 的入参是 Pydantic Schema 对象（不是 dict），
校验失败抛 ValueError，由路由层转成 HTTP 400。
"""
import asyncio
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_tool import CustomTool
from app.repositories.tool_repo import ToolRepository
from app.schemas.custom_tool import (
    CustomToolCreate,
    CustomToolUpdate,
    ToolTestResponse,
)
from app.utils.logger import logger

# 延迟导入避免循环依赖（dynamic_tools 又 import base_tools/map_tools）
from app.agent.tools.dynamic_tools import tool_registry


# 允许的工具类型白名单
_ALLOWED_TOOL_TYPES = {"builtin", "map_amap", "map_baidu", "python_func", "http_api"}


class ToolService:
    """自定义工具业务逻辑"""

    # ----------------------------------------------------------
    # 查询
    # ----------------------------------------------------------
    @staticmethod
    async def list_tools(db: AsyncSession, enabled_only: bool = False) -> list[CustomTool]:
        """列出工具列表"""
        return await ToolRepository.get_all(db, enabled_only=enabled_only)

    @staticmethod
    async def get_tool(db: AsyncSession, tool_id: int) -> Optional[CustomTool]:
        """按 ID 查询单个工具，不存在返回 None（路由层转成 404）"""
        return await ToolRepository.get_by_id(db, tool_id)

    # ----------------------------------------------------------
    # 创建
    # ----------------------------------------------------------
    @staticmethod
    async def create_tool(db: AsyncSession, obj_in: CustomToolCreate) -> CustomTool:
        """创建工具：校验唯一性与 schema，落库后热加载。"""
        # 1. 工具类型白名单
        if obj_in.tool_type not in _ALLOWED_TOOL_TYPES:
            raise ValueError(
                f"非法 tool_type={obj_in.tool_type}，允许值：{_ALLOWED_TOOL_TYPES}"
            )

        # 2. name 唯一性
        existed = await ToolRepository.get_by_name(db, obj_in.name)
        if existed is not None:
            raise ValueError(f"工具名 {obj_in.name} 已存在")

        # 3. parameters_schema 必须是合法 JSON Schema（至少是 dict，且有 properties）
        ps = obj_in.parameters_schema or {}
        if not isinstance(ps, dict) or "properties" not in ps:
            raise ValueError("parameters_schema 必须是合法 JSON Schema（含 properties 字段）")

        # model_dump()：Pydantic v2 的方法，把 Schema 对象转成 dict（旧版叫 .dict()）
        row = await ToolRepository.create(db, obj_in.model_dump())
        logger.info(f"创建工具成功：id={row.id} name={row.name} type={row.tool_type}")

        # 4. 热更新 Agent 工具集
        await tool_registry.reload()
        return row

    # ----------------------------------------------------------
    # 更新
    # ----------------------------------------------------------
    @staticmethod
    async def update_tool(
        db: AsyncSession,
        tool_id: int,
        obj_in: CustomToolUpdate,
    ) -> Optional[CustomTool]:
        """更新工具：部分字段更新，落库后热加载。"""
        row = await ToolRepository.get_by_id(db, tool_id)
        if row is None:
            return None

        update_data = obj_in.model_dump(exclude_unset=True)

        # 如果改了 name，要校验新名字不冲突
        if "name" in update_data and update_data["name"] != row.name:
            dup = await ToolRepository.get_by_name(db, update_data["name"])
            if dup is not None:
                raise ValueError(f"工具名 {update_data['name']} 已存在")

        # 如果改了 tool_type，校验白名单
        if "tool_type" in update_data and update_data["tool_type"] not in _ALLOWED_TOOL_TYPES:
            raise ValueError(f"非法 tool_type={update_data['tool_type']}")

        # 如果改了 parameters_schema，校验一下
        if "parameters_schema" in update_data and update_data["parameters_schema"] is not None:
            ps = update_data["parameters_schema"]
            if not isinstance(ps, dict) or "properties" not in ps:
                raise ValueError("parameters_schema 必须是合法 JSON Schema（含 properties 字段）")

        updated = await ToolRepository.update(db, tool_id, update_data)
        logger.info(f"更新工具成功：id={tool_id}")
        await tool_registry.reload()
        return updated

    # ----------------------------------------------------------
    # 删除
    # ----------------------------------------------------------
    @staticmethod
    async def delete_tool(db: AsyncSession, tool_id: int) -> bool:
        """删除工具，落库后热加载。"""
        ok = await ToolRepository.delete(db, tool_id)
        if ok:
            logger.info(f"删除工具成功：id={tool_id}")
            await tool_registry.reload()
        return ok

    # ----------------------------------------------------------
    # 在线测试
    # ----------------------------------------------------------
    @staticmethod
    async def test_tool(db: AsyncSession, tool_id: int, params: dict[str, Any]) -> ToolTestResponse:
        """在线执行一次工具测试，返回结果。

        - 不依赖工具是否 is_enabled，直接按 DB 记录构建一个临时 Tool 执行；
        - 对 python_func 类型加 asyncio.wait_for 超时保护（默认 5 秒，可由 config.timeout 覆盖）。
        """
        row = await ToolRepository.get_by_id(db, tool_id)
        if row is None:
            return ToolTestResponse(success=False, result="", error=f"工具 id={tool_id} 不存在")

        try:
            # 用注册器的构建逻辑临时造一个 Tool（不落库、不污染全局列表）
            tool_obj = tool_registry._build_tool(row)  # noqa: SLF001
            if tool_obj is None:
                return ToolTestResponse(success=False, result="", error="工具构建失败")

            # 取超时配置
            config = row.config or {}
            timeout = config.get("timeout", 10)

            # 统一走 LangChain Tool 的 ainvoke（异步调用）。
            # asyncio.wait_for：给 await 加超时，超时抛 asyncio.TimeoutError，
            # 防止 python_func 死循环或 http_api 卡死拖住整个请求。
            # 说明：两个分支目前逻辑相同（都加超时），保留 if 是为 python_func
            # 后续可能加更严格的资源限制留的扩展位。
            if row.tool_type == "python_func":
                result = await asyncio.wait_for(tool_obj.ainvoke(params), timeout=timeout)
            else:
                result = await asyncio.wait_for(tool_obj.ainvoke(params), timeout=timeout)

            return ToolTestResponse(success=True, result=str(result), error=None)

        except asyncio.TimeoutError:
            logger.warning(f"工具 {row.name} 测试超时（>{timeout}s）")
            return ToolTestResponse(success=False, result="", error=f"工具执行超时（>{timeout}秒）")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"工具 {row.name} 测试失败")
            return ToolTestResponse(success=False, result="", error=str(e))


__all__ = ["ToolService"]
