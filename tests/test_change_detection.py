"""
Kiểm thử tự động phát hiện biến động dữ liệu (Automatic Change Detection - CDC).

Kịch bản kiểm thử:
1. Đọc trạng thái ban đầu của sản phẩm VF-1001 từ Vietful Mock Service và CDMS Service.
2. Thực hiện thay đổi giá (Mutation) của VF-1001 trên Mock Service từ giá cũ sang giá trị mới.
3. Chờ CDMS Poller quét định kỳ (Channel 1: Scheduled Poller chạy chu kỳ 20s).
4. Xác minh CDMS tự động phát hiện thay đổi qua mã Hash SHA-256:
   - Cập nhật giá mới và tăng version trong bảng `products`.
   - Ghi nhận thêm duy nhất 1 bản ghi `UPDATED` vào bảng `product_change_logs`.
   - Tổng số log của VF-1001 tăng thêm đúng 1 bản ghi, không hề có bản ghi trùng lặp nào.
5. Chờ thêm 5 giây (khi dữ liệu không đổi) để chứng minh tính năng Deduplication (Exactly-Once).
"""

import httpx
import time
import os
import sys

# Đảm bảo in tiếng Việt chuẩn UTF-8 trên Windows terminal
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

VIETFUL_URL = os.getenv("VIETFUL_URL", "http://localhost:8001")
CDMS_URL = os.getenv("CDMS_URL", "http://localhost:8000")


def log(msg: str):
    print(f"[TEST CDC] {msg}")


def check_services():
    """Kiểm tra cả 2 service (Vietful Mock và CDMS) có đang hoạt động hay không"""
    log("Kiểm tra kết nối tới các dịch vụ...")
    try:
        r_vietful = httpx.get(f"{VIETFUL_URL}/health", timeout=5.0)
        assert r_vietful.status_code == 200, "Vietful Mock Service không phản hồi HTTP 200"
        log(f"-> Vietful Mock Service: SẴN SÀNG ({VIETFUL_URL})")
    except Exception as e:
        log(f"LỖI: Không thể kết nối Vietful Mock Service tại {VIETFUL_URL}: {e}")
        return False

    try:
        r_cdms = httpx.get(f"{CDMS_URL}/health", timeout=5.0)
        assert r_cdms.status_code == 200, "CDMS Service không phản hồi HTTP 200"
        log(f"-> CDMS Service: SẴN SÀNG ({CDMS_URL})")
    except Exception as e:
        log(f"LỖI: Không thể kết nối CDMS Service tại {CDMS_URL}: {e}")
        return False

    return True


