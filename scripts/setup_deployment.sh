#!/bin/bash

echo "Stopping Nginx and clearing ports..."
sudo systemctl stop nginx || true
sudo killall -9 nginx || true
sudo fuser -k 80/tcp || true
sudo fuser -k 443/tcp || true
sleep 2

# Remove broken default sites if any
sudo rm -f /etc/nginx/sites-enabled/default

# Clean up any broken letsencrypt config for this domain
# sudo rm -rf /etc/letsencrypt/live/neuronanobanana.duckdns.org || true

echo "Creating challenge directory for Certbot..."
sudo mkdir -p /var/www/html/.well-known/acme-challenge
sudo chown -R www-data:www-data /var/www/html
sudo chmod -R 755 /var/www/html

echo "Setting up temporary HTTP-only Nginx config..."
cat <<EOF > /tmp/neuronanobanana
server {
    listen 80;
    server_name neuronanobanana.duckdns.org;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo mv /tmp/neuronanobanana /etc/nginx/sites-available/neuronanobanana
sudo ln -sf /etc/nginx/sites-available/neuronanobanana /etc/nginx/sites-enabled/

echo "Starting Nginx..."
sudo systemctl start nginx
sleep 2

echo "Requesting SSL certificate..."
sudo certbot certonly --webroot -w /var/www/html -d neuronanobanana.duckdns.org --non-interactive --agree-tos -m neonixys@gmail.com --expand

# Keep track of exit code, only apply SSL config if cert was successfully issued
if [ $? -eq 0 ]; then
    echo "SSL Certificate issued successfully!"
    echo "Creating final Nginx SSL config..."
    cat <<EOF > /tmp/neuronanobanana
server {
    listen 80;
    server_name neuronanobanana.duckdns.org;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name neuronanobanana.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/neuronanobanana.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/neuronanobanana.duckdns.org/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    sudo mv /tmp/neuronanobanana /etc/nginx/sites-available/neuronanobanana
    sudo nginx -t && sudo systemctl restart nginx
    echo "Deployment complete! Your panel should be at https://neuronanobanana.duckdns.org"
else
    echo "CRITICAL ERROR: Certbot failed to issue a certificate."
    echo "Leaving Nginx in HTTP mode so that 404 errors can be debugged."
fi
