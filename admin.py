from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import APIKeyCookie
from urllib.parse import quote
import database
import os
import json
from google import genai
import assemblyai as aai
from payment_gateways import YooMoneyGateway, NowPaymentsGateway
from config import (
    ADMIN_PASSWORD,
    ADMIN_PORT,
    YOOMONEY_WALLET,
    YOOMONEY_SECRET,
    NOWPAYMENTS_API_KEY,
    NOWPAYMENTS_IPN_SECRET,
    ADMIN_ID,
)
import logging
import web_routes

logger = logging.getLogger(__name__)

app = FastAPI(title="NeuroNanoBanana Admin")
app.include_router(web_routes.router)
templates = Jinja2Templates(directory="templates")
COOKIE_NAME = "admin_session"
cookie_sec = APIKeyCookie(name=COOKIE_NAME, auto_error=False)

async def get_current_user(admin_session: str = Depends(cookie_sec)):
    if not admin_session: return None
    db_password = await database.get_setting("ADMIN_PASSWORD")
    actual_password = db_password or ADMIN_PASSWORD
    if admin_session != actual_password: return None
    return "admin"

# Root is now handled by web_routes (landing page / generator)
# /admin is available for admin panel

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request): return templates.TemplateResponse("login.html", {"request": request})

@app.get("/oferta", response_class=HTMLResponse)
async def read_oferta(request: Request):
    return templates.TemplateResponse("oferta.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def read_privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.post("/login")
async def login_post(response: Response, password: str = Form(...)):
    db_password = await database.get_setting("ADMIN_PASSWORD")
    actual_password = db_password or ADMIN_PASSWORD
    if password == actual_password:
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key=COOKIE_NAME, value=actual_password)
        return response
    return RedirectResponse(url="/login?error=1", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login")
    response.delete_cookie(COOKIE_NAME)
    return response

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    stats = await database.get_admin_stats()
    today_stats = await database.get_today_stats()
    month_stats = await database.get_month_stats()
    from config import IMAGE_MODEL, TEXT_MODEL
    image_model = await database.get_setting("IMAGE_MODEL") or IMAGE_MODEL or "gemini-3-pro-image-preview"
    text_model = await database.get_setting("TEXT_MODEL") or TEXT_MODEL or "gemini-2.0-flash"
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats, "today": today_stats, "month": month_stats, "image_model": image_model, "text_model": text_model, "page": "dashboard"})