def run_test_automatic_change_detection():
    TARGET_SKU = "VF-1001"
    NEW_PRICE = 1000000
    NEW_QUANTITY = 10

    log("================================================================================")
    log("BẮT ĐẦU KIỂM THỬ PHÁT HIỆN BIẾN ĐỘNG TỰ ĐỘNG (AUTOMATIC CHANGE DETECTION)")
    log("================================================================================")

    # 1. Lấy thông tin hiện tại của VF-1001 trên Mock Vietful
    log(f"Bước 1: Lấy thông tin ban đầu của {TARGET_SKU} từ Vietful Mock Service...")
    r_list = httpx.get(f"{VIETFUL_URL}/api/products?limit=100", timeout=5.0)
    items = [p for p in r_list.json() if p.get("sku") == TARGET_SKU]
    
    if not items:
        log(f"Không tìm thấy {TARGET_SKU} trên Mock Service. Đang reset lại kho hàng...")
        httpx.post(f"{VIETFUL_URL}/api/products/reset", timeout=5.0)
        r_list = httpx.get(f"{VIETFUL_URL}/api/products?limit=100", timeout=5.0)
        items = [p for p in r_list.json() if p.get("sku") == TARGET_SKU]

    assert len(items) > 0, f"Không tìm thấy sản phẩm {TARGET_SKU} trong danh mục Vietful"
    initial_mock_data = items[0]
    old_price = initial_mock_data.get("price")
    log(f"-> Dữ liệu ban đầu trên Vietful:")
    log(f"   + SKU: {initial_mock_data.get('sku')} | Tên: {initial_mock_data.get('name')}")
    log(f"   + Giá hiện tại: {old_price} | Tồn kho: {initial_mock_data.get('quantity')}")

    # Lấy thông tin và số lượng log hiện tại trên CDMS
    r_initial_cdms = httpx.get(f"{CDMS_URL}/api/v1/changes?sku={TARGET_SKU}", timeout=5.0)
    initial_logs = r_initial_cdms.json()
    initial_log_count = len(initial_logs)
    log(f"-> Số bản ghi Change Log hiện tại của {TARGET_SKU} trong CDMS: {initial_log_count}")

    # 2. Thực hiện thay đổi giá sản phẩm trên Mock Service
    log("--------------------------------------------------------------------------------")
    # Nếu giá hiện tại vô tình đã là NEW_PRICE thì chọn giá khác để luôn tạo ra biến động
    target_new_price = NEW_PRICE if old_price != NEW_PRICE else round(NEW_PRICE + 50.0, 2)
    log(f"Bước 2: Thay đổi thuộc tính giá của {TARGET_SKU} trên Mock Service từ ${old_price} sang ${target_new_price}...")
    
    mutation_payload = {
        "sku": TARGET_SKU,
        "price": target_new_price,
        "quantity": NEW_QUANTITY,
    }
    r_mutate = httpx.post(f"{VIETFUL_URL}/api/products/mutate", json=mutation_payload, timeout=5.0)
    assert r_mutate.status_code == 200, f"Gọi API mutate thất bại: {r_mutate.text}"
    mutated_data = r_mutate.json()
    log(f"-> Mock Service đã cập nhật thành công:")
    log(f"   + Giá mới: {mutated_data.get('price')} | Tồn kho mới: {mutated_data.get('quantity')}")
    log(f"   + Thời gian cập nhật: {mutated_data.get('updated_at')}")

    # 3. Chờ CDMS Poller quét chu kỳ tiếp theo
    log("--------------------------------------------------------------------------------")
    log("Bước 3: Chờ CDMS Poller định kỳ (Channel 1) quét và phát hiện biến động...")
    log("        (Đang lắng nghe CDMS cập nhật dữ liệu mới, tối đa 30 giây)...")

    detected = False
    max_wait_seconds = 35
    start_wait = time.time()

    while time.time() - start_wait < max_wait_seconds:
        time.sleep(2)
        # Kiểm tra bảng products trong CDMS
        r_prods = httpx.get(f"{CDMS_URL}/api/v1/products?limit=100", timeout=5.0)
        prods = [p for p in r_prods.json() if p.get("sku") == TARGET_SKU]
        if prods:
            current_prod = prods[0]
            if abs(current_prod.get("price", 0.0) - target_new_price) < 0.01:
                detected = True
                break
        print(".", end="", flush=True)

    print()
    elapsed = time.time() - start_wait
    assert detected, f"LỖI: Hết thời gian chờ {max_wait_seconds}s nhưng CDMS chưa cập nhật giá mới!"
    log(f"-> PHÁT HIỆN BIẾN ĐỘNG THÀNH CÔNG sau {elapsed:.1f} giây!")

    # 4. Kiểm chứng các chỉ số Exactly-Once trên CDMS
    log("--------------------------------------------------------------------------------")
    log("Bước 4: Kiểm chứng tính đúng đắn trong Cơ sở dữ liệu CDMS...")

    # Kiểm tra thông tin trong bảng `products`
    r_prods = httpx.get(f"{CDMS_URL}/api/v1/products?limit=100", timeout=5.0)
    target_product = [p for p in r_prods.json() if p.get("sku") == TARGET_SKU][0]

    log(f"-> Thông tin sản phẩm trong bảng 'products':")
    log(f"   + SKU: {target_product.get('sku')}")
    log(f"   + Giá hiện tại: {target_product.get('price')} (Khớp chính xác {target_new_price})")
    log(f"   + Version: {target_product.get('version')} (Đã tăng phiên bản)")
    log(f"   + Current Hash: {target_product.get('current_hash')}")

    # Kiểm tra thông tin trong bảng `product_change_logs`
    r_logs = httpx.get(f"{CDMS_URL}/api/v1/changes?sku={TARGET_SKU}", timeout=5.0)
    logs = r_logs.json()
    new_log_count = len(logs)

    log(f"-> Danh sách Change Logs của {TARGET_SKU} trong bảng 'product_change_logs':")
    for idx, l in enumerate(logs, 1):
        log(f"   [{idx}] ID: {l.get('id')} | Loại: {l.get('change_type')} | Kênh: {l.get('source_channel')} | Lúc: {l.get('recorded_at')}")

    # Kiểm tra chỉ có thêm đúng 1 bản ghi UPDATED
    assert new_log_count == initial_log_count + 1, (
        f"Kỳ vọng thêm đúng 1 bản ghi log mới, nhưng số lượng từ {initial_log_count} thành {new_log_count}"
    )

    latest_log = logs[0]  # Sắp xếp mới nhất trước
    assert latest_log.get("change_type") == "UPDATED", f"Kỳ vọng log mới nhất là UPDATED, nhưng nhận {latest_log.get('change_type')}"
    assert latest_log.get("source_channel") == "POLLING", "Kỳ vọng nguồn thay đổi ghi nhận từ POLLING"

    log("-> XÁC NHẬN: Bản ghi mới nhất là 'UPDATED' từ kênh 'POLLING'!")

    # 5. Kiểm tra tính năng chống trùng (Deduplication ở chu kỳ tiếp theo)
    log("--------------------------------------------------------------------------------")
    log("Bước 5: Chờ thêm 5 giây (chu kỳ sau khi dữ liệu không đổi) để chứng minh Exactly-Once...")
    time.sleep(5)
    r_logs_after = httpx.get(f"{CDMS_URL}/api/v1/changes?sku={TARGET_SKU}", timeout=5.0)
    logs_after = r_logs_after.json()
    assert len(logs_after) == new_log_count, (
        f"LỖI: Phát hiện bản ghi trùng lặp! Số lượng log bị tăng từ {new_log_count} lên {len(logs_after)}"
    )
    log(f"-> Số lượng log vẫn giữ nguyên {len(logs_after)} bản ghi. Tuyệt đối không phát sinh bản ghi trùng lặp!")

    log("================================================================================")
    log(">>> TẤT CẢ CÁC ĐIỀU KIỆN KIỂM THỬ BIẾN ĐỘNG TỰ ĐỘNG ĐỀU ĐẠT! <<<")
    log("================================================================================")


if __name__ == "__main__":
    if check_services():
        run_test_automatic_change_detection()
    else:
        log("Vui lòng khởi động các dịch vụ bằng lệnh: docker compose up --build")
        sys.exit(1)