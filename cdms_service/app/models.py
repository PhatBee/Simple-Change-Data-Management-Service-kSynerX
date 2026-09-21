'''
Định nghĩa mô hình dữ liệu bằng SQLAlchemy (ORM)
Bao gồm 2 bảng:
1. `products`: Lưu trữ trạng thái mới nhất của mỗi sản phẩm (loại bỏ trùng lặp)
2. `product_change_logs`: Lưu lịch sử mỗi khi có thay đổi (Exactly-Once Change Data Capture)
'''

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from datetime import datetime, timezone
from .database import Base

def utc_now():
    return datetime.now(timezone.utc)

class ProductModel(Base):
    '''
    Bảng lưu trạng thái hiện tại của sản phẩm
    SKU unique constrant
    '''
    __tablename__ = "products"

    id = Column(Integer, primary_key = True, index = True, autoincrement = True)
    sku = Column(String(100), unique = True, index = True, nullable = False)
    name = Column(String(255, nullable = False))
    category = Column(String(100), nullable = True)
    price = Column(Float, nullable = False, default = 0)
    quantity = Column(Integer, nullable = False, default = 0)
    status = Column(String(50), nullable = False, default = "ACTIVE")

    # Hash SHA-256 của các thuộc tính để so sánh sự thay đổi
    current_hash = Column(String(64), index = True, nullable = False)

    # Phiên bản dữ liệu
    version = Column(Integer, default = 1, nullable = False)

    created_at = Column(DateTime(timezone = True), default = utc_now, nullable = False)
    updated_at = Column(DateTime(timezone = True), default = utc_now, onupdate = utc_now, nullable = False)

class ProductChangeLogModel(Base):
    '''
    Bảng lưu nhật ký biến động dữ liệu
    Ghi nhận khi có sự thay đổi thực tế (không tính ghi lại dữ liệu cũ hoặc trùng lặp)
    '''
    __tablename__ = "product_change_logs"

    id = Column(Integer, primary_key = True, index = True, autoincrement = True)
    sku = Column(String(100), index = True, nullable = False)

    # Loại thay đổi: CREATED hoặc UPDATED
    changed_type = Column(String(20), nullable = False)

    # Mã hash của phiên bản này
    payload_hash = Column(String(64), nullable = False)

    # Snapshot JSON
    previous_data = Column(Text, nullable = True)
    current_Data = Column(Text, nullable = False)

    # Kênh đẩy dữ liệu: POLLING, WEBHOOK, EXCEK_UPLOAD
    source_channel = Column(String(50), nullable = False)

    # Thời điểm ghi nhận thay đổi
    recorded_at = Column(DateTime(timezone = True), default = utc_now, nullable = False)

    __table_args__ = (
        Index("idx_change_sku_recorded", "sku", "recorded_at"),
    )
