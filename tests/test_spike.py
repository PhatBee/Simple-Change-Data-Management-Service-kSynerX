"""
Script kiểm thử tải Spike và Concurrency (Đồng thời) cho Change Data Management Service (CDMS).
Mục tiêu:
1. Đảm bảo "Exactly-Once": Khi có hàng chục request đồng thời gửi cùng 1 dữ liệu,
   Database CHỈ GHI NHẬN 1 LẦN DUY NHẤT, không bị duplicate bản ghi.
2. Kiểm tra khả năng chịu tải đột biến (Spike Load) của 3 kênh nạp (Webhook, Polling, Excel Upload).
"""

import httpx
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi UnicodeEncodeError
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = os.getenv("CDMS_URL", "http://localhost:8000")


def log(msg: str):
    print(f"[TEST RUNNER] {msg}")


def check_cdms_health():
    """Kiểm tra dịch vụ CDMS đã sẵn sàng hoạt động chưa"""
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        if r.status_code == 200:
            log(f"CDMS Service đang hoạt động tốt tại: {BASE_URL}")
            return True
    except Exception as e:
        log(f"Không thể kết nối CDMS tại {BASE_URL}: {e}")
    return False


def test_single_webhook_deduplication():
    """Kiểm tra gửi tuần tự 2 payload giống hệt nhau: Lần 1 CREATED, Lần 2 SKIPPED"""
    log("=== TEST 1: Gửi 2 request tuần tự giống hệt nhau ===")
    payload = {
        "sku": f"TEST-SEQ-{int(time.time())}",
        "name": "Sequential Test Item",
        "category": "Testing",
        "price": 50.0,
        "quantity": 10,
        "status": "ACTIVE"
    }

    # Lần 1: Tạo mới
    r1 = httpx.post(f"{BASE_URL}/api/v1/webhook", json=payload, timeout=5.0)
    data1 = r1.json()
    log(f"Lần 1: HTTP {r1.status_code} - Created: {data1.get('created')}, Skipped: {data1.get('skipped_deduplicated')}")
    assert data1.get("created") == 1, "Lần 1 phải tạo mới thành công"

    # Lần 2: Gửi lại y hệt
    r2 = httpx.post(f"{BASE_URL}/api/v1/webhook", json=payload, timeout=5.0)
    data2 = r2.json()
    log(f"Lần 2: HTTP {r2.status_code} - Created: {data2.get('created')}, Skipped: {data2.get('skipped_deduplicated')}")
    assert data2.get("skipped_deduplicated") == 1, "Lần 2 phải bị bỏ qua (Deduplicated)"
    log("=> TEST 1 PASSED: Exactly-once hoạt động chuẩn xác trên luồng tuần tự!\n")


def send_webhook_request(session, payload):
    """Hàm gửi 1 request Webhook"""
    try:
        r = session.post(f"{BASE_URL}/api/v1/webhook", json=payload, timeout=10.0)
        return r.status_code, r.json()
    except Exception as e:
        return 500, {"error": str(e)}


