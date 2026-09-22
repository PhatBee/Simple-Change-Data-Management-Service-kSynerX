"""
Router tra cứu dữ liệu (Query APIs) của CDMS.
Cung cấp các API để kiểm tra danh sách sản phẩm hiện tại, nhật ký biến động (CDC Logs)
và thống kê dữ liệu.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from ..database import get_db
from ..models import ProductModel, ProductChangeLogModel
from ..schemas import ProductOut, ChangeLogOut

router = APIRouter(prefix="/api/v1", tags=["Data Queries & Audit"])


@router.get("/products", response_model=List[ProductOut], summary="Danh sách sản phẩm hiện tại")
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các sản phẩm đang được lưu trạng thái mới nhất trong kho CDMS"""
    return db.query(ProductModel).offset(skip).limit(limit).all()


@router.get("/changes", response_model=List[ChangeLogOut], summary="Lịch sử các lần thay đổi (CDC Logs)")
def get_changes(
    sku: Optional[str] = Query(None, description="Lọc theo mã SKU cụ thể"),
    channel: Optional[str] = Query(None, description="Lọc theo kênh: POLLING, WEBHOOK, EXCEL_UPLOAD"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Tra cứu nhật ký Exactly-Once.
    Chỉ hiển thị các sự kiện thực tế phát sinh biến động (CREATED hoặc UPDATED).
    """
    query = db.query(ProductChangeLogModel)
    if sku:
        query = query.filter(ProductChangeLogModel.sku == sku.upper())
    if channel:
        query = query.filter(ProductChangeLogModel.source_channel == channel.upper())
    
    return query.order_by(ProductChangeLogModel.recorded_at.desc()).offset(skip).limit(limit).all()


@router.get("/stats", summary="Thống kê tổng quan hệ thống CDMS")
def get_statistics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Báo cáo thống kê:
    - Tổng số sản phẩm duy nhất đang quản lý
    - Tổng số bản ghi biến động đã ghi nhận
    - Phân bổ số lượt thay đổi theo từng kênh nạp (Polling / Webhook / Excel)
    """
    total_products = db.query(func.count(ProductModel.id)).scalar() or 0
    total_changes = db.query(func.count(ProductChangeLogModel.id)).scalar() or 0

    channel_stats = (
        db.query(ProductChangeLogModel.source_channel, func.count(ProductChangeLogModel.id))
        .group_by(ProductChangeLogModel.source_channel)
        .all()
    )

    type_stats = (
        db.query(ProductChangeLogModel.change_type, func.count(ProductChangeLogModel.id))
        .group_by(ProductChangeLogModel.change_type)
        .all()
    )

    return {
        "total_unique_products": total_products,
        "total_change_events": total_changes,
        "by_channel": {ch: count for ch, count in channel_stats},
        "by_change_type": {t: count for t, count in type_stats},
    }
