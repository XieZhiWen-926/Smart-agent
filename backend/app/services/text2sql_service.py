"""
Text2SQL 服务
==============
自然语言 -> SQL 生成 + 安全校验 + 执行 + 结果转自然语言。

安全设计原则：
    - 生成的 SQL 在执行前必须经过 validate_sql 六道校验
    - 只允许 SELECT，禁止一切写操作和危险函数
    - 表名走白名单，防止越权查询其他表
    - 强制 LIMIT 100，防止全表扫描拖垮数据库

上游：services/data_router.py 的 text2sql 分支；下游：大模型（生成 SQL）+ MySQL（执行）。
为什么安全校验这么严：SQL 是 LLM 生成的，不可信，直接执行可能被注入删库。
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.model.factory import get_chat_model
from app.models.dataset import Dataset
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# 安全校验常量
# ---------------------------------------------------------------------------
# 禁止出现的 SQL 关键字（写操作 / DDL / 危险函数）
_FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "RENAME", "INTO",
    "REPLACE", "CALL", "EXECUTE", "EXEC", "SET", "HANDLER",
    "LOAD_FILE", "OUTFILE", "DUMPFILE", "BENCHMARK", "SLEEP",
    "INFORMATION_SCHEMA", "MYSQL", "PERFORMANCE_SCHEMA",
]

# 多语句分隔符
_MULTI_STMT_PATTERN = re.compile(r";\s*\S")

# 提取表名：FROM `table` / JOIN `table`
_TABLE_PATTERN = re.compile(
    r"(?:FROM|JOIN)\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?",
    re.IGNORECASE,
)


class Text2SQLService:
    """Text2SQL 生成与安全执行"""

    # ------------------------------------------------------------------
    # SQL 生成
    # ------------------------------------------------------------------
    @staticmethod
    async def generate_sql(
        db: AsyncSession,
        query: str,
        dataset: Dataset,
    ) -> tuple[str, float]:
        """
        根据用户自然语言问题和数据集 Schema 生成 SQL。

        :param query: 用户问题
        :param dataset: 数据集元数据（含 columns_meta）
        :return: (生成的 SQL, 置信度 0~1)
        """
        # 构建列描述：物理名 -> 中文原名(类型)
        col_lines = []
        for cm in dataset.columns_meta:
            col_lines.append(
                f"  - `{cm['physical_name']}` (原名: {cm['original_name']}, 类型: {cm['dtype']})"
            )
        col_desc = "\n".join(col_lines)

        # few-shot 示例（通用，不依赖具体业务数据）
        few_shots = (
            "示例 1：\n"
            f"  表名: `{dataset.table_name}`, 列见上方\n"
            "  问题: 总共有多少条记录？\n"
            f"  SQL: SELECT COUNT(*) AS total FROM `{dataset.table_name}` LIMIT 1;\n\n"
            "示例 2：\n"
            f"  问题: 按某列分组统计数量，取前10\n"
            f"  SQL: SELECT `col_0`, COUNT(*) AS cnt FROM `{dataset.table_name}` "
            "GROUP BY `col_0` ORDER BY cnt DESC LIMIT 10;\n\n"
            "示例 3：\n"
            "  问题: 筛选某列包含关键词的记录\n"
            f"  SQL: SELECT * FROM `{dataset.table_name}` WHERE `col_1` LIKE '%关键词%' LIMIT 20;"
        )

        prompt = (
            "你是一个 MySQL SQL 生成器。请根据用户问题生成一条只读 SELECT 语句。\n"
            "规则：\n"
            "1. 只输出 SQL 本身，不要解释、不要 markdown 代码块\n"
            "2. 表名和列名必须用反引号包裹\n"
            "3. 必须带 LIMIT（不超过 100）\n"
            "4. 只能用 SELECT，禁止任何写操作\n\n"
            f"表名: `{dataset.table_name}`\n"
            f"列信息:\n{col_desc}\n\n"
            f"{few_shots}\n\n"
            f"用户问题: {query}\n"
            "SQL:"
        )

        chat = get_chat_model()
        resp = await chat.ainvoke(prompt)   # ainvoke：LangChain 模型的异步调用方法
        # 不同模型返回类型不同，统一取文本内容
        raw_sql = resp.content if hasattr(resp, "content") else str(resp)

        # 清理：去掉 markdown 代码块标记和多余空白
        sql = raw_sql.strip()
        sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"^```\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.strip().rstrip(";").strip()

        # 置信度：简单规则——SQL 非空且包含 FROM 即认为基本可信
        confidence = 0.8 if "FROM" in sql.upper() else 0.3
        logger.info(f"Text2SQL 生成: query='{query}' -> sql='{sql}' (conf={confidence})")

        return sql, confidence

    # ------------------------------------------------------------------
    # 安全校验
    # ------------------------------------------------------------------
    @staticmethod
    def validate_sql(sql: str, allowed_tables: list[str]) -> tuple[bool, str]:
        """
        SQL 安全校验（六道关卡）。

        :param sql: 待校验 SQL
        :param allowed_tables: 允许查询的表名白名单
        :return: (是否合法, 错误信息)
        """
        if not sql or not sql.strip():
            return False, "SQL 为空"

        # 去除注释行和首尾空白，便于后续正则匹配
        cleaned = re.sub(r"--[^\n]*", " ", sql)       # 行注释
        cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)  # 块注释
        cleaned = cleaned.strip()

        # ---- 关卡 1：必须以 SELECT 开头 ----
        if not re.match(r"^\s*SELECT\b", cleaned, re.IGNORECASE):
            return False, "只允许 SELECT 查询"

        # ---- 关卡 2：禁止危险关键字 ----
        # 按单词边界匹配，避免误判列名里包含这些词
        upper = cleaned.upper()
        for kw in _FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{kw}\b", upper):
                # 例外：SELECT ... INTO OUTFILE 已经被 INTO 拦截
                # 但 SELECT 本身不禁止
                if kw == "SELECT":
                    continue
                return False, f"SQL 中包含禁止的关键字: {kw}"

        # ---- 关卡 3：禁止多语句（; 后面还有内容）----
        if _MULTI_STMT_PATTERN.search(cleaned):
            return False, "不允许多条 SQL 语句拼接"
        # 末尾单独一个分号没问题，但保险起见检查
        if cleaned.count(";") > 1:
            return False, "不允许多条 SQL 语句拼接"

        # ---- 关卡 4：禁止危险函数 ----
        dangerous_funcs = [
            "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
            "BENCHMARK", "SLEEP", "WAIT_FOR_EXECUTION",
            "EXECUTE", "EXEC(", "PREPARE", "DEALLOCATE",
        ]
        for func in dangerous_funcs:
            if func.upper() in upper:
                return False, f"SQL 中包含危险函数: {func}"

        # ---- 关卡 5：表名白名单校验 ----
        tables_in_sql = _TABLE_PATTERN.findall(cleaned)
        if not tables_in_sql:
            return False, "SQL 中未找到表名"
        for t in tables_in_sql:
            if t not in allowed_tables:
                return False, f"表 `{t}` 不在允许查询的表白名单中"

        # ---- 关卡 6：基本结构检查 ----
        # 必须有 FROM
        if not re.search(r"\bFROM\b", upper):
            return False, "SQL 缺少 FROM 子句"

        logger.debug(f"SQL 校验通过: {sql}")
        return True, ""

    # ------------------------------------------------------------------
    # 执行查询
    # ------------------------------------------------------------------
    @staticmethod
    async def execute_sql(
        db: AsyncSession,
        sql: str,
        dataset: Dataset,
    ) -> list[dict]:
        """
        校验通过后执行 SQL，自动追加 LIMIT 100。

        :raises ValueError: SQL 校验不通过
        :return: 查询结果字典列表
        """
        allowed = [dataset.table_name]
        ok, err = Text2SQLService.validate_sql(sql, allowed)
        if not ok:
            raise ValueError(f"SQL 安全校验失败: {err}")

        # 强制 LIMIT 100（如果 SQL 里没有 LIMIT）
        if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
            sql = sql.rstrip(";") + " LIMIT 100"

        logger.info(f"执行安全查询: {sql}")
        result = await db.execute(text(sql))
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 结果转自然语言
    # ------------------------------------------------------------------
    @staticmethod
    async def results_to_natural_language(
        query: str,
        sql: str,
        results: list[dict],
    ) -> str:
        """
        将 SQL 查询结果转为自然语言回答。

        :param query: 用户原始问题
        :param sql: 执行的 SQL
        :param results: 查询结果
        :return: 自然语言回答
        """
        if not results:
            return "查询已执行，但没有找到匹配的数据记录。"

        # 截断结果，避免 Prompt 过长（最多展示 20 行）
        preview = results[:20]
        results_str = "\n".join(str(r) for r in preview)
        total = len(results)

        prompt = (
            "请根据以下数据库查询结果，用简洁的中文回答用户问题。"
            "不要编造结果中没有的数据。如果结果为空就如实说没有。\n\n"
            f"用户问题: {query}\n"
            f"执行的 SQL: {sql}\n"
            f"查询结果（共 {total} 行，展示前 {len(preview)} 行）:\n{results_str}\n\n"
            "回答："
        )

        chat = get_chat_model()
        resp = await chat.ainvoke(prompt)
        answer = resp.content if hasattr(resp, "content") else str(resp)
        return answer.strip()
