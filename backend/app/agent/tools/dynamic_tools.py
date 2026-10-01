"""
动态工具加载注册器。
- 启动时从 MySQL custom_tools 表加载所有 is_enabled=True 的工具；
- 按 tool_type 动态构建 LangChain Tool 对象；
- 提供 reload() 给工具 CRUD 后热更新；
- 模块级单例 tool_registry 供 Agent / API 层直接使用。

【安全警告】python_func 类型允许管理员在 DB 中写入任意 Python 代码片段，
虽然本模块对 exec 的命名空间做了最小化白名单（无 os/sys/subprocess/open/网络），
但仍存在不可完全消除的风险，生产环境应：
  1) 严格限制谁能写 custom_tools 记录；
  2) 对 python_func 工具加调用超时与资源配额；
  3) 必要时关闭该类型，仅允许 http_api。
"""
import asyncio
import json
from typing import Any, Callable

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, create_model

from app.database import AsyncSessionLocal
from app.models.custom_tool import CustomTool
from app.utils.logger import logger

from app.agent.tools import base_tools, map_tools


# ---------- 安全沙箱白名单（python_func 专用）----------
# 只暴露纯计算常用内置函数，显式剔除 os/sys/subprocess/open/__import__ 等危险入口。
# 注意：即使这样，exec 仍非真正的安全沙箱，仅作第一道防线。
_SAFE_BUILTINS: dict[str, Callable] = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "print": print,
    "range": range,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
}


# ---------- 工具名 -> 内置/地图 Tool 对象 的索引 ----------
def _builtin_tool_index() -> dict[str, Any]:
    """把 base_tools / map_tools 中所有 @tool 装饰的工具按 name 建索引。

    【★ 为什么用 isinstance(obj, BaseTool) 而不是 callable(obj)？★】
    LangChain 1.x 把 BaseTool 的 __call__ 从实例协议里移除了，导致
    @tool 装饰出来的工具对象虽然功能完好，但 callable(工具) 返回 False。
    如果沿用老写法 `hasattr(obj, "name") and callable(obj)` 做过滤，
    索引会变成空的 → 启动日志出现
        "builtin 工具 rag_summarize 未在代码中找到，跳过"
        "动态工具注册完成，共 0 个可用工具"
    结果是 Agent 手里一个工具都没有，什么工具都不会调用。
    isinstance 判断的是类型，不受实例协议变化影响，是版本稳定的正确写法。
    """
    idx: dict[str, Any] = {}
    for mod in (base_tools, map_tools):
        # dir(mod) 列出模块里所有名字，getattr 取出对应对象——这就是"反射"，
        # 不用提前知道模块里定义了哪些工具，运行时自动发现
        for name in dir(mod):
            obj = getattr(mod, name)
            # LangChain @tool 装饰后得到 BaseTool 的子类实例，带 .name 属性
            if isinstance(obj, BaseTool):
                idx[obj.name] = obj
    return idx


_BUILTIN_INDEX: dict[str, Any] = _builtin_tool_index()


# ---------- 把 JSON Schema 动态转成 Pydantic 模型 ----------
# (类型, ...) 里的 "..." 是 Python 的 Ellipsis 字面量，在 pydantic 里表示"必填"
_JSON_TYPE_MAP = {
    "string": (str, ...),
    "integer": (int, ...),
    "number": (float, ...),
    "boolean": (bool, ...),
    "array": (list, ...),
    "object": (dict, ...),
}


def _build_args_model(parameters_schema: dict, tool_name: str) -> type[BaseModel]:
    """根据 JSON Schema 动态构建一个 pydantic Args 模型。

    仅支持常见 scalar/array/object 类型；required 字段设为必填，其余可选。

    【为什么要动态建模型？】LangChain 的 StructuredTool 需要一个 pydantic
    模型来描述"这个工具接收什么参数"，既做校验，也生成给大模型看的参数说明。
    工具是存在数据库里的，参数结构各不相同，只能在运行时动态创建。
    """
    properties = parameters_schema.get("properties", {}) or {}
    required = set(parameters_schema.get("required", []) or [])

    fields: dict[str, Any] = {}
    for prop_name, prop_def in properties.items():
        json_type = prop_def.get("type", "string")
        py_type, _ = _JSON_TYPE_MAP.get(json_type, (str, ...))
        # 必填字段默认值为 ...（Ellipsis），可选字段默认 None
        default = ... if prop_name in required else None
        # 描述写进 Field description，便于 LLM 理解
        fields[prop_name] = (py_type, default)

    # create_model 是 pydantic 的"动态建类"函数：运行时才造出一个模型类
    model = create_model(f"{tool_name}_args", **fields)
    return model


