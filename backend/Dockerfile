# AI Web Tool - Backend

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# ca-certificates: needed for HTTPS (MiniMax API)
# lib64 symlink: bundled claude binary expects /lib64/ld-linux-x86-64.so.2 (RHEL path)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /lib/x86_64-linux-gnu /lib64

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Claude Agent SDK ships its own bundled Linux CLI at
#   site-packages/claude_agent_sdk/_bundled/claude (ELF binary)
# No separate Claude Code install needed.

# Create non-root user for Claude Agent SDK (CLI refuses to run as root)
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app

# Create necessary directories
RUN mkdir -p /app/logs /app/uploads

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
