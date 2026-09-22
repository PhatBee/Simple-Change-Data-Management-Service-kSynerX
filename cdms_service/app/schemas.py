"""
Pydantic Schemas phục vụ validation dữ liệu đầu vào và định dạng phản hồi API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class ProductPayload(BaseModel):
    """Schema dữ liệu sản phẩm khi nhận từ Webhook hoặc Excel"""
    sku: str = Field(..., min_length=1, description="Mã định danh sản phẩm")
    name: str = Field(..., min_length=1, description="Tên sản phẩm")
    category: Optional[str] = Field(default="Không phân loại", description="Danh mục")
    price: float = Field(..., ge=0, description="Giá sản phẩm")
    quantity: int = Field(..., ge=0, description="Số lượng tồn kho")
    status: Optional[str] = Field(default="ACTIVE", description="Trạng thái kinh doanh")


class ProductOut(BaseModel):
    """Schema dữ liệu trả về cho thông tin sản phẩm trong kho CDMS"""
    id: int
    sku: str
    name: str
    category: Optional[str]
    price: float
    quantity: int
    status: str
    current_hash: str
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChangeLogOut(BaseModel):
    """Schema dữ liệu lịch sử biến động (CDC)"""
    id: int
    sku: str
    change_type: str
    payload_hash: str
    previous_data: Optional[str]
    current_data: str
    source_channel: str
    recorded_at: datetime

    class Config:
        from_attributes = True


class IngestionSummary(BaseModel):
    """Báo cáo kết quả xử lý nạp dữ liệu (Hiển thị rõ bao nhiêu bản ghi mới, đổi, bỏ qua)"""
    status: str = "success"
    source_channel: str
    total_received: int
    created: int
    updated: int
    skipped_deduplicated: int
    message: str