def _validate_params(params: dict, parameters_schema: dict) -> None:
    """用 JSON Schema 做最基础的参数校验（必填字段存在）。"""
    required = parameters_schema.get("required", []) or []
    missing = [k for k in required if k not in params]
    if missing:
        raise ValueError(f"缺少必填参数：{', '.join(missing)}")


class DynamicToolRegistry:
    """动态工具注册器：从 DB 加载并构建 LangChain Tool 列表。"""

    def __init__(self) -> None:
        self._tools: list[Any] = []
        self._loaded = False

    # ----------------------------------------------------------
    # 从 DB 加载
    # ----------------------------------------------------------
    async def load_from_db(self) -> None:
        """查询 custom_tools 表中所有启用的工具，逐个构建 LangChain Tool。"""
        loaded: list[Any] = []

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            stmt = select(CustomTool).where(CustomTool.is_enabled.is_(True))
            result = await db.execute(stmt)
            rows = result.scalars().all()

        logger.info(f"动态工具加载：DB 中启用工具 {len(rows)} 个")

        for row in rows:
            try:
                tool_obj = self._build_tool(row)
                if tool_obj is not None:
                    loaded.append(tool_obj)
            except Exception as e:  # noqa: BLE001
                logger.error(f"工具 {row.name} 构建失败，跳过：{e}")

        self._tools = loaded
        self._loaded = True
        logger.info(f"动态工具注册完成，共 {len(loaded)} 个可用工具")

    def _build_tool(self, row: CustomTool) -> Any | None:
        """根据 tool_type 分发构建对应类型的 LangChain Tool。"""
        ttype = row.tool_type
        name = row.name
        desc = row.description or name
        params_schema = row.parameters_schema or {}
        config = row.config or {}

        # ---- 1. 内置工具：直接从 base_tools / map_tools 索引取 ----
        if ttype == "builtin":
            tool_obj = _BUILTIN_INDEX.get(name)
            if tool_obj is None:
                logger.warning(f"builtin 工具 {name} 未在代码中找到，跳过")
                return None
            return tool_obj

        # ---- 2. 高德/百度地图工具：从 map_tools 索引取 ----
        if ttype in ("map_amap", "map_baidu"):
            tool_obj = _BUILTIN_INDEX.get(name)
            if tool_obj is None:
                logger.warning(f"map 工具 {name} 未在 map_tools 中找到，跳过")
                return None
            return tool_obj

        # ---- 3. python_func：在受限命名空间 exec 出 run() 函数 ----
        if ttype == "python_func":
            return self._build_python_func_tool(name, desc, params_schema, config)

        # ---- 4. http_api：包装成 httpx 调用工具 ----
        if ttype == "http_api":
            return self._build_http_tool(name, desc, params_schema, config)

        logger.warning(f"未知 tool_type={ttype}，工具 {name} 跳过")
        return None

    # ----------------------------------------------------------
    # python_func 工具（受限沙箱）
    # ----------------------------------------------------------
    def _build_python_func_tool(
        self,
        name: str,
        desc: str,
        params_schema: dict,
        config: dict,
    ) -> StructuredTool:
        """从 config['code'] 读取函数源码，exec 后包装成 Tool。

        【安全】exec 的 globals 只暴露 _SAFE_BUILTINS，无 import os/sys/subprocess/open。
        代码里必须定义一个 run(...) 函数，返回字符串或可序列化对象。
        """
        code = config.get("code", "")
        if not code:
            raise ValueError(f"python_func 工具 {name} 缺少 config.code")

        # 受限命名空间：__builtins__ 只放白名单函数。
        # exec 的第二个参数是"全局命名空间"，把 __builtins__ 替换成白名单后，
        # 被 exec 的代码就用不了 open/os/import 等危险能力。
        safe_globals: dict[str, Any] = {"__builtins__": dict(_SAFE_BUILTINS)}
        local_ns: dict[str, Any] = {}

        # compile 把源码编译成字节码，exec 在上述受限命名空间里执行它
        exec(compile(code, f"<dynamic:{name}>", "exec"), safe_globals, local_ns)  # noqa: S102
        user_run = local_ns.get("run")
        if user_run is None or not callable(user_run):
            raise ValueError(f"python_func 工具 {name} 的代码必须定义 run() 函数")

        args_model = _build_args_model(params_schema, name)

        # 闭包：_wrapper 内部"记住"了外层的 user_run / params_schema，
        # 即使本函数返回后，这些变量依然可用
        async def _wrapper(**kwargs: Any) -> str:
            # 参数校验
            _validate_params(kwargs, params_schema)
            try:
                # 同步函数直接 run，异步函数 await
                result = user_run(**kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, (dict, list)):
                    return json.dumps(result, ensure_ascii=False)
                return str(result)
            except Exception as e:  # noqa: BLE001
                return f"python_func 工具执行失败：{e}"

        return StructuredTool.from_function(
            func=None,
            coroutine=_wrapper,
            name=name,
            description=desc,
            args_schema=args_model,
        )

    # ----------------------------------------------------------
    # http_api 工具
    # ----------------------------------------------------------
    def _build_http_tool(
        self,
        name: str,
        desc: str,
        params_schema: dict,
        config: dict,
    ) -> StructuredTool:
        """从 config 读取 url/method/headers，包装成 httpx 调用工具。

        config 示例：
        {
            "url": "https://api.example.com/order",
            "method": "GET",
            "headers": {"Authorization": "Bearer xxx"},
            # path/query 参数占位符用 {param_name}，运行时从 kwargs 替换
        }
        """
        url = config.get("url", "")
        method = (config.get("method") or "GET").upper()
        headers = config.get("headers") or {}
        timeout = config.get("timeout", 10)

        if not url:
            raise ValueError(f"http_api 工具 {name} 缺少 config.url")

        args_model = _build_args_model(params_schema, name)

        async def _wrapper(**kwargs: Any) -> str:
            _validate_params(kwargs, params_schema)
            # 用 kwargs 填充 URL 中的 {占位符}；f"{{{k}}}" 就是字符串 "{" + k + "}"
            final_url = url.format(**{k: v for k, v in kwargs.items() if f"{{{k}}}" in url})
            # 其余参数作为 query（GET）或 body（POST/PUT）
            payload = {k: v for k, v in kwargs.items() if f"{{{k}}}" not in url}

            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if method == "GET":
                        resp = await client.get(final_url, params=payload, headers=headers)
                    else:
                        resp = await client.request(method, final_url, json=payload, headers=headers)
                    resp.raise_for_status()
                    # 尝试 JSON 格式化返回，否则返回文本
                    try:
                        data = resp.json()
                        return json.dumps(data, ensure_ascii=False)
                    except Exception:  # noqa: BLE001
                        return resp.text
            except Exception as e:  # noqa: BLE001
                logger.exception(f"http_api 工具 {name} 调用失败")
                return f"HTTP API 调用失败：{e}"

        return StructuredTool.from_function(
            func=None,
            coroutine=_wrapper,
            name=name,
            description=desc,
            args_schema=args_model,
        )

    # ----------------------------------------------------------
    # 对外接口
    # ----------------------------------------------------------
    def get_tools(self) -> list[Any]:
        """返回当前已加载的所有 LangChain Tool 列表。"""
        return self._tools

    async def reload(self) -> None:
        """工具增删改后调用，重新从 DB 全量加载。"""
        logger.info("动态工具注册器 reload ...")
        await self.load_from_db()


# ---------- 模块级单例 ----------
tool_registry = DynamicToolRegistry()
