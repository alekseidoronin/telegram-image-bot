#!/bin/bash
cd /home/debian/Telegram-image-bot
sudo pkill -f "python bot.py" || true
# wait for process to die
sleep 2
nohup sudo python bot.py > /dev/null 2>&1 &
echo "Bot started"
