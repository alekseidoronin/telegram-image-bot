#!/bin/bash
cd /home/debian/Telegram-image-bot
sudo pkill -f "python" || true
sleep 2
nohup sudo /usr/local/bin/python3.11 bot.py > bot_output.log 2>&1 < /dev/null &
echo "Bot started"
