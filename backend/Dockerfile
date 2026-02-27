FROM python:3.9-slim

WORKDIR /app

# 复制并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 确保安装了生产级服务器和 mysql 驱动
RUN pip install gunicorn uvicorn pymysql

# 复制后端所有代码
COPY . .

EXPOSE 8000

# 启动 FastAPI
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000"]