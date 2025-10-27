# Use an official Python runtime as the base image
FROM python:3.11-slim

# Set working directory in the container
WORKDIR /app

# Copy the script into the container
COPY bot.py .

# Install system dependencies (if any, e.g., for aiohttp or other libraries)
RUN apt-get update && apt-get install -y
# Install Python dependencies
RUN pip install --no-cache-dir \
    requests \
    bs4 \
    colorama

# Command to run the script
CMD ["python", "bot.py"]
