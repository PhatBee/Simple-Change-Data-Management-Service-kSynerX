'''
Channel 1: Module Poller thực hiện Scheduled Polling
Định kì gửi HTTP Get request qua Vietful Inventory Service để kéo danh sách sản phẩm 
đưa vào Change Detector Service lưu các thay đổi mới
'''

import httpx
import logging
from ..config import settings
from ..database import SessionLocal
from .change_detector import process_batch

logger = logging.getLogger("cdms.poller")

def poll_vietful_inventory():
    '''
    Hàm được APScheduler gọi định kỳ theo cấu hình POLL_INTERVAL_SECONDS.
    Tự tạo Session DB và tự động đóng sau khi kết thúc
    '''

    url =f"{settings.VIETFUL_SERVICE_URL}/api/products"
    logger.info(f"[Channel 1 - Poller] Bắt đầu quét dữ liệu từ: {url}")

    try:
        with httpx.Client(timeout = 10.0) as client:
            response = client.get(url)
            if response.status_code != 200:
                logger.warning(f"[Channel 1 - Poller] Vietful Service trả về lỗi HTTP {response.status_code}")
                return
            products_data = response.json()
            if not isinstance(products_data, list):
                logger.warning(f"[Channel 1 - Poller] Dữ liệu trả về không đúng định dạng danh sách")
                return
            
            # Đưa dữ liệu vào xử lý Exactly-once
            db = SessionLocal()

            try: 
                summary = process_batch(db, products_data, source_channel = "POLLING")
                logger.info(
                    f"[Channel 1 - Poller] Hoàn thành quét: Nhận {summary['total_received']}"
                    f"Mới: {summary['created']}, Cập nhật: {summary['updated']}, Bỏ qua: {summary['skipped_deduplicated']}"
                )
            finally:
                db.close()

    except httpx.ConnectError:
        # Xử lý an toàn
        logger.warning(f"[Channer 1 - Poller] Không thể kết nối tới dịch vụ Vietful Service tại {url}")
    except Exception as e:
        logger.error(f"[Channel 1 - Poller] Lỗi bất ngờ trong quá trình polling: {str(e)}", exc_info = True)