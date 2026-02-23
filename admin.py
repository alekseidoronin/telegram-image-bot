"""
Admin Panel: FastAPI app with Jinja2 templates.
"""

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import APIKeyCookie
from urllib.parse import quote
import database
from config import ADMIN_PASSWORD, ADMIN_PORT
import uvicorn
import os

app = FastAPI(title="Nano Banana Admin")

# Templates setup
templates = Jinja2Templates(directory="templates")

# Simple cookie-based auth
COOKIE_NAME = "admin_session"
cookie_sec = APIKeyCookie(name=COOKIE_NAME, auto_error=False)

async def get_current_user(admin_session: str = Depends(cookie_sec)):
    if not admin_session:
        return None
    # Check against DB setting first, then fall back to config
    db_password = await database.get_setting("ADMIN_PASSWORD")
    actual_password = db_password or ADMIN_PASSWORD
    if admin_session != actual_password:
        return None
    return "admin"


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

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
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie(COOKIE_NAME)
    return response


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")

    stats = await database.get_stats()
    today_stats = await database.get_today_stats()
    month_stats = await database.get_month_stats()

    # Dynamic model names from DB
    from config import IMAGE_MODEL, TEXT_MODEL
    image_model = await database.get_setting("IMAGE_MODEL", IMAGE_MODEL)
    text_model = await database.get_setting("TEXT_MODEL", TEXT_MODEL)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "today": today_stats,
        "month": month_stats,
        "image_model": image_model,
        "text_model": text_model,
        "page": "dashboard",
    })


# ── Users ────────────────────────────────────────────────────────────────────

@app.get("/admin/users", response_class=HTMLResponse)
async def users_list(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")

    users_raw = await database.get_all_users()
    users = []
    for u in users_raw:
        u_dict = dict(u)
        u_dict['total_count'] = await database.get_user_total_count(u['telegram_id'])
        u_dict['remaining'] = u['daily_limit']
        u_dict['is_admin_bool'] = await database.is_user_admin(u['telegram_id'])
        users.append(u_dict)

    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "page": "users",
    })

