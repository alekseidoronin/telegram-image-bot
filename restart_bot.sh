#!/bin/bash
# Script to restart the bot daily at 4:00 AM
cd /home/debian/Telegram-image-bot
docker compose restart bot
echo "$(date): Bot restarted by cron" >> restart.log
