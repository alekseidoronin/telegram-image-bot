#!/bin/bash
set -e
cd /home/debian/Telegram-image-bot
echo "🔄 Stopping existing container..."
sudo fuser -k 8080/tcp 2>/dev/null || true
echo "🔨 Rebuilding Docker image..."
sudo docker compose build bot
echo "🚀 Starting bot..."
sudo docker compose up -d bot
echo "✅ Docker bot restarted successfully"
sudo docker compose logs --tail=30 bot
