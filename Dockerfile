FROM python:3.10-slim

RUN apt-get update && apt-get install -y tzdata gosu && rm -rf /var/lib/apt/lists/*

# Set up work directory
WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backend /app/backend
COPY frontend /app/frontend
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

# Expose the API port
EXPOSE 8089

ENTRYPOINT ["/app/entrypoint.sh"]

# Start the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8089"]