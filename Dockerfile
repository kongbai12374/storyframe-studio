FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock /app/
RUN pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.lock
COPY backend/ /app/
RUN useradd -u 1000 -m studio
USER studio
CMD ["uvicorn","config.asgi:application","--host","0.0.0.0","--port","8000","--workers","1","--limit-concurrency","12"]
