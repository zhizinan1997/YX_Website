# Stage 1: Install Python dependencies
FROM python:3.11-alpine AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile --target=/deps -r requirements.txt

# Stage 2: Runtime image
FROM python:3.11-alpine

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/deps

# Copy installed packages
COPY --from=builder /deps /app/deps

# Copy only runtime files to keep image small
COPY server.py /app/server.py
COPY index.html /app/index.html
COPY robots.txt /app/robots.txt
COPY requirements.txt /app/requirements.txt
COPY admin /app/admin
COPY app /app/app
COPY assets /app/assets
COPY pages /app/pages
COPY templates /app/templates
COPY update_logs /app/update_logs

# Ship all default data seeds; runtime-sensitive files/dirs are excluded by .dockerignore.
COPY data /app/data

# Include full CDN assets for out-of-the-box deployment on fresh servers.
COPY cdn_assets /app/cdn_assets

# Ensure required runtime directories exist
RUN mkdir -p \
    /app/data/messages \
    /app/data/resumes \
    /app/data/news_uploads \
    /app/data/h2_home_videos \
    /app/data/product_cards/uploads \
    /app/data/hero/uploads \
    /app/data/hero/derived \
    /app/data/partners/uploads

EXPOSE 8000

CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "server:app"]
