"""
Router Channel 2 (Webhook Ingestion).
Mở API RESTful tiếp nhận dữ liệu sản phẩm do các hệ thống ngoài hoặc client đẩy về.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Union, Dict, Any
from ..database import get_db
from ..schemas import ProductPayload, IngestionSummary
from ..services.change_detector import process_batch

router = APIRouter(prefix="/api/v1/webhook", tags=["Channel 2 - Webhook"])


@router.post(
    "",
    response_model=IngestionSummary,
    status_code=status.HTTP_200_OK,
    summary="Tiếp nhận dữ liệu sản phẩm qua Webhook",
    description="Cho phép hệ thống ngoài đẩy 1 sản phẩm đơn lẻ hoặc danh sách sản phẩm để CDMS xử lý Exactly-Once.",
)
def receive_webhook(
    payload: Union[ProductPayload, List[ProductPayload]],
    db: Session = Depends(get_db),
):
    """
    Tiếp nhận payload từ Webhook.
    Chuyển đổi thành danh sách từ điển và đẩy qua ChangeDetectorService.
    """
    # Chuẩn hóa đầu vào thành danh sách các dictionary
    if isinstance(payload, list):
        items = [p.model_dump() for p in payload]
    else:
        items = [payload.model_dump()]

    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload không chứa dữ liệu sản phẩm hợp lệ",
        )

    # Đưa vào pipeline xử lý Exactly-Once
    result = process_batch(db, items, source_channel="WEBHOOK")
    return result
