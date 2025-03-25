FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create volume for logs
VOLUME /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "-m", "src.main"]
