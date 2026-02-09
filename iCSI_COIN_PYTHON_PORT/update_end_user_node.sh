#!/bin/bash
echo "Pulling latest changes from git..."
git pull
echo "Rebuilding end user node container..."
docker-compose -f end_user_node/docker-compose.yml up -d --build
echo "Process Complete!"
