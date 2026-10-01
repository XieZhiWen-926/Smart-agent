"""
数据集路由：
- CSV 上传 -> 落盘 data/uploads/ -> 建 Dataset 记录 -> 触发 Celery 异步导入
- 数据集列表 / 详情 / 删除
- 自然语言查询（DataRouter 路由到 text2sql / rag / clarify）
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import PROJECT_ROOT
from app.models.async_task import AsyncTask
from app.models.dataset import Dataset
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.dataset import (
    DatasetQueryRequest,
    DatasetResponse,
    UploadResponse,
)
from app.services.data_router import DataRouter
from app.services.dataset_service import DatasetService
from app.tasks.dataset_tasks import import_csv_task
from app.utils.logger import logger

router = APIRouter()

# 上传目录与大小限制
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


@router.get("")
async def list_datasets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """数据集列表"""
    items = await DatasetService.list_datasets(db)
    return ApiResponse(data=[DatasetResponse.model_validate(d) for d in items])


@router.get("/{dataset_id}", response_model=ApiResponse[DatasetResponse])
async def get_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """数据集详情"""
    ds = await DatasetService.get_dataset(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    return ApiResponse(data=DatasetResponse.model_validate(ds))


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV 文件"),
    name: str = Form(..., description="数据集名称"),
    description: str = Form(default="", description="数据集描述"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传 CSV：保存文件并触发后台导入任务"""
    content = await file.read()
    # 大小校验
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件大小超过 10MB 限制")
    # 扩展名校验
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .csv 文件")

    # 用 uuid 重命名防止文件名冲突/路径穿越
    safe_filename = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    file_path = UPLOAD_DIR / safe_filename
    file_path.write_bytes(content)

    # 预生成 task_id，并在派发前将数据集和任务记录一起提交。
    # 这样即使 worker 立即开始执行，也能查询到 async_tasks 记录。
    task_id = uuid.uuid4().hex
    ds = Dataset(
        name=name,
        description=description,
        source_file=file.filename,
        # table_name 是 unique 列，导入完成前先用临时占位名，导入任务会改成正式表名
        table_name=f"tmp_pending_{uuid.uuid4().hex[:8]}",
        columns_meta=[],
        status="pending",
        created_by=current_user.id,
    )
    db.add(ds)
    await db.flush()   # flush：先把数据发到数据库拿到自增 ds.id，但还不 commit（提交见下面）
    async_task = AsyncTask(
        task_id=task_id,
        task_type="csv_import",
        status="pending",
    )
    db.add(async_task)
    await db.commit()
    await db.refresh(ds)

    try:
        import_csv_task.apply_async(args=(ds.id, str(file_path)), task_id=task_id)
    except Exception as exc:
        logger.exception(f"数据集导入任务派发失败 id={ds.id} task_id={task_id}")
        ds.status = "failed"
        ds.error_msg = str(exc)[:2000]
        async_task.status = "failed"
        async_task.error_msg = str(exc)[:2000]
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="后台导入任务派发失败，请稍后重试",
        ) from exc

    logger.info(f"数据集上传成功 id={ds.id} celery_task={task_id}")
    return UploadResponse(
        dataset_id=ds.id,
        task_id=task_id,
        message="文件已上传，正在后台导入数据集",
    )


@router.delete("/{dataset_id}", response_model=ApiResponse)
async def delete_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除数据集"""
    ok = await DatasetService.delete_dataset(db, dataset_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    return ApiResponse(message="删除成功")


@router.post("/query")
async def dataset_query(
    body: DatasetQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """自然语言查询：由 DataRouter 自动路由到 text2sql / rag / clarify"""
    if body.dataset_id is not None:
        dataset = await DatasetService.get_dataset(db, body.dataset_id)
        if dataset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
        if dataset.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="数据集尚未完成导入",
            )

    # bug 修复：原调用传了 dataset_id=body.dataset_id，但 DataRouter.route 的签名
    # 只有 (db, query, customer_id)，多传关键字参数会运行时报 TypeError 直接 500。
    # 上面的预检查保留（校验数据集存在且已导入完成），路由仍由语义匹配自动选数据集。
    result = await DataRouter().route(
        db,
        body.query,
        customer_id=None,
    )
    return ApiResponse(data=result)
