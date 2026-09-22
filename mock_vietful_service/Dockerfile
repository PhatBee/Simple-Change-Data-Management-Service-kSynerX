FROM python:3.11-slim

WORKDIR /app

# Đặt biến môi trường Python không ghi file .pyc và không buffer stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cài đặt các thư viện cần thiết
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY app/ ./app/

# Mở cổng 8001 cho Mock Vietful Service
EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
