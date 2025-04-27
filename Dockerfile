FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install python-dotenv gunicorn

# Copy application code
COPY . .

# Make the entrypoint script executable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port for the application
EXPOSE 8080

# Use the entrypoint script
ENTRYPOINT ["/entrypoint.sh"]

# Run the application with gunicorn (essential for Render)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]