@app.get("/admin/users/{tid}", response_class=HTMLResponse)
async def user_detail(tid: int, request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")

    user_data_raw = await database.get_user(tid)
    if not user_data_raw:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = dict(user_data_raw)
    user_data['total_count'] = await database.get_user_total_count(tid)
    user_data['remaining'] = user_data['daily_limit']
    user_data['is_admin_bool'] = await database.is_user_admin(tid)

    generations = await database.get_user_generations(tid, limit=100)

    # Calculate totals
    total_api_cost = sum(g['api_cost'] for g in generations)

    return templates.TemplateResponse("user_detail.html", {
        "request": request,
        "user_data": user_data,
        "generations": generations,
        "total_api_cost": total_api_cost,
        "page": "users",
    })

@app.post("/admin/users/{tid}/limit")
async def update_limit(tid: int, remaining: int = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    await database.set_user_limit(tid, remaining)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/block")
async def block_user(tid: int, blocked: str = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    is_blocked = (blocked == "1" or blocked.lower() == "true")
    await database.set_user_block(tid, is_blocked)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/admin")
async def toggle_admin(tid: int, admin: str = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    is_admin = (admin == "1" or admin.lower() == "true")
    await database.set_user_admin_status(tid, is_admin)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/delete")
async def delete_user_route(tid: int, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    # Prevent deleting the superadmin
    if tid == 632600126:
        return RedirectResponse(
            url="/admin/users?msg=" + quote("Нельзя удалить суперадмина."),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    await database.delete_user(tid)
    return RedirectResponse(
        url="/admin/users?msg=" + quote("Пользователь удален."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── Pricing ──────────────────────────────────────────────────────────────────

@app.get("/admin/pricing", response_class=HTMLResponse)
async def pricing_list(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")

    pricing = await database.get_pricing()
    return templates.TemplateResponse("pricing.html", {
        "request": request,
        "pricing": pricing,
        "page": "pricing",
    })

@app.post("/admin/pricing/{pid}")
async def update_pricing_route(pid: int, api_cost: float = Form(...), sale_price: float = Form(...), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    await database.update_pricing(pid, api_cost, sale_price)
    return RedirectResponse(url="/admin/pricing?msg=" + quote("Цены обновлены."), status_code=status.HTTP_303_SEE_OTHER)


# ── Settings ─────────────────────────────────────────────────────────────────

@app.get("/admin/settings", response_class=HTMLResponse)
async def settings_get(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")

    # Get settings from DB
    db_settings = await database.get_all_settings()

    # Defaults from config/env if not in DB
    from config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ASSEMBLYAI_KEY, IMAGE_MODEL, TEXT_MODEL

    settings = {
        "TELEGRAM_BOT_TOKEN": db_settings.get("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        "GEMINI_API_KEY": db_settings.get("GEMINI_API_KEY", GEMINI_API_KEY),
        "ASSEMBLYAI_KEY": db_settings.get("ASSEMBLYAI_KEY", ASSEMBLYAI_KEY),
        "IMAGE_MODEL": db_settings.get("IMAGE_MODEL", IMAGE_MODEL),
        "TEXT_MODEL": db_settings.get("TEXT_MODEL", TEXT_MODEL),
        "ADMIN_PASSWORD": db_settings.get("ADMIN_PASSWORD", ADMIN_PASSWORD),
    }

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "page": "settings",
    })

@app.post("/admin/settings")
async def settings_post(
    request: Request,
    TELEGRAM_BOT_TOKEN: str = Form(...),
    GEMINI_API_KEY: str = Form(...),
    ASSEMBLYAI_KEY: str = Form(...),
    IMAGE_MODEL: str = Form(...),
    TEXT_MODEL: str = Form(...),
    ADMIN_PASSWORD_NEW: str = Form(""),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/login")

    # Check if telegram token changed
    old_token = await database.get_setting("TELEGRAM_BOT_TOKEN")
    token_changed = old_token and old_token != TELEGRAM_BOT_TOKEN

    await database.set_setting("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    await database.set_setting("GEMINI_API_KEY", GEMINI_API_KEY)
    await database.set_setting("ASSEMBLYAI_KEY", ASSEMBLYAI_KEY)
    await database.set_setting("IMAGE_MODEL", IMAGE_MODEL)
    await database.set_setting("TEXT_MODEL", TEXT_MODEL)

    # Update admin password if provided
    password_changed = False
    if ADMIN_PASSWORD_NEW and ADMIN_PASSWORD_NEW.strip():
        await database.set_setting("ADMIN_PASSWORD", ADMIN_PASSWORD_NEW.strip())
        password_changed = True

    msg = "Настройки сохранены."
    if token_changed:
        msg += " Токен Telegram изменен — требуется перезапуск бота."
    if password_changed:
        msg += " Пароль админки изменен — перелогиньтесь."

    redirect = RedirectResponse(url="/admin/settings?msg=" + quote(msg), status_code=status.HTTP_303_SEE_OTHER)
    # If password changed, update cookie to new password
    if password_changed:
        redirect.set_cookie(key=COOKIE_NAME, value=ADMIN_PASSWORD_NEW.strip())
    return redirect


# ── Restart ──────────────────────────────────────────────────────────────────

@app.post("/admin/restart")
async def restart_bot_route(user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    import os
    import signal
    import threading

    print("Restart requested via Admin Panel. Terminating process...")

    def delayed_kill():
        import time
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=delayed_kill).start()

    return RedirectResponse(
        url="/admin/settings?msg=" + quote("Сигнал перезагрузки отправлен. Бот обновится в течение 10-20 секунд."),
        status_code=status.HTTP_303_SEE_OTHER,
    )