@app.get("/admin/users", response_class=HTMLResponse)
async def users_list(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    
    # Telegram users
    tg_users_raw = await database.get_all_users()
    users = []
    for u in tg_users_raw:
        u_dict = dict(u)
        u_dict['total_count'] = await database.get_user_total_count(u['telegram_id'])
        u_dict['remaining'] = u['daily_limit']
        u_dict['is_admin_bool'] = await database.is_user_admin(u['telegram_id'])
        u_dict['type'] = 'TG'
        users.append(u_dict)
    
    # Web users (active sessions)
    web_users_raw = await database.get_all_web_sessions()
    for w in web_users_raw:
        w_dict = dict(w)
        # For display, we use part of token as tid
        users.append({
            'telegram_id': w_dict['token'][:8],
            'token': w_dict['token'],
            'full_name': "Web User",
            'username': 'Web Access',
            'total_count': '—',
            'remaining': w_dict.get('balance', 0),
            'is_admin_bool': False,
            'is_blocked': w_dict.get('is_used', 0) == 1,
            'last_active': w_dict.get('created_at'),
            'type': 'WEB'
        })
        
    return templates.TemplateResponse("users.html", {"request": request, "users": users, "page": "users"})


@app.post("/admin/users/create")
async def create_user(
    request: Request,
    telegram_id: int = Form(...),
    username: str = Form(""),
    full_name: str = Form(""),
    daily_limit: int = Form(0),
    is_admin: int = Form(0),
    user=Depends(get_current_user),
):
    """Manual user creation from admin panel."""
    if not user:
        return RedirectResponse(url="/login")

    # Upsert user with provided data
    import aiosqlite
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, daily_limit, is_admin)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                daily_limit = excluded.daily_limit,
                is_admin = excluded.is_admin
            """,
            (telegram_id, username or None, full_name or None, daily_limit, 1 if is_admin else 0),
        )
        await db.commit()

    await database.log_audit(
        f"Admin {user}",
        "Create User",
        f"User {telegram_id} ({username or full_name or 'no name'}) created/updated manually",
    )
    return RedirectResponse(
        url="/admin/users?msg=" + quote("Пользователь сохранен."),
        status_code=status.HTTP_303_SEE_OTHER,
    )

@app.get("/admin/users/{tid}", response_class=HTMLResponse)
async def user_detail(tid: int, request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    user_data_raw = await database.get_user(tid)
    if not user_data_raw: raise HTTPException(status_code=404, detail="User not found")
    user_data = dict(user_data_raw)
    user_data['total_count'] = await database.get_user_total_count(tid)
    user_data['remaining'] = user_data['daily_limit']
    user_data['is_admin_bool'] = await database.is_user_admin(tid)
    generations = await database.get_user_generations(tid, limit=100)
    total_api_cost = sum(g['api_cost'] for g in generations)
    return templates.TemplateResponse("user_detail.html", {"request": request, "user_data": user_data, "generations": generations, "total_api_cost": total_api_cost, "page": "users"})

@app.post("/admin/users/{tid}/limit")
async def update_limit(tid: int, remaining: int = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.set_user_limit(tid, remaining)
    await database.log_audit(f"Admin {user}", "Change Limit", f"User {tid} set to {remaining}")
    return RedirectResponse(url=f"/admin/users/{tid}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/add_limit")
async def add_limit(tid: int, amount: int = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.add_user_limit(tid, amount)
    await database.log_audit(f"Admin {user}", "Add Limit", f"User {tid} added {amount}")
    return RedirectResponse(url=f"/admin/users/{tid}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/block")
async def block_user(tid: int, blocked: str = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    is_blocked = (blocked == "1" or blocked.lower() == "true")
    await database.set_user_block(tid, is_blocked)
    await database.log_audit(f"Admin {user}", "Block/Unblock", f"User {tid} blocked={is_blocked}")
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/admin")
async def toggle_admin(tid: int, admin: str = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    is_admin = (admin == "1" or admin.lower() == "true")
    await database.set_user_admin_status(tid, is_admin)
    await database.log_audit(f"Admin {user}", "Change Role", f"User {tid} admin={is_admin}")
    return RedirectResponse(url="/admin/users?msg=" + quote("Роль обновлена."), status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/delete")
async def delete_user_route(tid: int, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.delete_user(tid)
    await database.log_audit(f"Admin {user}", "Delete User", f"User {tid} deleted")
    return RedirectResponse(url="/admin/users?msg=" + quote("Пользователь удален."), status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/delete_web")
async def delete_web_session_route(token: str = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.delete_web_session(token)
    await database.log_audit(f"Admin {user}", "Delete Web Session", f"Token {token} deleted")
    return RedirectResponse(url="/admin/users?msg=" + quote("Веб-сессия удалена."), status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/pricing/{pid}")
async def update_pricing_route(pid: int, api_cost: float = Form(...), sale_price: float = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.update_pricing(pid, api_cost, sale_price)
    return RedirectResponse(url="/admin/pricing?msg=" + quote("Цены обновлены."), status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/pricing", response_class=HTMLResponse)
async def pricing_list(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    pricing = await database.get_pricing()
    return templates.TemplateResponse("pricing.html", {"request": request, "pricing": pricing, "page": "pricing"})

@app.get("/admin/orders", response_class=HTMLResponse)
async def orders_list(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    transactions = await database.get_all_transactions()
    return templates.TemplateResponse("orders.html", {"request": request, "transactions": transactions, "page": "orders"})

@app.get("/admin/settings", response_class=HTMLResponse)
async def settings_get(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    db_settings = await database.get_all_settings()
    from config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ASSEMBLYAI_KEY, IMAGE_MODEL, TEXT_MODEL
    settings = {
        "TELEGRAM_BOT_TOKEN": db_settings.get("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        "GEMINI_API_KEY": db_settings.get("GEMINI_API_KEY", GEMINI_API_KEY),
        "ASSEMBLYAI_KEY": db_settings.get("ASSEMBLYAI_KEY", ASSEMBLYAI_KEY),
        "IMAGE_MODEL": db_settings.get("IMAGE_MODEL", IMAGE_MODEL),
        "TEXT_MODEL": db_settings.get("TEXT_MODEL", TEXT_MODEL),
        "ADMIN_PASSWORD": db_settings.get("ADMIN_PASSWORD", ADMIN_PASSWORD),
        "YOOMONEY_WALLET": db_settings.get("YOOMONEY_WALLET", YOOMONEY_WALLET),
        "YOOMONEY_SECRET": db_settings.get("YOOMONEY_SECRET", YOOMONEY_SECRET),
        "NOWPAYMENTS_API_KEY": db_settings.get("NOWPAYMENTS_API_KEY", NOWPAYMENTS_API_KEY),
        "NOWPAYMENTS_IPN_SECRET": db_settings.get("NOWPAYMENTS_IPN_SECRET", NOWPAYMENTS_IPN_SECRET),
    }
    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings, "page": "settings"})

@app.post("/admin/settings")
async def settings_post(
    request: Request, 
    TELEGRAM_BOT_TOKEN: str = Form(...), 
    GEMINI_API_KEY: str = Form(...), 
    ASSEMBLYAI_KEY: str = Form(...), 
    IMAGE_MODEL: str = Form(...), 
    TEXT_MODEL: str = Form(...), 
    YOOMONEY_WALLET: str = Form(""),
    YOOMONEY_SECRET: str = Form(""),
    NOWPAYMENTS_API_KEY: str = Form(""),
    NOWPAYMENTS_IPN_SECRET: str = Form(""),
    ADMIN_PASSWORD_NEW: str = Form(""), 
    user=Depends(get_current_user)
):
    if not user: return RedirectResponse(url="/login")
    await database.set_setting("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    await database.set_setting("GEMINI_API_KEY", GEMINI_API_KEY)
    await database.set_setting("ASSEMBLYAI_KEY", ASSEMBLYAI_KEY)
    await database.set_setting("IMAGE_MODEL", IMAGE_MODEL)
    await database.set_setting("TEXT_MODEL", TEXT_MODEL)
    await database.set_setting("YOOMONEY_WALLET", YOOMONEY_WALLET)
    await database.set_setting("YOOMONEY_SECRET", YOOMONEY_SECRET)
    await database.set_setting("NOWPAYMENTS_API_KEY", NOWPAYMENTS_API_KEY)
    await database.set_setting("NOWPAYMENTS_IPN_SECRET", NOWPAYMENTS_IPN_SECRET)
    
    if ADMIN_PASSWORD_NEW.strip(): await database.set_setting("ADMIN_PASSWORD", ADMIN_PASSWORD_NEW.strip())
    await database.log_audit(f"Admin {user}", "Update Settings", "Keys or Models updated in DB")
    return RedirectResponse(url="/admin/settings?msg=" + quote("Настройки сохранены."), status_code=status.HTTP_303_SEE_OTHER)

# ── Payment Webhooks ─────────────────────────────────────────────────────────

@app.post("/api/webhooks/yoomoney")
async def yoomoney_webhook(request: Request):
    form_data = await request.form()
    data = dict(form_data)
    
    logger.info(f"YooMoney webhook received: {data}")
    
    secret = await database.get_setting("YOOMONEY_SECRET") or YOOMONEY_SECRET
    wallet = await database.get_setting("YOOMONEY_WALLET") or YOOMONEY_WALLET
    
    gw = YooMoneyGateway(wallet, secret)
    if gw.validate_callback(data):
        order_id = data.get("label")
        logger.info(f"YooMoney validation success for order: {order_id}")
        if order_id:
            if await database.complete_transaction(order_id):
                logger.info(f"Transaction {order_id} completed successfully.")
                await notify_user_payment(order_id)
                return Response(status_code=200)
            else:
                logger.warning(f"Transaction {order_id} could not be completed (not found or already paid).")
                return Response(status_code=200) # Still return 200 to acknowledge receipt
    else:
        logger.warning(f"YooMoney validation FAILED for data: {data}")
    return Response(status_code=400)

@app.post("/api/webhooks/nowpayments")
async def nowpayments_webhook(request: Request):
    signature = request.headers.get("x-nowpayments-sig")
    body = await request.body()
    
    ipn_secret = await database.get_setting("NOWPAYMENTS_IPN_SECRET") or NOWPAYMENTS_IPN_SECRET
    
    # Validate HMAC-SHA512 signature over sorted JSON body
    gw = NowPaymentsGateway(api_key="", ipn_secret=ipn_secret or "")
    if signature and gw.validate_callback(body.decode(), signature):
        data = json.loads(body)
        order_id = data.get("order_id")
        status = (data.get("payment_status") or "").lower()

        if not order_id:
            logger.warning("NOWPayments webhook without order_id: %s", data)
            return Response(status_code=400)

        # Accept finished, confirmed and partially_paid as successful payments
        if status in ["finished", "confirmed", "partially_paid"]:
            tx = await database.get_transaction(order_id)
            if not tx:
                logger.warning("NOWPayments webhook: transaction not found for order_id=%s", order_id)
                return Response(status_code=400)

            if await database.complete_transaction(order_id):
                # Notify user (credits already added in complete_transaction)
                await notify_user_payment(order_id)

                # Notify admin about crypto payment
                if hasattr(app.state, "bot_app"):
                    try:
                        price_amount = data.get("price_amount")
                        price_currency = data.get("price_currency")
                        user_id = tx["user_id"]

                        # Try to enrich user info from DB
                        user_row = await database.get_user(user_id)
                        if user_row:
                            u = dict(user_row)
                            user_info = f"{u.get('full_name') or '—'} (@{u.get('username') or '—'}, ID {user_id})"
                        else:
                            user_info = f"ID {user_id}"

                        text = (
                            "💰 <b>Оплата подтверждена (Crypto)</b>\n"
                            f"Сумма: <b>{price_amount} {price_currency}</b>\n"
                            f"Пакет: <b>{tx['generations']} ген.</b>\n"
                            f"Юзер: {user_info}\n"
                            f"Order ID: <code>{order_id}</code>"
                        )
                        await app.state.bot_app.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=text,
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error("Failed to notify admin about NOWPayments payment: %s", e)

                return Response(status_code=200)

    logger.warning("NOWPayments webhook validation failed")
    return Response(status_code=400)
    
@app.post("/admin/orders/{order_id}/confirm")
async def confirm_order_manual(order_id: str, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    if await database.complete_transaction(order_id):
        await notify_user_payment(order_id)
        await database.log_audit(f"Admin {user}", "Manual Confirm", f"Order {order_id} confirmed manually")
        return RedirectResponse(url="/admin/orders?msg=Order+confirmed", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/admin/orders?error=Already+paid+or+not+found", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/orders/{order_id}/reject")
async def confirm_order_reject(order_id: str, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    if await database.reject_transaction(order_id):
        await database.log_audit(f"Admin {user}", "Reject Order", f"Order {order_id} rejected")
        return RedirectResponse(url="/admin/orders?msg=Order+rejected", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/admin/orders?error=Could+not+reject", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/orders/{order_id}/restore")
async def confirm_order_restore(order_id: str, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    if await database.restore_transaction(order_id):
        await database.log_audit(f"Admin {user}", "Restore Order", f"Order {order_id} restored")
        return RedirectResponse(url="/admin/orders?msg=Order+restored", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/admin/orders?error=Could+not+restore", status_code=status.HTTP_303_SEE_OTHER)

async def notify_user_payment(order_id):
    tx = await database.get_transaction(order_id)
    if not tx:
        return

    user_id_str = str(tx['user_id'])
    is_web_order = order_id.startswith("web-")

    # Web order: user_id holds the invite token (first 36 chars)
    if is_web_order:
        try:
            token_prefix = user_id_str  # stored as token[:36]
            # Find the actual token
            import aiosqlite
            async with aiosqlite.connect(database.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT token FROM invite_tokens WHERE token LIKE ?",
                    (token_prefix + "%",)
                ) as cursor:
                    row = await cursor.fetchone()
                if row:
                    token = row["token"]
                    gens = tx["generations"]
                    await db.execute(
                        "UPDATE invite_tokens SET generations_left = generations_left + ? WHERE token = ?",
                        (gens, token)
                    )
                    await db.commit()
                    print(f"[web-payment] Credited {gens} gens to token {token[:12]}… (order {order_id})")
        except Exception as e:
            print(f"Error crediting web token: {e}")
        return

    # Telegram order: send notification message
    if hasattr(app.state, 'bot_app'):
        try:
            await app.state.bot_app.bot.send_message(
                chat_id=tx['user_id'],
                text=f"✅ <b>Оплата получена!</b>\nНачислено: <b>{tx['generations']}</b> генераций.\nНомер заказа: <code>{order_id}</code>",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error notifying user: {e}")


@app.post("/admin/test_keys")
async def test_keys(user=Depends(get_current_user)):
    if not user: return {"success": False, "error": "Not authorized"}
    gemini_key = await database.get_setting("GEMINI_API_KEY")
    assembly_key = await database.get_setting("ASSEMBLYAI_KEY")
    results = {}
    if gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            client.models.generate_content(model='gemini-1.5-flash', contents="test")
            results["gemini"] = {"ok": True}
        except Exception as e: results["gemini"] = {"ok": False, "error": str(e)}
    else: results["gemini"] = {"ok": False, "error": "Key missing"}
    if assembly_key:
        try:
            import requests
            headers = {"authorization": assembly_key}
            response = requests.get("https://api.assemblyai.com/v2/account", headers=headers, timeout=5)
            if response.status_code == 200: results["assembly"] = {"ok": True}
            else: results["assembly"] = {"ok": False, "error": f"Status {response.status_code}"}
        except Exception as e: results["assembly"] = {"ok": False, "error": str(e)}
    else: results["assembly"] = {"ok": False, "error": "Key missing"}
    return results

@app.get("/admin/audit", response_class=HTMLResponse)
async def audit_list(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    logs = await database.get_audit_logs(limit=200)
    return templates.TemplateResponse("audit.html", {"request": request, "logs": logs, "page": "audit"})

@app.get("/admin/logs", response_class=HTMLResponse)
async def view_logs(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    log_content = "Лог-файл пуст или не найден."
    log_path = "/app/logs/app.log"
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            lines = f.readlines()
            log_content = "".join(lines[-200:])
    return templates.TemplateResponse("logs.html", {"request": request, "log_content": log_content, "page": "logs"})

@app.post("/admin/invite/create")
async def admin_create_invite(hours: int = 48, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    import secrets
    token = secrets.token_urlsafe(24)
    from datetime import datetime, timedelta, timezone
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    await database.create_invite_token(token, expires_at)
    # Return JSON for JS to handle
    from config import ADMIN_URL
    invite_url = f"{ADMIN_URL.rstrip('/')}/try?token={token}"
    return {"token": token, "invite_url": invite_url}

@app.get("/admin/invite/list")
async def admin_list_invites(user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    tokens_raw = await database.get_all_invite_tokens()
    return {"tokens": [dict(t) for t in tokens_raw]}
