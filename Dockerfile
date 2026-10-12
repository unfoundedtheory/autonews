FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system newsroom && useradd --system --gid newsroom newsroom
COPY pyproject.toml README.md /app/
COPY utbot /app/utbot
RUN pip install --no-cache-dir . && mkdir -p /app/media /app/state && chown newsroom:newsroom /app/media /app/state
USER newsroom
EXPOSE 8000
CMD ["uvicorn","utbot.web:app","--host","0.0.0.0","--port","8000","--workers","1"]
