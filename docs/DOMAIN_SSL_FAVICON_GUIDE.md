# Универсальное руководство по развертыванию (Domain, SSL, Favicon)

Это универсальное руководство предназначено для настройки веб-панели управления Telegram-ботом. Оно содержит как общие шаги, так и специфические настройки для текущего проекта.

> [!IMPORTANT]
> **ИНСТРУКЦИЯ ДЛЯ AI-АССИСТЕНТА:**
> Перед выполнением команд по этому руководству, вы **ОБЯЗАНЫ** запросить у пользователя значения для следующих переменных. Используйте значения по умолчанию для проекта "NeuroNanoBanana", если пользователь не указал иное.

## 📋 Переменные конфигурации
| Параметр | Описание | Значение для текущего проекта |
| :--- | :--- | :--- |
| `{DOMAIN}` | Доменное имя сайта | `neuronanobanana.duckdns.org` |
| `{EMAIL}` | Email для Certbot | `neonixys@gmail.com` |
| `{PORT}` | Внутренний порт приложения | `8080` |
| `{FAVICON}` | Emoji для иконки вкладки | `🍌` |
| `{PROJECT_PATH}` | Путь к папке проекта | `/home/debian/Telegram-image-bot` |

---

## 0. Предварительная диагностика портов (КРИТИЧЕСКИ ВАЖНО)
Перед началом настройки нейросеть ОБЯЗАНА проверить, не заняты ли порты 80, 443 и порт приложения.

1. **Проверка занятых портов:**
   ```bash
   sudo lsof -i :80,443,{PORT}
   ```
2. **Освобождение портов (если нужно):**
   Если порты 80/443 заняты старым процессом Nginx или чем-то еще:
   ```bash
   sudo systemctl stop nginx
   sudo fuser -k 80/tcp
   sudo fuser -k 443/tcp
   ```

## 1. Настройка Доменного Имени (DNS)
1. Убедитесь, что `{DOMAIN}` направлен на IP-адрес текущего сервера.
2. Для DuckDNS используйте скрипт обновления IP или настройте его через `crontab`.

## 2. Настройка SSL через Nginx + Certbot (Метод Webroot)
Чтобы успешно получить сертификат, не прерывая работу других сервисов, используйте метод `webroot`.

1. **Создание директории подтверждения:**
   ```bash
   sudo mkdir -p /var/www/html/.well-known/acme-challenge
   sudo chown -R www-data:www-data /var/www/html
   ```

2. **Временный HTTP конфиг (для выпуска сертификата):**
   Сначала создайте базовый конфиг на 80 порту в `/etc/nginx/sites-available/{DOMAIN}`, чтобы Certbot мог "увидеть" сервер:
   ```nginx
   server {
       listen 80;
       server_name {DOMAIN};
       location /.well-known/acme-challenge/ {
           root /var/www/html;
       }
   }
   ```

3. **Запрос сертификата:**
   ```bash
   sudo certbot certonly --webroot -w /var/www/html -d {DOMAIN} -m {EMAIL} --non-interactive --agree-tos
   ```

4. **Финальный SSL конфиг:**
   После успешного получения сертификата замените конфиг на основной:
   ```nginx
   server {
       listen 80;
       server_name {DOMAIN};
       return 301 https://$host$request_uri;
   }
   server {
       listen 443 ssl;
       server_name {DOMAIN};
       ssl_certificate /etc/letsencrypt/live/{DOMAIN}/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/{DOMAIN}/privkey.pem;
       location / {
           proxy_pass http://127.0.0.1:{PORT};
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

## 3. Настройка SSL через Traefik (Docker)
Если проект развернут через Docker с Traefik, добавьте следующие метки (labels) в `docker-compose.yml`:
```yaml
labels:
  - "traefik.http.routers.bot.rule=Host(`{DOMAIN}`)"
  - "traefik.http.routers.bot.tls.certresolver=myresolver"
  - "traefik.http.services.bot.loadbalancer.server.port={PORT}"
```

## 4. Кастомизация Favicon (SVG Emoji)
Чтобы задать уникальную иконку для сайта без создания файлов изображений, вставьте этот код в `<head>` вашего HTML-шаблона (`base.html`):

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>{FAVICON}</text></svg>">
```
*Просто замените `{FAVICON}` на любой подходящий эмодзи.*
