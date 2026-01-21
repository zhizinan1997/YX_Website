FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy website files
COPY . .

# Create data directory
RUN mkdir -p /app/data/messages

# Expose port
EXPOSE 8000

# Run with gunicorn in production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "server:app"]
