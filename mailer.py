import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

# SMTP Configuration (Gmail)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "neonixys@gmail.com"
SMTP_PASSWORD = os.getenv("MAIL_PASSWORD", "")

def send_access_link(email, link):
    """
    Sends a beautiful HTML email with an access link to the specified email address.
    """
    if not SMTP_PASSWORD:
        logger.error("send_access_link: SMTP_PASSWORD is not set. Email not sent.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Ваш доступ к NeuroNanoBanana 🍌"
        msg["From"] = f"NeuroNanoBanana <{SMTP_USER}>"
        msg["To"] = email

        html = f"""
        <html>
        <body style="font-family: 'Inter', sans-serif; background-color: #0a0c10; padding: 40px; color: #f8fafc; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #161a22; border: 1px solid #2d3748; border-radius: 24px; padding: 40px; box-shadow: 0 20px 50px rgba(0,0,0,0.5);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <div style="font-size: 50px; margin-bottom: 10px;">🍌</div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -1px;">NeuroNanoBanana</h1>
                    <p style="color: #94a3b8; font-size: 14px; margin-top: 5px; text-transform: uppercase; letter-spacing: 2px;">Web Access Granted</p>
                </div>
                
                <div style="height: 1px; background: linear-gradient(to right, transparent, #2b59ff, transparent); margin: 30px 0;"></div>
                
                <p style="font-size: 18px; line-height: 1.6; color: #ffffff;"><b>Привет!</b></p>
                <p style="font-size: 16px; line-height: 1.6; color: #94a3b8;">Мы вручную проверили твой запрос. Доступ к веб-панели генерации изображений <b>активирован</b>.</p>
                
                <div style="background-color: #1e2532; border-radius: 16px; padding: 25px; margin: 30px 0; border: 1px solid #2d3748;">
                    <p style="margin: 0; font-size: 14px; color: #64748b; margin-bottom: 10px;">Твоя персональная ссылка:</p>
                    <div style="text-align: center; margin: 20px 0;">
                        <a href="{link}" style="display: inline-block; background-color: #2b59ff; color: #ffffff; padding: 18px 40px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 18px; box-shadow: 0 10px 25px rgba(43, 89, 255, 0.4);">Войти в Banana Web</a>
                    </div>
                </div>
                
                <p style="font-size: 13px; color: #64748b; line-height: 1.5;">
                    💡 <b>Важно:</b> Ссылка является одноразовой. При первом клике она «привяжется» к твоему текущему браузеру. Не открывай её в режиме инкогнито, если хочешь сохранить доступ.
                </p>
                
                <div style="height: 1px; background: #2d3748; margin: 30px 0;"></div>
                
                <p style="font-size: 12px; color: #4a5568; text-align: center; margin: 0;">
                    &copy; 2026 NeuroNanoBanana Lab. Генерируй будущее сегодня.<br>
                    <a href="https://t.me/NanaoBananaBot" style="color: #2b59ff; text-decoration: none;">Наш Telegram</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        part_html = MIMEText(html, "html")
        msg.attach(part_html)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, email, msg.as_string())
        
        logger.info(f"send_access_link: Successfully sent email to {email}")
        return True
    except Exception as e:
        logger.error(f"send_access_link: Failed to send email to {email}: {e}")
        return False
