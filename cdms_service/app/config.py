'''
Quản lý các thông tin cấu hình
Sử dụng pydantic basesettings đọc biến môi trường hoặc default
'''

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Đường dẫn kết nối tới cơ sở dữ liệu. Mặc định trỏ tới Postgres trong Docker Compose
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/cdms_db"

    # URL tới mock Vietful Service (dùng để polling)
    VIETFUL_SERVICE_URL: str = "https://localhost:8001"

    # Chu kỳ polling dữ liệu
    POLL_INTERVAL_SECONDS: int = 30

    # Môi trường
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(env_file = ".env", env_file_encoding = "utf-8", extra = "ignore")

settings = Settings()