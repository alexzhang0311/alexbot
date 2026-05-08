# AI Web Tool - Backend

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy Claude Code CLI binary
COPY bin/claude.exe /usr/local/bin/claude
RUN chmod +x /usr/local/bin/claude

# Create non-root user for Claude Agent SDK (CLI refuses root + bypassPermissions)
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app

# Create necessary directories
RUN mkdir -p /app/logs /app/uploads

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
