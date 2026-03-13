#!/bin/bash
echo "Stopping Nginx completely (since Traefik is handling SSL on port 80/443)..."
sudo systemctl stop nginx
sudo systemctl disable nginx
sudo rm -f /etc/nginx/sites-enabled/neuronanobanana

echo "Restarting Traefik in n8n..."
# We need to make sure the network exists. If n8n created the network, it's called n8n_default usually
cd /home/debian/n8n && sudo docker-compose up -d

echo "Rebuilding and restarting the Bot with Traefik labels..."
cd /home/debian/Telegram-image-bot

# Start the bot on the Traefik network
sudo docker-compose down
sudo docker-compose up -d --build

echo "Done! Traefik should now route https://neuronanobanana.duckdns.org to the bot on port 8080."
