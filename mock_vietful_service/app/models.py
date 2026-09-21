'''
Định nghĩa cấu trúc dữ liệu cho product của Vietful Inventory Service
Dùng Pydantic chuẩn hóa dữ liệu vào / ra của API
'''

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Product(BaseModel):
    # Mã định danh sản phẩm (unique)
    sku: str = Field(..., description = "Mã SKU duy nhất của sản phẩm. Ví dụ: VF-1001")
    # Tên sản phẩm
    name: str = Field(..., description = "Tên sản phẩm")
    # Phân loại sản phẩm (danh mục)
    category: str = Field(..., description = "Danh mục sản phẩm")
    # Giá bán hiện tại
    price: float = Field(..., ge=0 ,description = "Giá sản phẩm")
    # Số lượng tồn tho
    quantity: int = Field(..., ge=0, description = "Số lượng tồn kho")
    # Trạng thái kinh doanh
    status: str = Field(..., default = "ACTIVE",description = "Trạng thái: ACTIVE, OUT_OF_STOCK, DISCONTINUED")
    # Thời điểm cập nhật cuối
    updated_at: str = Field(..., description = "Thời gian cập nhật gần nhất")

class ProductMutationRequest(BaseModel):
    # Dùng cho API giả lập thay đổi dữ liệu product để test phát hiện thay đổi 
    sku: Optional[str] = Field(None, description = "SKU cần đổi, nếu trống sẽ lấy ngẫu nhiên"),
    price: Optional[float] = Field(None, description = "Giá mới")
    quantity: Optional[int] = Field(Nonte, description = "Số lượng mới")
