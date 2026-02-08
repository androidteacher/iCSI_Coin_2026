FROM python:3.11

WORKDIR /app

# Copy the source code
COPY . /app

# Install system dependencies for cryptography/scrypt
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Expose the default port
EXPOSE 9333

# Default entrypoint
ENTRYPOINT ["python", "icsi_coin_server.py"]