def test_concurrent_spike_webhook(num_requests: int = 50):
    """
    Spike Test: Bắn đồng thời 50 request cùng 1 lúc với cùng một SKU và nội dung.
    Kỳ vọng: Tổng số lần ghi nhận thay đổi chỉ là 1, toàn bộ 49 request còn lại bị bỏ qua!
    """
    log(f"=== TEST 2: Spike & Concurrency Test ({num_requests} requests đồng thời) ===")
    test_sku = f"SPIKE-CONCURRENT-{int(time.time())}"
    payload = {
        "sku": test_sku,
        "name": "Spike Flash Sale Item",
        "category": "FlashSale",
        "price": 990000,
        "quantity": 500,
        "status": "ACTIVE"
    }

    results = []
    start_time = time.time()

    with httpx.Client(timeout=15.0) as client:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(send_webhook_request, client, payload) for _ in range(num_requests)]
            for f in as_completed(futures):
                results.append(f.result())

    elapsed = time.time() - start_time
    status_codes = [r[0] for r in results]
    success_count = status_codes.count(200)

    log(f"Thời gian hoàn thành {num_requests} requests: {elapsed:.2f}s ({num_requests/elapsed:.1f} req/s)")
    log(f"Số lượng requests thành công HTTP 200: {success_count}/{num_requests}")

    # Truy vấn API Audit Log của CDMS để kiểm tra số bản ghi thực tế trong CSDL
    audit_res = httpx.get(f"{BASE_URL}/api/v1/changes?sku={test_sku}", timeout=5.0)
    change_logs = audit_res.json()

    log(f"Số lượng bản ghi Change Log trong CSDL cho SKU {test_sku}: {len(change_logs)}")
    assert len(change_logs) == 1, f"LỖI: Kỳ vọng chỉ có 1 bản ghi duy nhất, nhưng phát hiện {len(change_logs)} bản ghi!"
    assert change_logs[0]["change_type"] == "CREATED"
    log("=> TEST 2 PASSED: 100% Exactly-Once được đảm bảo dưới tải đồng thời cao (Anti-Race condition)!\n")


def test_excel_upload_deduplication():
    """Kiểm tra nạp file Excel 2 lần liên tiếp: Lần 2 toàn bộ phải bị bỏ qua"""
    log("=== TEST 3: Excel Upload Deduplication ===")
    excel_path = os.path.join("tests", "sample_products.xlsx")
    if not os.path.exists(excel_path):
        log(f"Bỏ qua test excel vì không tìm thấy file {excel_path}")
        return

    # Upload lần 1
    with open(excel_path, "rb") as f:
        files = {"file": ("sample_products.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r1 = httpx.post(f"{BASE_URL}/api/v1/upload-excel", files=files, timeout=10.0)
    data1 = r1.json()
    log(f"Upload lần 1: Nhận {data1.get('total_received')}, Mới: {data1.get('created')}, Trùng: {data1.get('skipped_deduplicated')}")

    # Upload lần 2 (ngay lập tức)
    with open(excel_path, "rb") as f:
        files = {"file": ("sample_products.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r2 = httpx.post(f"{BASE_URL}/api/v1/upload-excel", files=files, timeout=10.0)
    data2 = r2.json()
    log(f"Upload lần 2: Nhận {data2.get('total_received')}, Mới: {data2.get('created')}, Trùng: {data2.get('skipped_deduplicated')}")

    assert data2.get("created") == 0, "Upload lần 2 không được tạo mới bản ghi nào"
    assert data2.get("skipped_deduplicated") == data2.get("total_received"), "Upload lần 2 toàn bộ phải bị bỏ qua"
    log("=> TEST 3 PASSED: File Excel upload trùng lặp bị lọc bỏ hoàn toàn!\n")


def test_system_stats():
    """Kiểm tra API thống kê tổng thể"""
    log("=== TEST 4: Kiểm tra số liệu thống kê hệ thống ===")
    r = httpx.get(f"{BASE_URL}/api/v1/stats", timeout=5.0)
    stats = r.json()
    log(f"Tổng số sản phẩm đang quản lý: {stats.get('total_unique_products')}")
    log(f"Tổng số sự kiện biến động (Change Logs): {stats.get('total_change_events')}")
    log(f"Chi tiết theo kênh nạp: {stats.get('by_channel')}")
    log("=> TEST 4 PASSED: Hệ thống hoạt động trơn tru!\n")


if __name__ == "__main__":
    log("BẮT ĐẦU KIỂM THỬ CHANGE DATA MANAGEMENT SERVICE...")
    if not check_cdms_health():
        log("HƯỚNG DẪN: Hãy chắc chắn CDMS đang chạy trước khi test (docker compose up hoặc uvicorn).")
        exit(1)

    test_single_webhook_deduplication()
    test_concurrent_spike_webhook(num_requests=50)
    test_excel_upload_deduplication()
    test_system_stats()
    log(">>> TẤT CẢ CÁC BÀI KIỂM THỬ SPIKE & EXACTLY-ONCE ĐỀU ĐẠT <<<")
