FROM python:3.11-slim

WORKDIR /app

# Copy the source code
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Expose the default port
EXPOSE 9333

# Default entrypoint
ENTRYPOINT ["python", "icsi_coin_server.py"]
