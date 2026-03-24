# Stage 1: Build stage (if any compiled deps needed)
FROM python:3.11-alpine AS builder

WORKDIR /app

# Install dependencies into a virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile --target=/app/deps -r requirements.txt

# Stage 2: Production stage (minimal)
FROM python:3.11-alpine

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy only the installed packages from builder
COPY --from=builder /app/deps /app/deps
ENV PYTHONPATH=/app/deps

# Copy website files
COPY . .

# Create data directory
RUN mkdir -p /app/data/messages

# Expose port
EXPOSE 8000

# Run with gunicorn
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "server:app"]
