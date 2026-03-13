#!/bin/bash
cd /home/debian/Telegram-image-bot
sudo pkill -f "python bot.py" || true
sudo pkill -f "python3 bot.py" || true
sleep 2
nohup sudo python3 bot.py > bot_output.log 2>&1 < /dev/null &
echo "Bot started"
