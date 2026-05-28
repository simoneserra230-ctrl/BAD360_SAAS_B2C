FROM python:3.11-slim

# System deps for ReportLab (PDF) and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
