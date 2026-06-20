FROM python:3.12-slim

# Install git, required by pipeline runner for initial repository clone
# Also install docker CLI so we can interact with the host docker daemon
RUN apt-get update && apt-get install -y git docker.io && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for caching
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the entire project
COPY . .

# Set environment variable so the backend knows it's running inside Docker
ENV IN_DOCKER=true

EXPOSE 5000

# Run the backend
CMD ["python", "backend/app.py"]
