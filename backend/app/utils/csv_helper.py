"""
CSV 读取工具模块
================
替代旧版手工 `line.split(",")` 的 CSV 解析方式。

旧代码 Bug 对比：
    旧实现：逐行 `line.strip().split(",")` 切分列。
    Bug 1：如果某个字段值里本身含逗号（如 `"北京市,朝阳区"`），会被错误切成两列。
    Bug 2：如果字段值里含换行符（如 `"客户反馈：\n第一次...\n第二次..."`），
            整行会被当成两行读取，导致列数错位、后续解析全部崩溃。
    新实现：使用 pandas.read_csv，底层调用 csv 模块，能正确识别引号包裹的
            逗号和换行，上述两种情况都不会出错。

同时负责：
    - 文件编码自动检测（UTF-8 / GBK / GB2312 等）
    - 中文表名 / 列名清洗为 MySQL 合规标识符
    - 列类型推断
"""
from __future__ import annotations

import hashlib
import re

import chardet
import pandas as pd


# ---------------------------------------------------------------------------
# 编码检测
# ---------------------------------------------------------------------------
def detect_encoding(file_path: str) -> str:
    """
    检测 CSV 文件编码。

    读取文件前 64KB 原始字节，用 chardet 做编码嗅探。
    对中文场景常见的 GBK / GB2312 做兜底处理。

    :param file_path: CSV 文件绝对路径
    :return: 编码名字符串，如 "utf-8" / "gbk"
    """
    with open(file_path, "rb") as f:
        raw = f.read(65536)  # 读前 64KB 足够判断编码

    if not raw:
        return "utf-8"

    result = chardet.detect(raw)
    encoding = result.get("encoding", "utf-8")

    # chardet 对中文常见编码的归一化处理
    encoding_upper = (encoding or "").upper()
    if encoding_upper in ("GB2312", "GB-2312"):
        # GB2312 是 GBK 的子集，统一用 GBK 读避免缺字
        return "gbk"
    if encoding_upper in ("GB18030", "GBK", "GB-1988"):
        return "gbk"
    if encoding_upper.startswith("UTF-8"):
        return "utf-8"
    if encoding_upper in ("ASCII",):
        return "ascii"

    # 兜底：尝试 utf-8-sig（带 BOM），再退回 utf-8
    return encoding.lower() if encoding else "utf-8"


# ---------------------------------------------------------------------------
# 安全读取 CSV
# ---------------------------------------------------------------------------
def read_csv_safely(file_path: str) -> tuple[pd.DataFrame, dict]:
    """
    安全读取 CSV 文件，自动处理编码与引号内特殊字符。

    关键说明：
        - pandas.read_csv 底层使用 Python 内置 csv 模块，
          能正确识别双引号包裹的逗号和换行符，
          这是替代旧版 `line.split(",")` 的核心原因。
        - dtype=str：全部按字符串读入，避免 pandas 自动推断类型导致
          数字前导零丢失（如 "00123" 变成 123）。类型推断交给
          infer_column_types 统一处理。

    :param file_path: CSV 文件绝对路径
    :return: (DataFrame, 列名映射信息 dict)
        列名映射信息形如：
        {
            "original_columns": ["用户ID", "用户名", ...],
            "physical_columns": ["col_0", "col_1", ...],
        }
    """
    encoding = detect_encoding(file_path)

    # 先用检测到的编码读；若带 BOM 则用 utf-8-sig 重试
    try:
        df = pd.read_csv(file_path, encoding=encoding, dtype=str)
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding="utf-8-sig", dtype=str)

    # 去除列名首尾空白
    df.columns = [str(c).strip() for c in df.columns]

    # 构建列名映射
    original_cols = list(df.columns)
    physical_cols = [sanitize_column_name(c, i) for i, c in enumerate(original_cols)]
    column_mapping = {
        "original_columns": original_cols,
        "physical_columns": physical_cols,
    }

    # 重命名 DataFrame 列为物理列名，方便后续 to_sql
    df.columns = physical_cols

    return df, column_mapping


