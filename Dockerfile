# ============================================================
# Agent Factory — Streamlit 运行镜像（极速构建版）
# 全部使用国内镜像源，3-5 分钟构建完毕
# 外网访问：http://103.236.98.149:29187
# ============================================================

FROM python:3.11-slim

LABEL maintainer="Agent Factory Team"
LABEL description="Agent Factory — 智能体全自动生成工厂控制台"

WORKDIR /app

# === Layer 1: 系统依赖 — 阿里云 Debian 镜像极速 ===
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# === Layer 2: Python 依赖 — 阿里云 PyPI 镜像极速 ===
COPY requirements.txt .
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements.txt

# === Layer 3: 项目代码 ===
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "factory_app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.enableXsrfProtection=false", \
     "--server.enableCORS=false", \
     "--browser.gatherUsageStats=false"]
