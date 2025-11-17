FROM python:3.11-slim

# Create non-root user
RUN useradd -ms /bin/bash appuser

WORKDIR /app
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Make logs directory
RUN mkdir -p /app/logs && chown -R appuser:appuser /app/logs

# Switch to non-root user
USER appuser

# Start supervisord
CMD ["supervisord", "-c", "/app/supervisord.conf"]