# ---------------------------------------------------------------------------
# 表名 / 列名清洗
# ---------------------------------------------------------------------------
def sanitize_table_name(name: str) -> str:
    """
    将数据集名称清洗为 MySQL 合规表名。

    规则：
        1. 只保留 a-z / A-Z / 0-9 / 下划线
        2. 中文或特殊字符被剥离；若剥离后为空，则用 "ds" 占位
        3. 统一转小写
        4. 前面加 "ds_" 前缀（data set），后面追加原始名的 MD5 前 6 位
           保证不同中文数据集不会撞名

    示例：
        "用户使用记录"  -> "ds_ds_a1b2c3"
        "Sales_2024"    -> "ds_sales_2024_4f5e6d"

    :param name: 原始数据集名称（可能含中文）
    :return: 合规 MySQL 表名
    """
    # 只保留字母数字下划线（正则 [^...] 表示"除了这些以外的字符都删掉"）
    ascii_part = re.sub(r"[^a-zA-Z0-9_]", "", name)
    ascii_part = ascii_part.lower().strip("_")
    if not ascii_part:
        ascii_part = "ds"

    # 追加原始名 hash 前 6 位，避免不同中文数据集重名
    # md5 是哈希算法：任意输入算出固定长度摘要，同名必同值、异名几乎必异值
    name_hash = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]

    table_name = f"ds_{ascii_part}_{name_hash}"

    # MySQL 表名最长 64 字符，截断兜底
    if len(table_name) > 64:
        table_name = table_name[:64]

    return table_name


def sanitize_column_name(name: str, index: int) -> str:
    """
    将列名清洗为 MySQL 合规物理列名。

    规则：中文列名统一转为 `col_{index}`，原始中文名存入 columns_meta，
    通过 physical_name <-> original_name 的映射让 Text2SQL 理解。

    示例：
        ("用户ID", 0) -> "col_0"
        ("age", 1)    -> "col_1"   （英文列也统一编号，保持一致）

    :param name: 原始列名
    :param index: 列在 CSV 中的序号（从 0 开始）
    :return: 物理列名
    """
    return f"col_{index}"


# ---------------------------------------------------------------------------
# 列类型推断
# ---------------------------------------------------------------------------
def infer_column_types(df: pd.DataFrame) -> list[dict]:
    """
    推断 DataFrame 每列的逻辑类型。

    推断顺序（优先级从高到低）：
        bool  -> 列值仅包含 是/否、true/false、0/1 等
        date  -> 列值能被 pandas.to_datetime 成功解析
        int   -> 列值去掉空串后全部是整数
        float -> 列值去掉空串后全部是浮点数
        string-> 其余

    :param df: 全部按 str 读入的 DataFrame
    :return: [{"physical_name": "col_0", "original_name": "用户ID",
               "dtype": "string", "description": ""}, ...]
    """
    result: list[dict] = []
    physical_cols = list(df.columns)

    for idx, col in enumerate(physical_cols):
        series = df[col].dropna().astype(str).str.strip()
        # 去掉空串
        series_nonempty = series[series != ""]

        dtype = "string"  # 默认

        if len(series_nonempty) > 0:
            sample = series_nonempty.head(50)  # 抽样判断即可

            # ---- bool ----
            bool_set = {"是", "否", "true", "false", "0", "1", "yes", "no"}
            if all(v.lower() in bool_set for v in sample.str.lower()):
                dtype = "bool"
            else:
                # ---- int ----
                try:
                    # 允许带小数点后全零的情况，如 "1.0" -> int
                    # 正则 \.0+$ 表示"结尾处的 .0 / .00 ..."，先剥掉再判断
                    cleaned = sample.str.replace(r"\.0+$", "", regex=True)
                    # ^-?\d+$ 表示"可选负号 + 纯数字"，即整数字符串
                    if cleaned.str.match(r"^-?\d+$").all():
                        dtype = "int"
                    else:
                        # ---- float ----
                        try:
                            sample.astype(float)
                            dtype = "float"
                        except ValueError:
                            # ---- date ----
                            try:
                                pd.to_datetime(sample, format="mixed", errors="raise")
                                dtype = "date"
                            except (ValueError, TypeError):
                                dtype = "string"
                except Exception:
                    dtype = "string"

        result.append({
            "physical_name": col,
            "original_name": "",  # 由外部调用方填充
            "dtype": dtype,
            "description": "",
        })

    return result


# ---------------------------------------------------------------------------
# 类型映射：逻辑类型 -> MySQL DDL 类型
# ---------------------------------------------------------------------------
def dtype_to_mysql(dtype: str) -> str:
    """
    将推断出的逻辑类型映射为 MySQL DDL 列类型。

    :param dtype: "string" / "int" / "float" / "date" / "bool"
    :return: MySQL 类型字符串
    """
    mapping = {
        "string": "TEXT",
        "int": "BIGINT",
        "float": "DOUBLE",
        "date": "DATETIME",
        "bool": "TINYINT(1)",
    }
    return mapping.get(dtype, "TEXT")
