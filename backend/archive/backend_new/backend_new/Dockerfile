# --- 使用轻量级 Python 基础镜像 ---
FROM python:3.11-slim

# --- 设置工作目录 ---
WORKDIR /app

# --- 设置环境变量 ---
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# --- 安装系统级依赖（OpenCV 和基础编译工具） ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# --- 复制依赖列表 ---
# 注意：假设 requirements.txt 在项目根目录，构建时需在根目录执行
COPY ./requirements.txt /app/requirements.txt

# --- 安装依赖 ---
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# --- 复制后端代码 ---
# 仅复制 backend 目录下的内容
COPY ./backend /app/backend
WORKDIR /app/backend

# --- 暴露后端端口 ---
EXPOSE 8000

# --- 启动 FastAPI 服务 ---
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
