"""
Router Channel 3 (Excel File Upload).
Tiếp nhận file bảng tính (.xlsx / .xls), trích xuất danh sách sản phẩm bằng Pandas/Openpyxl
và đưa vào ChangeDetectorService để lưu các thay đổi.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
import pandas as pd
import io
from ..database import get_db
from ..schemas import IngestionSummary
from ..services.change_detector import process_batch

router = APIRouter(prefix="/api/v1/upload-excel", tags=["Channel 3 - Excel Upload"])


@router.post(
    "",
    response_model=IngestionSummary,
    status_code=status.HTTP_200_OK,
    summary="Tải lên file Excel danh mục sản phẩm",
    description="Nhận file .xlsx hoặc .xls chứa các cột: sku, name, category, price, quantity, status.",
)
async def upload_excel(
    file: UploadFile = File(..., description="File Excel sản phẩm (.xlsx hoặc .xls)"),
    db: Session = Depends(get_db),
):
    """
    Đọc và phân tích cú pháp file Excel được tải lên.
    Chuẩn hóa các cột và đưa dữ liệu vào ChangeDetectorService.
    """
    filename = file.filename or ""
    if not (filename.endswith(".xlsx") or filename.endswith(".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Định dạng file không được hỗ trợ. Vui lòng tải lên file định dạng .xlsx hoặc .xls.",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File tải lên bị rỗng",
        )

    try:
        # Đọc dữ liệu từ byte stream bằng pandas
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể đọc nội dung file Excel: {str(e)}",
        )

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File Excel không có dòng dữ liệu nào",
        )

    # Chuẩn hóa tên các cột về chữ thường và xóa khoảng trắng
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Kiểm tra cột bắt buộc
    required_columns = {"sku", "name"}
    missing = required_columns - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File Excel thiếu các cột bắt buộc: {', '.join(missing)}",
        )

    # Chuyển đổi DataFrame sang danh sách từ điển
    items = []
    for _, row in df.iterrows():
        sku_val = str(row.get("sku", "")).strip()
        if not sku_val or sku_val.lower() == "nan":
            continue

        item = {
            "sku": sku_val,
            "name": str(row.get("name", "")).strip(),
            "category": str(row.get("category", "Không phân loại")).strip() if pd.notna(row.get("category")) else "Không phân loại",
            "price": float(row.get("price", 0.0)) if pd.notna(row.get("price")) else 0.0,
            "quantity": int(row.get("quantity", 0)) if pd.notna(row.get("quantity")) else 0,
            "status": str(row.get("status", "ACTIVE")).strip() if pd.notna(row.get("status")) else "ACTIVE",
        }
        items.append(item)

    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không tìm thấy bản ghi sản phẩm hợp lệ nào trong file Excel",
        )

    # Đưa vào pipeline xử lý Exactly-Once
    result = process_batch(db, items, source_channel="EXCEL_UPLOAD")
    return result
