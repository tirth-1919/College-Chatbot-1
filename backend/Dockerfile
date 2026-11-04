FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && playwright install chromium --with-deps
COPY . .
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.user_main:app --host 0.0.0.0 --port 8000"]
