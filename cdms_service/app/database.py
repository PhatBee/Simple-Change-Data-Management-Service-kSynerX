'''
Quản lý kết nối cơ sở dữ liệu PostgreSQL và dự phòng SQLite
'''

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# Cấu hình tham số kết nối
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args = connect_args,
    pool_pre_ping = True            # Kiểm tra ping trước khi query
)

SessionLocal = sessionmaker(
    autocommit = False,
    autoflush = False,
    bind = engine,
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    '''Tạo bảng nếu chưa có'''
    Base.metadata.create_all(bind = engine)