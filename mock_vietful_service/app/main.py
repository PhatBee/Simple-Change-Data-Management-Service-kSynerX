'''
Mock Vietful Inventory Service
Cung cấp API Product sử dụng Faker sinh dữ liệu mẫu thực tế
'''

from fastapi import FastAPI, HTTPException, Query
from typing import List, Dict, Optional
from datetime import datetime, timezone
import random
from faker import Faker

from .models import Product, ProductMutationRequest

app = FastAPI(
    title = "Vietful Inventory Mock Service",
    description = "Service giả lập quản lý kho hàng Vietful cho bài test CDMS",
    version = "1.0.0"
)

fake = Faker()
Faker.seed(42)

# Bộ nhớ tạm lưu danh sách sản phẩm mẫu
INVENTORY_DB: Dict[str, Product] = {}

CATEGORIES = ["Điện tử", "Nhà cửa", "Thời trang", "Thể thao", "Sách", "Đồ gia dụng", "Đồ chơi"]

def generate_initial_products(count: int = 15,) -> Dict[str, Product]:
    # Hàm sinh danh sách ban đầu bằng Faker
    products = {}
    for index in range (1, count + 1):
        sku = f"VF-{1000 + i}"
        now_str = datetime.now(timezone.utc).isoformat()
        product = Product(
            sku = sku,
            name = fake.catch_phrase(),
            category = random.choice(CATEGORIES),
            price = round(random.uniform(250000, 13000000), 0),
            quantity = random.randInt(5, 100),
            status = "ACTIVE",
            uploaded_at = now_str,
        )
        products[sku] = product
    return products

# Khởi tạo dữ liệu kho hàng khi chạy
INVENTORY_DB = generate_initial_products(15)


@app.get("/api/products", response_model=List[Product], tags="[Products]")
def get_products(
    category: Optional[str] = Query(None, description = "Lọc theo danh mục"),
    limit: int = Query(50, ge = 1, le = 100, description = "Số lượng sản phẩm tối đa trả về"),
):
    '''
    Endpoint: Trả về danh sách sản phẩm tồn kho của Vietful
    CDMS Channel 1 (Scheduled Polling) sẽ định kỳ gọi vào API này để lấy dữ liệu
    '''
    products = list(INVENTORY_DB.values())
    if category:
        products = [p for p in products if p.category.lower() == category.lower()]
    return products[:limit]

@app.post("/api/products/mutate", response_model = Product, tags = ["Testing Simulation"])
def mutate_product(request: ProductMutationRequest):
    '''
    Endpoint hỗ trợ test: Thay đổi trường thông tin dữ liệu sản phẩm
    Hỗ trợ trong việc kiểm tra CDMS có bắt sự kiện thay đổi hay không?
    '''
    target_sku = request.sku
    if not target_sku:
        # Nếu không có sku, lấy một sku ngẫu nhiên
        target_sku = random.choice(list(INVENTORY_DB.keys()))

    if target_sku not in INVENTORY_DB:
        raise HTTPException(status_code = 404, detail = f"SKU {target_sku} không tồn tại")

    product = INVENTORY_DB[target_sku]
    now_str = datetime.now(timezone.utc).isoformat()

    # Cập nhật thông tin mới
    new_price = request.price if request.price is not None else round(product.price * random.uniform(0.8, 1.3), 0)
    new_quantity = request.quantity if request.quantity is not None else max(0, product.quantity + random.randint(-10, 20))
    new_status = "OUT_OF_STOCK" if new_quantity == 0 else "ACTIVE"

    updatedProduct = Product(
        sku = product.sku,
        name = product.name,
        category = product.category,
        price = new_price,
        quantity = new_quantity,
        status = new_status,
        updated_at = now_str
    )
    INVENTORY_DB[target_sku] = updatedProduct
    return updatedProduct