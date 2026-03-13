#!/bin/bash
cd /home/debian/Telegram-image-bot
sudo fuser -k 8080/tcp || true
sudo docker compose restart bot
echo "Docker bot restarted"
