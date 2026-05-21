FROM python:3.11-slim

WORKDIR /app

# Copy dependency definition
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose Flask / Gunicorn port
EXPOSE 5000

# Launch Gunicorn with environment configuration
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
