'''
Service phát hiện thay đổi dữ liệu
Áp dụng "Exactly-Once"
- Chỉ chèn dữ liệu khi có sự thay đổi hoặc product mới
- Bỏ qua dữ liệu trùng lặp / không đổi
- Sử dụng database transaction và row locking chống race condition khi có tải spike đồng thời
'''

import json
import hashlib
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from ..models import ProductModel, ProductChangeLogModel

def calculate_product_hash(data: Dict[str, Any]) -> str:
    '''
    Thực hiện băm SHA-256 cho product
    Sắp xếp các khóa từ điển đảm bảo mã hash nhất quán
    '''

    normalized_data = {
        "sku": str(data.get("sku", "")).strip().upper(),
        "name": str(data.get("name", "")).strip(),
        "category": str(data.get("category", "")).strip(),
        "price": round(float(data.get("price", 0)), 0),
        "quantity": int(data.get("quantity", 0)),
        "status": str(data.get("status", "ACTIVE")).strip().upper(),
    }

    # Chuyển thành JSON có sắp xếp
    canonical_json = json.dumps(normalized_data, sort_keys = True, ensure_ascii = False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

def process_single_product(db: Session, item: Dict[str, Any], source_channel = str) -> str:
    '''
    Xử lý product theo exactly-once
    - Nếu SKU chưa có: INSERT product (version 1) + INSERT changelog (CREATED)
    - Nếu SKU tồn tại
        + Hash trùng khớp: SKIPPED
        + Hash khác: UPDATE product (version + 1) + INSERT changelog (UPDATED)

    Return: `CREATED`, `UPDATED`, `SKIPPED`
    '''

    sku = str(item.get("sku", "")).strip().upper()
    if not sku:
        return "INVALID"
    
    new_hash = calculate_product_hash(item)

    # Snapshot lưu vào change log
    current_snapshot = json.dumps({
        "sku": sku,
        "name": item.get("name"),
        "category": item.get("category"),
        "price": item.get("price", 0),
        "quantity": item.get("quantity", 0),
        "status": item.get("status", "ACTIVE").strip().upper(),
    },  ensure_ascii = False)

    # Sử dụng with_for_update() cho PostgreSQL để khóa dòng dữ liệu, tránh xung đột nhiều luồng ghi
    query = db.query(ProductModel).filter(ProductModel.sku == sku)
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    
    existing_product = query.first()

    if existing_product is None:
        # Trường hợp 1: product mới
        new_product = ProductModel(
            sku = sku,
            name = item.get("name", ""),
            category = item.get("category", "Không phân loại"),
            price = item.get("price", 0),
            quantity = item.get("quantity", 0),
            status = item.get("status", "ACTIVE").strip().upper(),
            current_hash = new_hash,
            version = 1
        )
        db.add(new_product)

        # Ghi nhận log lần đầu: CREATED
        changelog = ProductChangeLogModel(
            sku = sku,
            change_type = "CREATED",
            payload_hash = new_hash,
            current_data = current_snapshot,
            source_channel = source_channel,
        )
        db.add(changelog)
        return "CREATED"

    else:
        # TRường hợp 2: Sản phẩm tồn tại trong database
        if existing_product.current_hash == new_hash:
            # Hash y hệt, bỏ qua
            return "SKIPPED"
        
        # Dữ liệu có thay đổi
        previous_snapshot = json.dumps({
            "sku": existing_product.sku,
            "name": existing_product.name,
            "category": existing_product.category,
            "price": existing_product.price,
            "quantity": existing_product.quantity,
            "status": existing_product.status,
        },  ensure_ascii = False)

        # Cập nhật thông tin mới + tăng version
        existing_product.name = item.get("name", existing_product.name)
        existing_product.category = item.get("category", existing_product.category)
        existing_product.price = float(item.get("price", existing_product.price))
        existing_product.quantity = int(item.get("quantity", existing_product.quantity))
        existing_product.status = item.get("status", existing_product.status)
        existing_product.current_hash = new_hash
        existing_product.version += 1

        # Ghi nhận log: UPDATED
        changelog = ProductChangeLogModel(
            sku = sku,
            change_type = "UPDATED",
            payload_hash = new_hash,
            previous_data = previous_snapshot,
            current_data = current_snapshot,
            source_channel = source_channel,
        )
        db.add(changelog)
        return "UPDATED"

def process_batch(db: Session, items: List[Dict[str, Any]], source_channel: str) -> Dict[str, Any]:
    '''
    Xử lý danh sách sản phẩm trong database transaction
    Tổng hợp kết quả: số lượng tạo mới, cập nhật, bỏ qua
    '''
    created_count = 0
    updated_count = 0
    skipped_count = 0

    try:
        for item in items:
            result = process_single_product(db, item, source_channel)
            if result == "CREATED":
                created_count += 1
            elif result == "UPDATED":
                updated_count += 1
            elif result == "SKIPPED":
                skipped_count += 1
            
        db.commit()

    except Exception as e:
        db.rollback()
        raise e
    
    return {
        "status": "success",
        "source_channel": source_channel,
        "total_received": len(items),
        "created": created_count,
        "updated": updated_count,
        "skipped_deduplicated": skipped_count,
        "message": f"Đã xử lý {len(items)} bản ghi: {created_count} mới, {updated_count} cập nhật, {skipped_count} trùng lặp bỏ qua"

    }
