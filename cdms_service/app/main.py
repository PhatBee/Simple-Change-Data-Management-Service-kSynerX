'''
Chương trình chính CDMS (FastAPI)
Khởi tạo Database và kích hoạt APScheduler chạy ngầm cho Channel 1
'''

from fastapi import FastAPI
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import logging

from .config import settings
from .database import init_db
from .services.poller import poll_vietful_inventory
from .api import webhook, excel_upload, changes

# Cấu hình logging
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cdms.main")

# Khởi tạo scheduler cho channel 1 (Scheduled Polling)
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    '''
    Vòng đời ứng dụng:
    - Khi khởi động: Tự tạo bảng và kích hoạt APScheduler
    - Khi tắt: Dừng hoàn toàn
    '''
    logger.info("=== Khởi động Change Data Management Service (CDMS) ===")

    # Tạo CSDL
    try:
        init_db()
        logger.info("Khởi tạo cấu trúc bảng Database thành công")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo database: {str(e)}")

    # Lập lịch channel 1
    scheduler.add_job(
        poll_vietful_inventory,
        "interval",
        seconds = settings.POLL_INTERVAL_SECONDS,
        id = "vietful_poller_job",
        replace_existing = True,
    )

    scheduler.start()
    logger.info(f"Đã kích hoạt channel 1 (APScheduler) chạy chu kỳ {settings.POLL_INTERVAL_SECONDS}s/lần")

    # Chạy ngay khi khởi động
    scheduler.add_job(poll_vietful_inventory, id = "vietful_initial_poll")

    yield

    # Dọn dẹp tài nguyên khi tắt ứng dụng
    logger.info("Đang dừng APScheduler...")
    scheduler.shutdown(wait = False)
    logger.info("=== CDMS đã dừng an toàn ===")

app = FastAPI(
    title = "Simple Change Data Management Service (CDMS)",
    description = "Dịch vụ ghi nhận và lưu trữ các biến động dữ liệu sản phẩm (Exactly-Once CDC)",
    version = "1.0.0",
    lifespan = lifespan,
)

# Đăng ký các router
app.include_router(webhook.router)
app.include_router(excel_upload.router)
app.include_router(changes.router)