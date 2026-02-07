FROM python:3.11

WORKDIR /app

# Copy the source code
# Copy the source code
COPY templates /app/templates
COPY static /app/static
COPY . /app
RUN cat icsi_coin_server.py


# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Expose the default port
EXPOSE 9333

# Default entrypoint
ENTRYPOINT ["python", "icsi_coin_server.py"]
