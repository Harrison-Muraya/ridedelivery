FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Normalize line endings if the repo was edited on Windows
RUN sed -i 's/\r$//' /app/deploy/entrypoint.sh \
    && chmod +x /app/deploy/entrypoint.sh

ENV PYTHONPATH=/app
ENV APP_ENV=production
ENV DEBUG=false

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
