# Use an official Python runtime as the base image
FROM python:3.11-slim

# Set working directory in the container
WORKDIR /app

# Copy the script and requirements file into the container
COPY bot.py .
COPY requirements.txt .

# Install system dependencies (minimal, for cleaner image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port (Render assigns dynamically via $PORT)
EXPOSE $PORT

# Command to run the Flask app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "bot:app"]
