"""
数据集业务逻辑
===============
负责 CSV 导入、元数据管理、数据查询与物理表删除。

上游：api/datasets.py 路由、tasks/ 里的 Celery 任务（调用 import_csv_task）；
下游：repositories/dataset_repo.py 管元数据表，物理数据表由本类动态建/删。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine

from app.config import settings
from app.models.dataset import Dataset
from app.repositories.dataset_repo import DatasetRepository
from app.utils import csv_helper
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# 同步引擎（用于 df.to_sql 批量写入）
# ---------------------------------------------------------------------------
# df.to_sql 是同步阻塞操作，不能直接在异步会话里跑。
# 单独创建一个同步 engine，通过 asyncio.to_thread 调用，避免阻塞事件循环。
_sync_engine = None


def _get_sync_engine():
    """惰性创建同步 SQLAlchemy 引擎（pymysql 驱动）"""
    global _sync_engine
    if _sync_engine is None:
        logger.info("创建同步数据库引擎（用于 df.to_sql）")
        _sync_engine = create_engine(
            settings.sync_database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _sync_engine


class DatasetService:
    """数据集业务逻辑"""

    # ------------------------------------------------------------------
    # 查询类
    # ------------------------------------------------------------------
    @staticmethod
    async def list_datasets(db: AsyncSession, status: Optional[str] = None) -> list[Dataset]:
        """列出数据集，可按状态过滤"""
        return await DatasetRepository.get_all(db, status=status)

    @staticmethod
    async def get_dataset(db: AsyncSession, dataset_id: int) -> Optional[Dataset]:
        """按 ID 获取数据集"""
        return await DatasetRepository.get_by_id(db, dataset_id)

    # ------------------------------------------------------------------
    # CSV 导入（Celery 任务核心逻辑）
    # ------------------------------------------------------------------
    @staticmethod
    async def import_csv_task(db: AsyncSession, dataset_id: int, file_path: str) -> None:
        """
        CSV 导入数据集的完整流程（由 Celery 任务调用）。

        步骤：
            1. 标记状态为 processing
            2. 用 csv_helper 安全读取 CSV（正确处理引号内逗号/换行）
            3. 生成合规表名和列名映射
            4. 动态 CREATE TABLE（列名用反引号包裹）
            5. df.to_sql 批量写入
            6. 更新数据集元数据（table_name / columns_meta / row_count 等）
            7. 失败时标记 failed 并记录 error_msg
        """
        try:
            # ---- 1. 标记处理中 ----
            await DatasetRepository.update_status(db, dataset_id, "processing")
            logger.info(f"[dataset={dataset_id}] 开始导入 CSV: {file_path}")

            # ---- 2. 安全读取 CSV ----
            df, column_mapping = csv_helper.read_csv_safely(file_path)
            original_cols = column_mapping["original_columns"]
            physical_cols = column_mapping["physical_columns"]
            logger.info(f"[dataset={dataset_id}] CSV 读取完成: {len(df)} 行, {len(df.columns)} 列")

            # ---- 3. 生成表名和列映射 ----
            # 从 DB 取数据集名用于生成表名
            dataset = await DatasetRepository.get_by_id(db, dataset_id)
            if not dataset:
                raise ValueError(f"数据集 ID={dataset_id} 不存在")

            table_name = csv_helper.sanitize_table_name(dataset.name)

            # 推断列类型并填充 original_name
            columns_meta = csv_helper.infer_column_types(df)
            for i, col_meta in enumerate(columns_meta):
                col_meta["original_name"] = original_cols[i] if i < len(original_cols) else ""

            # ---- 4. 动态 CREATE TABLE ----
            # 列名用反引号包裹，防止特殊字符；类型由 infer_column_types 推断
            col_defs = []
            for cm in columns_meta:
                mysql_type = csv_helper.dtype_to_mysql(cm["dtype"])
                col_defs.append(f"  `{cm['physical_name']}` {mysql_type} NULL")
            create_sql = (
                f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n"
                + ",\n".join(col_defs)
                + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            )
            logger.debug(f"[dataset={dataset_id}] 建表 SQL:\n{create_sql}")

            async with db.begin():
                await db.execute(text(create_sql))
            logger.info(f"[dataset={dataset_id}] 物理表 `{table_name}` 创建成功")

            # ---- 5. 批量写入数据（同步操作放到线程池）----
            # asyncio.to_thread：把同步阻塞函数丢到线程里跑并 await 其结果，
            # 避免卡住事件循环（这是异步代码里调用同步库的常用手法）
            sync_engine = _get_sync_engine()
            await asyncio.to_thread(
                df.to_sql,
                name=table_name,
                con=sync_engine,
                if_exists="append",
                index=False,
            )
            logger.info(f"[dataset={dataset_id}] {len(df)} 行数据写入完成")

            # ---- 6. 更新元数据 ----
            await DatasetRepository.update(
                db,
                dataset_id,
                table_name=table_name,
                columns_meta=columns_meta,
                row_count=len(df),
                column_count=len(physical_cols),
                status="completed",
                error_msg="",
            )
            logger.info(f"[dataset={dataset_id}] 导入完成，表名={table_name}")

            # ---- 7. 可选：将 CSV 行向量化（供 RAG 兜底）----
            try:
                from app.rag.vector_store import get_vector_store
                vs = get_vector_store()
                await vs.add_csv_rows(df, dataset.name)
            except Exception as vec_err:
                # 向量化失败不影响主流程，仅记录日志
                logger.warning(f"[dataset={dataset_id}] CSV 行向量化失败（不影响导入）: {vec_err}")

        except Exception as e:
            logger.exception(f"[dataset={dataset_id}] CSV 导入失败: {e}")
            try:
                await DatasetRepository.update_status(
                    db, dataset_id, "failed", error_msg=str(e)[:2000]
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------
    @staticmethod
    async def delete_dataset(db: AsyncSession, dataset_id: int) -> bool:
        """
        删除数据集：先 DROP 物理表，再删元数据记录。

        :return: 是否删除成功
        """
        dataset = await DatasetRepository.get_by_id(db, dataset_id)
        if not dataset:
            return False

        # DROP 物理表（如果存在）
        try:
            drop_sql = f"DROP TABLE IF EXISTS `{dataset.table_name}`"
            async with db.begin():
                await db.execute(text(drop_sql))
            logger.info(f"数据集 {dataset_id} 物理表 `{dataset.table_name}` 已删除")
        except Exception as e:
            logger.warning(f"删除物理表失败（继续删元数据）: {e}")

        # 删除元数据
        await DatasetRepository.delete(db, dataset_id)
        return True

    # ------------------------------------------------------------------
    # 只读查询
    # ------------------------------------------------------------------
    @staticmethod
    async def query_dataset_table(db: AsyncSession, table_name: str, sql: str) -> list[dict]:
        """
        执行只读 SELECT 查询，返回字典列表。

        :param table_name: 物理表名（用于日志）
        :param sql: 已经过安全校验的 SELECT 语句
        :return: [{"col_0": "val1", "col_1": "val2"}, ...]
        """
        logger.info(f"执行查询 [{table_name}]: {sql}")
        result = await db.execute(text(sql))
        rows = result.mappings().all()
        # 转为普通 dict 列表，方便 JSON 序列化
        return [dict(r) for r in rows]
