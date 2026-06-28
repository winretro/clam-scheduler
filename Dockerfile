FROM python:3.10-slim

RUN apt-get update && apt-get install -y tzdata

# Create a standard, non-root user named 'appuser'
RUN useradd -m -s /bin/bash appuser

# Set up work directory
WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backend /app/backend
COPY frontend /app/frontend

# Hand ownership of the /app directory over to 'appuser'
RUN chown -R appuser:appuser /app

# SWITCH TO THE NON-ROOT USER
USER appuser

# Expose the API port
EXPOSE 8089

# Start the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8089"]