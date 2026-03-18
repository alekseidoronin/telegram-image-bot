"""
Web Routes — публичный веб-интерфейс для генерации изображений.

Эндпоинты:
  GET  /                  → редирект на /try?token=... или промпт-страница
  GET  /try?token=<tok>   → валидация токена, выдача сессии
  POST /web-generate      → генерация изображения (требует cookie-сессии)
  POST /web-buy?package=  → создание платёжной ссылки YooMoney
"""

import base64
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite
import bcrypt
from fastapi import APIRouter, Request, Response, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import database
import mailer
import image_service
from image_service import text_to_image, get_deduction_amount, get_real_api_cost
from config import (
    YOOMONEY_WALLET,
    YOOMONEY_SECRET,
    ADMIN_URL,
    ADMIN_PASSWORD,
    NOWPAYMENTS_API_KEY,
    NOWPAYMENTS_IPN_SECRET,
)


logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ── Session cookie ────────────────────────────────────────────────────────────
_SESSION_COOKIE = "web_session"
_SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

# ── Package definitions ───────────────────────────────────────────────────────
PACKAGES = {
    "single":   {"gens": 1,   "price": 15.0,  "label": "1 генерация"},
    "starter":  {"gens": 10,  "price": 100.0, "label": "10 генераций"},
    "standard": {"gens": 50,  "price": 400.0, "label": "50 генераций"},
    "pro":      {"gens": 100, "price": 700.0, "label": "100 генераций"},
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    """Extract real IP from headers (works behind Nginx/Traefik proxies)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _get_session_token(request: Request) -> Optional[str]:
    return request.cookies.get(_SESSION_COOKIE)


def _fingerprint(request: Request) -> str:
    """Simple fingerprint: IP + User-Agent hash."""
    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")
    raw = f"{ip}|{ua}"
    import hashlib
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


async def _get_session(request: Request):
    """
    Read the session token from cookie.
    """
    web_token = _get_session_token(request)
    if not web_token:
        return None
    
    # Check WebSessions
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM WebSessions WHERE token = ?', (web_token,)) as cursor:
            row = await cursor.fetchone()
            if row:
                res = dict(row)
                res["generations_left"] = res.get("balance", 0)
                return res

    # Fallback to invite_tokens
    row = await database.get_invite_token(web_token)
    return dict(row) if row else None


# ── GET / ─────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def web_index(request: Request):
    """
    Root: if the user has a valid session cookie → show the generator.
    Otherwise redirect to a landing / login page.
    """
    session = await _get_session(request)
    if session:
        remaining = session.get("generations_left", 0)
        payment_url = await _build_payment_url("standard", "web_direct")
        return templates.TemplateResponse("web_app.html", {
            "request": request,
            "remaining": remaining,
            "payment_url": payment_url,
            "error": None,
        })
    # No session — show an invite-required page
    return HTMLResponse(content=_landing_html(), status_code=200)


# ── Web Admin Login (password → web session) ──────────────────────────────────

@router.get("/web-admin-login", response_class=HTMLResponse)
async def web_admin_login_form(request: Request):
    """Simple email+password form to enter web generator as admin tester."""
    html = """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>NeuroNanoBanana — Web Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
  body { font-family:'Inter',sans-serif;background:#08080e;color:#e5e7eb;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:16px; }
  .card { max-width:360px;width:100%;background:#13131a;border-radius:18px;border:1px solid rgba(148,163,184,0.25);padding:28px 24px;box-shadow:0 18px 45px rgba(0,0,0,0.65); }
  h1 { font-size:1.4rem;margin-bottom:10px;background:linear-gradient(135deg,#7c4dff,#00e5ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:900; }
  p { font-size:0.9rem;color:#9ca3af;margin-bottom:18px;line-height:1.5; }
  label { display:block;font-size:0.8rem;color:#9ca3af;margin-bottom:6px;font-weight:600; }
  input[type=text], input[type=email], input[type=password] { width:100%;padding:10px 12px;border-radius:10px;border:1px solid #4b5563;background:#020617;color:#e5e7eb;font-family:inherit; }
  button { margin-top:16px;width:100%;padding:10px 14px;border-radius:10px;border:none;background:#7c4dff;color:#fff;font-weight:700;cursor:pointer; }
  .err { margin-top:10px;font-size:0.8rem;color:#f97373; }
  a.back { display:block;margin-top:14px;font-size:0.8rem;color:#9ca3af;text-decoration:none; }
</style></head>
<body>
  <div class="card">
    <h1>Web Admin доступ</h1>
    <p>Введите email и пароль администратора, чтобы протестировать веб‑генератор без Telegram‑бота.</p>
    <form method="post" action="/web-admin-login">
      <label>Email</label>
      <input type="email" name="email" placeholder="admin@neuronanobanana.local" autofocus required />
      <label style="margin-top:10px;">Пароль</label>
      <input type="password" name="password" required />
      <button type="submit">Войти в веб‑генератор</button>
    </form>
    <a href="/" class="back">← На главную</a>
  </div>
</body></html>"""
    return HTMLResponse(content=html, status_code=200)


@router.post("/web-admin-login")
async def web_admin_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """
    Authenticate against WebAccounts (email + password) and create a long-lived
    WebSession with a large balance for admin testing.
    """
    account = await database.get_web_account_by_email(email)
    ok = False
    if account is not None:
        pw_hash = account["password_hash"]
        if pw_hash:
            try:
                ok = bcrypt.checkpw(
                    password.encode("utf-8"),
                    pw_hash,
                )
            except Exception:
                ok = False

    is_admin = bool(account["is_admin"]) if account is not None else False

    if not ok or not account or not is_admin:
        # Re-render form with error
        html = f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>NeuroNanoBanana — Web Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
  body {{ font-family:'Inter',sans-serif;background:#08080e;color:#e5e7eb;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:16px; }}
  .card {{ max-width:360px;width:100%;background:#13131a;border-radius:18px;border:1px solid rgba(248,113,113,0.4);padding:28px 24px;box-shadow:0 18px 45px rgba(0,0,0,0.65); }}
  h1 {{ font-size:1.4rem;margin-bottom:10px;background:linear-gradient(135deg,#f97373,#fb7185);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:900; }}
  p {{ font-size:0.9rem;color:#fecaca;margin-bottom:18px;line-height:1.5; }}
  label {{ display:block;font-size:0.8rem;color:#9ca3af;margin-bottom:6px;font-weight:600; }}
  input[type=text], input[type=email], input[type=password] {{ width:100%;padding:10px 12px;border-radius:10px;border:1px solid #4b5563;background:#020617;color:#e5e7eb;font-family:inherit; }}
  button {{ margin-top:16px;width:100%;padding:10px 14px;border-radius:10px;border:none;background:#ef4444;color:#fff;font-weight:700;cursor:pointer; }}
  .err {{ margin-top:10px;font-size:0.8rem;color:#f97373; }}
  a.back {{ display:block;margin-top:14px;font-size:0.8rem;color:#9ca3af;text-decoration:none; }}
</style></head>
<body>
  <div class="card">
    <h1>Неверный логин или пароль</h1>
    <p>Email или пароль администратора указаны неверно. Повторите попытку.</p>
    <form method="post" action="/web-admin-login">
      <label>Email</label>
      <input type="email" name="email" value="{email}" autofocus required />
      <label style="margin-top:10px;">Пароль</label>
      <input type="password" name="password" required />
      <button type="submit">Попробовать снова</button>
      <div class="err">Проверьте раскладку, регистр символов и email.</div>
    </form>
    <a href="/" class="back">← На главную</a>
  </div>
</body></html>"""
        return HTMLResponse(content=html, status_code=401)

    # Password ok → create (or reuse) a dedicated WebSession with big balance.
    token = "web-admin"
    existing = await database.get_web_session(token)
    if not existing:
        await database.create_web_session(token, user_id=account["id"], balance=9999)

    redir = RedirectResponse(url="/", status_code=302)
    redir.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return redir


# ── Web Login (email + password for ordinary users) ─────────────────────────

_LOGIN_FORM_HTML = """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Вход — NeuroNanoBanana</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
  body{font-family:'Inter',sans-serif;background:#08080e;color:#e5e7eb;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:16px;}
  .card{max-width:360px;width:100%;background:#13131a;border-radius:18px;border:1px solid rgba(148,163,184,0.25);padding:28px 24px;box-shadow:0 18px 45px rgba(0,0,0,0.65);}
  h1{font-size:1.4rem;margin-bottom:10px;background:linear-gradient(135deg,#7c4dff,#00e5ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:900;}
  p{font-size:0.9rem;color:#9ca3af;margin-bottom:18px;line-height:1.5;}
  label{display:block;font-size:0.8rem;color:#9ca3af;margin-bottom:6px;font-weight:600;}
  input[type=email],input[type=password]{width:100%;padding:10px 12px;border-radius:10px;border:1px solid #4b5563;background:#020617;color:#e5e7eb;font-family:inherit;}
  button{margin-top:16px;width:100%;padding:10px 14px;border-radius:10px;border:none;background:#7c4dff;color:#fff;font-weight:700;cursor:pointer;}
  .err{margin-top:10px;font-size:0.8rem;color:#f97373;}
  a.link{display:block;margin-top:14px;font-size:0.8rem;color:#9ca3af;text-decoration:none;}
</style></head><body>
  <div class="card">
    <h1>Вход в кабинет</h1>
    <p>Введите email и пароль, чтобы войти в веб‑приложение.</p>
    <form method="post" action="/web-login">
      <label>Email</label>
      <input type="email" name="email" required placeholder="your@email.com" />
      <label style="margin-top:10px;">Пароль</label>
      <input type="password" name="password" required />
      <button type="submit">Войти</button>
      <div class="err" id="err"></div>
    </form>
    <a href="/" class="link">← На главную</a>
    <a href="/web-register" class="link">Нет аккаунта? Запросите доступ или задайте пароль по ссылке из письма.</a>
  </div>
</body></html>"""


@router.get("/web-login", response_class=HTMLResponse)
async def web_login_form(request: Request):
    """Login form for web users (email + password)."""
    session = await _get_session(request)
    if session:
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(content=_LOGIN_FORM_HTML)


@router.post("/web-login")
async def web_login_post(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
):
    """Authenticate via WebAccounts and set session cookie."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return HTMLResponse(
            content=_LOGIN_FORM_HTML.replace('id="err"></div>', 'id="err">Укажите корректный email.</div>'),
            status_code=400,
        )
    account = await database.get_web_account_by_email(email)
    if not account:
        return HTMLResponse(
            content=_LOGIN_FORM_HTML.replace('id="err"></div>', 'id="err">Аккаунт не найден. Войдите по ссылке из приглашения или запросите доступ.</div>'),
            status_code=401,
        )
    pw_hash = account["password_hash"]
    if not pw_hash:
        return HTMLResponse(
            content=_LOGIN_FORM_HTML.replace('id="err"></div>', 'id="err">Пароль ещё не задан. Задайте пароль по ссылке из письма (раздел «Профиль» или /web-register?token=...).</div>'),
            status_code=401,
        )
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), pw_hash)
    except Exception:
        ok = False
    if not ok:
        return HTMLResponse(
            content=_LOGIN_FORM_HTML.replace('id="err"></div>', 'id="err">Неверный пароль.</div>'),
            status_code=401,
        )
    account_id = account["id"]
    existing = await database.get_web_session_by_account_id(account_id)
    if existing:
        session_token = existing["token"]
    else:
        session_token = secrets.token_urlsafe(32)
        await database.create_web_session(session_token, user_id=account_id, balance=0)
    redir = RedirectResponse(url="/", status_code=302)
    redir.set_cookie(
        key=_SESSION_COOKIE,
        value=session_token,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return redir


# ── Web Register (set password for invite-linked account) ─────────────────────

@router.get("/web-register", response_class=HTMLResponse)
async def web_register_form(request: Request, token: str = ""):
    """Set password for account linked to invite. Requires ?token=... from invite link."""
    if not token:
        return HTMLResponse(content="""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"/><title>Задать пароль</title></head><body style="font-family:Inter;background:#0a0c10;color:#e5e7eb;padding:40px;text-align:center;">
        <p>Чтобы задать пароль, перейдите по ссылке из письма с приглашением.</p>
        <a href="/">На главную</a> | <a href="/web-login">Вход</a>
        </body></html>""", status_code=400)
    row = await database.get_invite_token(token)
    if not row:
        return _error_page("Ссылка недействительна или истекла.")
    row = dict(row)
    email = (row.get("email") or "").strip()
    if not email:
        wu = await database.get_web_user(token)
        email = (dict(wu).get("email") or "").strip() if wu else ""
    if not email:
        return _error_page("По этой ссылке нельзя задать пароль. Используйте ссылку из письма.")
    account = await database.get_web_account_by_email(email)
    if not account:
        return _error_page("Аккаунт не найден.")
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Задать пароль — NeuroNanoBanana</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
  body{{font-family:'Inter',sans-serif;background:#08080e;color:#e5e7eb;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:16px;}}
  .card{{max-width:360px;width:100%;background:#13131a;border-radius:18px;border:1px solid rgba(148,163,184,0.25);padding:28px 24px;}}
  h1{{font-size:1.4rem;margin-bottom:10px;font-weight:900;}}
  p{{font-size:0.9rem;color:#9ca3af;margin-bottom:18px;}}
  label{{display:block;font-size:0.8rem;color:#9ca3af;margin-bottom:6px;font-weight:600;}}
  input{{width:100%;padding:10px 12px;border-radius:10px;border:1px solid #4b5563;background:#020617;color:#e5e7eb;}}
  button{{margin-top:16px;width:100%;padding:10px 14px;border-radius:10px;border:none;background:#7c4dff;color:#fff;font-weight:700;cursor:pointer;}}
  .err{{margin-top:10px;font-size:0.8rem;color:#f97373;}}
  a{{font-size:0.8rem;color:#9ca3af;text-decoration:none;display:block;margin-top:10px;}}
</style></head><body>
  <div class="card">
    <h1>Задать пароль</h1>
    <p>Email: <strong>{email}</strong>. Задайте пароль, чтобы входить без ссылки.</p>
    <form method="post" action="/web-register">
      <input type="hidden" name="token" value="{token}" />
      <label>Новый пароль</label>
      <input type="password" name="password" required minlength="6" />
      <label style="margin-top:10px;">Повторите пароль</label>
      <input type="password" name="password2" required minlength="6" />
      <button type="submit">Сохранить пароль</button>
      <div class="err" id="err"></div>
    </form>
    <a href="/">На главную</a>
  </div>
</body></html>"""
    return HTMLResponse(content=html)


@router.post("/web-register")
async def web_register_post(
    request: Request,
    token: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
):
    """Set password for account linked to invite token."""
    if not token:
        return RedirectResponse(url="/web-register", status_code=302)
    row = await database.get_invite_token(token)
    if not row:
        return _error_page("Ссылка недействительна.")
    row = dict(row)
    email = (row.get("email") or "").strip()
    if not email:
        wu = await database.get_web_user(token)
        email = (dict(wu).get("email") or "").strip() if wu else ""
    if not email:
        return _error_page("Не удалось определить email.")
    if (password or "") != (password2 or ""):
        return RedirectResponse(url=f"/web-register?token={token}&err=nomatch", status_code=302)
    if len(password) < 6:
        return RedirectResponse(url=f"/web-register?token={token}&err=short", status_code=302)
    account = await database.get_web_account_by_email(email)
    if not account:
        return _error_page("Аккаунт не найден.")
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    await database.set_web_account_password(account["id"], pw_hash)
    redir = RedirectResponse(url="/?registered=1", status_code=302)
    redir.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return redir


# ── GET /auth?token=<tok> ───────────────────────────────────────────────────

@router.get("/auth", response_class=HTMLResponse)
async def web_auth_token(request: Request, response: Response, token: str = ""):
    """Validate token and set session."""
    if not token:
        return RedirectResponse(url="/", status_code=302)

    session_row = await database.get_web_session(token)
    if not session_row:
        return _error_page("Ссылка недействительна.")

    await database.use_web_session(token)
    await database.log_audit("Web User", "Web Login", f"Token: {token[:8]}...")

    redir = RedirectResponse(url="/", status_code=302)
    redir.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return redir


# ── GET /try?token=<tok> ──────────────────────────────────────────────────────

@router.get("/try", response_class=HTMLResponse)
async def web_try(request: Request, token: str = ""):
    """One-time invite link validation."""
    if not token:
        return RedirectResponse(url="/", status_code=302)

    row = await database.get_invite_token(token)

    if not row:
        return _error_page("Ссылка недействительна.")

    row = dict(row)

    # Check expiry
    try:
        expires_at = datetime.fromisoformat(row["expires_at"])
        # Make aware if naive
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return _error_page("Срок действия ссылки истёк.")
    except Exception:
        return _error_page("Ошибка проверки срока ссылки.")

    fp = _fingerprint(request)
    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")

    # First visit: lock the token to this fingerprint
    if not row["is_used"]:
        await database.activate_invite_token(token, fp, ip, ua)
        await database.log_audit("Web User", "Web Invite Activation", f"Token: {token[:8]}...")
    else:
        # Already used — verify same fingerprint
        stored_fp = row.get("fingerprint") or ""
        if stored_fp and stored_fp != fp:
            return _error_page("Эта ссылка уже была использована с другого устройства.")

    remaining = row.get("generations_left", 0)

    # Resolve email: from invite row or legacy WebUsers
    email = (row.get("email") or "").strip()
    if not email:
        web_user = await database.get_web_user(token)
        if web_user:
            wu = dict(web_user)
            email = (wu.get("email") or "").lower().strip()

    # Link invite to WebAccount (create account by email if needed)
    need_password = False
    if email and "@" in email:
        try:
            account, created = await database.get_or_create_web_account_for_invite(email)
            if account:
                await database.set_invite_account_id(token, account["id"])
                if not account.get("password_hash"):
                    need_password = True
        except Exception as e:
            logger.exception("Failed to link invite to WebAccount: %s", e)

    # Mirror into main users table for analytics
    try:
        if email:
            digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
            synthetic_id = int(digest[:10], 16) + 10_000_000_000
            existing = await database.get_user(synthetic_id)
            if not existing:
                await database.upsert_user(synthetic_id, email, email)
            await database.upsert_web_user(token, email)
    except Exception as e:
        logger.exception("Failed to sync web user into main users table: %s", e)

    payment_url = await _build_payment_url("standard", f"web_{token[:8]}")

    response = templates.TemplateResponse("web_app.html", {
        "request": request,
        "remaining": remaining,
        "payment_url": payment_url,
        "error": None,
        "need_password": need_password,
        "invite_token": token,
    })
    # Set session cookie = the token itself (long enough to last the session)
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return response


@router.post("/web-generate")
async def web_generate(request: Request):
    """
    Generate an image. Requires a valid session cookie.
    Accepts: prompt, mode, ratio, quality, model,
             image_b64 (img2img), images_b64 (multi) in JSON body.
    """
    session = await _get_session(request)
    if not session:
        return JSONResponse(status_code=401, content={"error": "Сессия не найдена. Откройте персональную ссылку заново."})

    if session.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(session["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                return JSONResponse(status_code=401, content={"error": "Сессия истекла."})
        except Exception:
            pass

    if session.get("generations_left", 0) <= 0:
        return JSONResponse(status_code=402, content={"error": "Генерации закончились"})

    # Parse body
    try:
        body        = await request.json()
        prompt      = (body.get("prompt") or "").strip()
        mode        = body.get("mode", "txt2img") or "txt2img"
        ratio       = body.get("ratio",   "1:1") or "1:1"
        quality     = body.get("quality", "1K")  or "1K"
        model       = (body.get("model") or "").strip()
        image_b64   = body.get("image_b64") or None    # img2img
        images_b64  = body.get("images_b64") or []     # multi
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Неверный формат запроса."})

    if not prompt:
        return JSONResponse(status_code=400, content={"error": "Промпт не может быть пустым."})
    if quality not in ("1K", "2K", "4K"):
        quality = "1K"

    api_key     = await database.get_setting("GEMINI_API_KEY")
    admin_model = await database.get_setting("IMAGE_MODEL")
    image_model = model if model else admin_model

    if not api_key:
        return JSONResponse(status_code=500, content={"error": "API ключ не настроен."})

    # Unified credit logic: determine how many credits this generation costs
    credits_needed = get_deduction_amount(image_model or "", quality)
    if credits_needed < 1:
        credits_needed = 1

    # Try to resolve platform user (shared with Telegram) via WebAccount
    platform_user = None
    platform_is_admin = False
    platform_tid = None
    # WebSessions: user_id = WebAccounts.id
    if "balance" in session and session.get("user_id"):
        try:
            acc_user = await database.get_user_by_web_account(session["user_id"])
            if acc_user:
                platform_user = acc_user
        except Exception:
            platform_user = None
    # Invite-based session with linked account_id
    if (not platform_user) and session.get("account_id"):
        try:
            acc_user = await database.get_user_by_web_account(session["account_id"])
            if acc_user:
                platform_user = acc_user
        except Exception:
            platform_user = None

    if platform_user:
        platform_tid = platform_user["telegram_id"]
        platform_is_admin = await database.is_user_admin(platform_tid)
        limit = platform_user["daily_limit"]
        # Админы и -1 (безлимит) не ограничиваются
        if (not platform_is_admin) and limit != -1 and limit < credits_needed:
            msg = (
                "⚠️ Недостаточно кредитов. Pro режим требует 3 кредита. "
                "Переключитесь на Standard (1 кредит) или пополните баланс."
                if (image_model or "").lower().find("pro") >= 0
                else "Генерации закончились."
            )
            return JSONResponse(status_code=402, content={"error": msg})
    else:
        # Старое поведение: используем WebSessions / invite_tokens
        if "balance" in session:
            # It's a WebSessions row (без связанного users)
            async with aiosqlite.connect(database.DB_PATH) as db:
                cursor = await db.execute(
                    "UPDATE WebSessions SET balance = balance - ? WHERE token = ? AND balance >= ?",
                    (credits_needed, session["token"], credits_needed),
                )
                await db.commit()
                if cursor.rowcount == 0:
                    msg = (
                        "⚠️ Недостаточно кредитов. Pro режим требует 3 кредита. "
                        "Переключитесь на Standard (1 кредит) или пополните баланс."
                        if (image_model or "").lower().find("pro") >= 0
                        else "Генерации закончились."
                    )
                    return JSONResponse(status_code=402, content={"error": msg})
        else:
            # It's an invite_tokens row
            ok = await database.claim_invite_generation(session["token"], amount=credits_needed)
            if not ok:
                msg = (
                    "⚠️ Недостаточно кредитов. Pro режим требует 3 кредита. "
                    "Переключитесь на Standard (1 кредит) или пополните баланс."
                    if (image_model or "").lower().find("pro") >= 0
                    else "Генерации закончились."
                )
                return JSONResponse(status_code=402, content={"error": msg})

    image_bytes = None
    try:
        if mode == "img2img" and image_b64:
            input_bytes = base64.b64decode(image_b64)
            image_bytes = await image_service.image_to_image(
                api_key, input_bytes, prompt, ratio, quality,
                search=False, image_model=image_model
            )
        elif mode == "multi" and len(images_b64) >= 2:
            input_list = [base64.b64decode(b) for b in images_b64[:10]]
            image_bytes = await image_service.multi_image(
                api_key, input_list, prompt, ratio, quality,
                search=False, image_model=image_model
            )
        else:
            # txt2img (default)
            image_bytes = await text_to_image(
                api_key=api_key, prompt=prompt,
                aspect_ratio=ratio, quality=quality,
                search=False, image_model=image_model,
            )
    except Exception:
        logger.exception("web_generate: generation failed (mode=%s)", mode)
        await _refund_generation(session, credits_needed)
        return JSONResponse(status_code=500, content={"error": "Ошибка генерации, попробуйте снова."})

    if not image_bytes:
        await _refund_generation(session, credits_needed)
        return JSONResponse(status_code=500, content={"error": "Изображение не сгенерировано. Попробуйте другой промпт."})

    img_b64_out   = base64.b64encode(image_bytes).decode()

    # Если есть платформенный пользователь — списываем лимит через users и возвращаем его остаток
    if platform_user and platform_tid is not None:
        await database.decrease_user_balance(platform_tid, credits_needed)
        # перечитываем пользователя, чтобы отдать актуальный остаток
        updated = await database.get_user(platform_tid)
        remaining = updated["daily_limit"] if updated else 0
        return JSONResponse(content={"image_b64": img_b64_out, "remaining": remaining})

    # Иначе работаем как раньше с WebSessions / invite_tokens
    if "balance" in session:
        new_remaining = await database.get_web_session_balance(session["token"])
    else:
        new_remaining = await database.get_invite_generations_left(session["token"])
    return JSONResponse(content={"image_b64": img_b64_out, "remaining": new_remaining})


# ── POST /web-buy?package=<pkg> ───────────────────────────────────────────────

@router.post("/web-buy")
async def web_buy(request: Request, package: str = "standard", gateway: str = "yoomoney"):
    """Create a payment link (YooMoney or NOWPayments) and record the pending transaction."""
    pkg = PACKAGES.get(package) or PACKAGES["standard"]
    order_id = "web-" + str(uuid.uuid4())

    # Try to associate with session token (user_id = 0 for web users)
    session = await _get_session(request)
    user_id = 0  # web users don't have telegram IDs
    try:
        await database.create_transaction(
            order_id=order_id,
            user_id=user_id,
            amount=pkg["price"],
            generations=pkg["gens"],
            gateway=f"{gateway}_web",
        )
        # Tag the transaction with the invite token so we can credit it on payment
        if session:
            async with aiosqlite.connect(database.DB_PATH) as db:
                await db.execute(
                    "UPDATE transactions SET user_id = ? WHERE order_id = ?",
                    (session["token"][:36], order_id),  # store token as user_id for web
                )
                await db.commit()
    except Exception:
        logger.exception("web_buy: failed to record transaction")

    payment_url: Optional[str] = None

    # YooMoney (bank card, РФ)
    if gateway == "yoomoney":
        payment_url = await _build_payment_url_from_pkg(pkg, order_id)

    # Crypto via NOWPayments
    elif gateway == "crypto":
        from payment_gateways import NowPaymentsGateway

        api_key = await database.get_setting("NOWPAYMENTS_API_KEY") or NOWPAYMENTS_API_KEY
        ipn_secret = await database.get_setting("NOWPAYMENTS_IPN_SECRET") or NOWPAYMENTS_IPN_SECRET

        if not api_key:
            logger.error("web_buy: NOWPayments API key is missing")
        else:
            base_url = await database.get_setting("ADMIN_URL") or ADMIN_URL or "https://neuronanobanana.duckdns.org"
            success_url = f"{base_url}/?paid=1"
            callback_url = f"{base_url.rstrip('/')}/api/webhooks/nowpayments"

            gw = NowPaymentsGateway(api_key=api_key, ipn_secret=ipn_secret or "")
            payment_url = gw.create_invoice(
                order_id=order_id,
                amount=pkg["price"],
                currency="rub",
                description=pkg["label"],
                success_url=success_url,
                cancel_url=base_url,
                callback_url=callback_url,
            )

    if not payment_url:
        return JSONResponse(
            status_code=500,
            content={"error": "Не удалось создать платёж. Попробуйте ещё раз или выберите другой способ оплаты."},
        )

    return JSONResponse(content={"payment_url": payment_url, "order_id": order_id, "gateway": gateway})


# ── GET /web-profile ──────────────────────────────────────────────────────────

def _get_account_id_from_session(session: dict) -> Optional[int]:
    """Return WebAccount id if this session is account-based (WebSession with user_id)."""
    if session.get("user_id") and "balance" in session:
        try:
            return int(session["user_id"])
        except (TypeError, ValueError):
            pass
    return None


@router.get("/web-profile")
async def web_profile(request: Request):
    """Return profile data for the current web session."""
    session = await _get_session(request)
    if not session:
        return JSONResponse(status_code=401, content={"error": "No session"})

    token = session["token"]
    account_id = _get_account_id_from_session(session)

    # Try to resolve platform user (shared with Telegram) via WebAccount
    platform_user = None
    platform_tid = None
    if account_id:
        try:
            platform_user = await database.get_user_by_web_account(account_id)
        except Exception:
            platform_user = None

    remaining = session.get("generations_left", 0)
    if platform_user:
        platform_tid = platform_user["telegram_id"]
        remaining = platform_user["daily_limit"]

    email = ""
    display_name = ""
    has_password = False
    need_password = False

    if account_id:
        acc = await database.get_web_account_by_id(account_id)
        if acc:
            email = (acc["email"] or "").strip()
            display_name = (acc["display_name"] or "").strip()
            has_password = bool(acc.get("password_hash"))
            need_password = not has_password
    else:
        web_user = await database.get_web_user(token)
        if web_user:
            wu = dict(web_user)
            email = wu.get("email") or ""
            display_name = wu.get("display_name") or ""
        inv = await database.get_invite_token(token)
        inv_d = dict(inv) if inv else {}
        if inv_d.get("account_id"):
            acc = await database.get_web_account_by_id(inv_d["account_id"])
            if acc:
                email = email or (acc["email"] or "")
                display_name = display_name or (acc["display_name"] or "")
                has_password = bool(acc.get("password_hash"))
                need_password = not has_password

    # How many gens were bought (total_used = 3 - remaining + bought)
    # We track bought_gens by looking at paid transactions
    bought_gens = 0
    tx_history = []
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            # Web transactions store token[:36] as user_id
            async with db.execute(
                "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
                (token[:36],)
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                r = dict(row)
                if r.get("status") == "paid":
                    bought_gens += r.get("generations", 0)
                # Format date
                try:
                    dt = datetime.fromisoformat(r["created_at"])
                    r["created_at_fmt"] = dt.strftime("%d.%m.%Y %H:%M")
                except Exception:
                    r["created_at_fmt"] = r.get("created_at", "")
                r["label"] = f"{r.get('generations',0)} генераций ({r.get('amount',0):.0f} ₽)"
                tx_history.append(r)
    except Exception:
        logger.exception("web_profile: failed to load transactions")

    # Web generations history (shared with Telegram user)
    web_generations = []
    if platform_user and platform_tid is not None:
        try:
            gens = await database.get_user_generations(platform_tid, limit=20)
            for g in gens:
                q = g["quality"] or ""
                # Вес в кредитах: 4K = 2, иначе 1 (как в админке)
                credits = 2 if q == "4K" else 1
                # Пока модель в генерациях не логируется отдельно; используем дефолтный лейбл
                model_label = "Nanao Banana"  # Standard / Pro выбирается при генерации
                web_generations.append(
                    {
                        "created_at": g["created_at"],
                        "mode": g["mode"],
                        "quality": q,
                        "aspect_ratio": g["aspect_ratio"],
                        "prompt": g["prompt"],
                        "success": bool(g["success"]),
                        "credits": credits,
                        "api_cost": float(g["api_cost"] or 0.0),
                        "model": model_label,
                    }
                )
        except Exception:
            logger.exception("web_profile: failed to load generations history")

    # Stats
    total_used = 0
    if platform_user:
        # Используем общую статистику из generations для этого пользователя (как в админке)
        try:
            total_used = await database.get_user_total_count(platform_tid)
        except Exception:
            total_used = 0
    else:
        # Старый режим: считаем относительно стартовых 3 и купленных генераций
        total_used = max(0, (3 + bought_gens) - remaining)

    expires_at_fmt = ""
    expired = False
    if session.get("expires_at"):
        try:
            exp = datetime.fromisoformat(session["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            expired = datetime.now(timezone.utc) > exp
            expires_at_fmt = exp.strftime("%d.%m.%Y в %H:%M UTC")
        except Exception:
            pass

    register_url = f"/web-register?token={token}" if need_password else None

    # Строка остатка как в Telegram-профиле
    if remaining == -1:
        remaining_str = "♾ Безлимитно"
    else:
        remaining_str = str(remaining)

    return JSONResponse(content={
        "remaining": remaining,
        "remaining_str": remaining_str,
        "total_used": total_used,
        "bought_gens": bought_gens,
        "expired": expired,
        "expires_at_fmt": expires_at_fmt,
        "transactions": tx_history,
        "web_generations": web_generations,
        "email": email,
        "display_name": display_name,
        "has_password": has_password,
        "need_password": need_password,
        "register_url": register_url,
        "account_id": account_id,
    })


# ── Web logout ─────────────────────────────────────────────────────────────────

@router.get("/web-logout")
async def web_logout(request: Request):
    """
    Clear web_session cookie and return to landing page.
    """
    redir = RedirectResponse(url="/", status_code=302)
    redir.delete_cookie(
        key=_SESSION_COOKIE,
        path="/",
    )
    return redir


@router.post("/web-profile/name")
async def web_profile_set_name(request: Request):
    """Update display_name (WebAccounts or WebUsers)."""
    session = await _get_session(request)
    if not session:
        return JSONResponse(status_code=401, content={"error": "No session"})

    try:
        data = await request.json()
        name = (data.get("name") or "").strip()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Неверный формат запроса"})

    if not name:
        return JSONResponse(status_code=400, content={"error": "Имя не может быть пустым"})

    account_id = _get_account_id_from_session(session)
    try:
        if account_id:
            await database.set_web_account_display_name(account_id, name)
        else:
            await database.set_web_user_display_name(session["token"], name)
    except Exception as e:
        logger.exception("Failed to set display name: %s", e)
        return JSONResponse(status_code=500, content={"error": "Не удалось сохранить имя"})

    return JSONResponse(content={"ok": True})


@router.post("/web-profile/password")
async def web_profile_set_password(request: Request):
    """Change password for WebAccount (old_password + new_password)."""
    session = await _get_session(request)
    if not session:
        return JSONResponse(status_code=401, content={"error": "No session"})

    account_id = _get_account_id_from_session(session)
    if not account_id:
        inv = await database.get_invite_token(session["token"])
        inv_d = dict(inv) if inv else {}
        if inv_d.get("account_id"):
            account_id = inv_d["account_id"]
    if not account_id:
        return JSONResponse(status_code=400, content={"error": "Смена пароля доступна после входа по ссылке или по email."})

    try:
        data = await request.json()
        old_password = (data.get("old_password") or "").strip()
        new_password = (data.get("new_password") or "").strip()
        new_password2 = (data.get("new_password2") or "").strip()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Неверный формат запроса"})

    if new_password != new_password2:
        return JSONResponse(status_code=400, content={"error": "Новый пароль и повтор не совпадают"})
    if len(new_password) < 6:
        return JSONResponse(status_code=400, content={"error": "Пароль должен быть не короче 6 символов"})

    acc = await database.get_web_account_by_id(account_id)
    if not acc or not acc.get("password_hash"):
        return JSONResponse(status_code=400, content={"error": "Задайте пароль по ссылке из письма (/web-register?token=...)"})
    try:
        if not bcrypt.checkpw(old_password.encode("utf-8"), acc["password_hash"]):
            return JSONResponse(status_code=400, content={"error": "Неверный текущий пароль"})
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Неверный текущий пароль"})

    pw_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
    await database.set_web_account_password(account_id, pw_hash)
    return JSONResponse(content={"ok": True})


# ── Admin: create invite tokens (manual email flow from dashboard) ────────────

@router.post("/admin/invite/create")
async def create_invite(
    request: Request,
    hours: int = Form(48),
    email: str = Form(...),
):
    """
    Admin-only: generate a new one-time invite link for a specific email.
    Works both with query params and with form-data (from /admin dashboard JS).
    """
    # Direct cookie check to avoid circular import with admin.py
    admin_session = request.cookies.get("admin_session")
    if not admin_session:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    db_password = await database.get_setting("ADMIN_PASSWORD")
    from config import ADMIN_PASSWORD
    actual_password = db_password or ADMIN_PASSWORD
    if admin_session != actual_password:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    email = (email or "").strip()
    if "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Некорректный email"})

    token = secrets.token_urlsafe(24)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

    await database.create_invite_token(token, expires_at, email=email)

    try:
        await database.upsert_web_user(token, email)
    except Exception as e:
        logger.exception("Failed to upsert WebUser for token %s: %s", token, e)

    base_url = await database.get_setting("ADMIN_URL") or ADMIN_URL or "https://neuronanobanana.duckdns.org"
    invite_url = f"{base_url.rstrip('/')}/try?token={token}"

    sent_ok = mailer.send_access_link(email, invite_url)

    await database.log_audit(
        "Admin Panel",
        "Create Web Invite",
        f"Email={email}, hours={hours}, sent_ok={sent_ok}",
    )

    return JSONResponse(
        content={
            "token": token,
            "invite_url": invite_url,
            "expires_at": expires_at,
            "email": email,
            "sent": bool(sent_ok),
        }
    )


@router.get("/admin/invite/list")
async def list_invites(request: Request):
    """Admin-only: list all invite tokens."""
    admin_session = request.cookies.get("admin_session")
    if not admin_session:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    db_password = await database.get_setting("ADMIN_PASSWORD")
    from config import ADMIN_PASSWORD
    actual_password = db_password or ADMIN_PASSWORD
    if admin_session != actual_password:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    rows = await database.get_all_invite_tokens(100)
    tokens = [dict(r) for r in rows]
    return JSONResponse(content={"tokens": tokens})


# ── Helpers (private) ─────────────────────────────────────────────────────────

async def _build_payment_url(package_key: str, order_id: str) -> str:
    pkg = PACKAGES.get(package_key) or PACKAGES["standard"]
    return await _build_payment_url_from_pkg(pkg, order_id)


async def _build_payment_url_from_pkg(pkg: dict, order_id: str) -> str:
    from payment_gateways import YooMoneyGateway
    wallet = await database.get_setting("YOOMONEY_WALLET") or YOOMONEY_WALLET
    secret = await database.get_setting("YOOMONEY_SECRET") or YOOMONEY_SECRET
    base_url = await database.get_setting("ADMIN_URL") or ADMIN_URL or "https://neuronanobanana.duckdns.org"
    success_url = f"{base_url}/?paid=1"
    gw = YooMoneyGateway(wallet or "", secret or "", success_url)
    url = gw.generate_payment_url(
        order_id=order_id,
        amount=pkg["price"],
        description=pkg["label"],
    )
    return url


async def _refund_generation(session: dict, amount: int = 1):
    """Refund credits on generation error (invite_tokens or WebSessions)."""
    if "balance" in session:
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE WebSessions SET balance = balance + ? WHERE token = ?",
                (amount, session["token"]),
            )
            await db.commit()
    else:
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE invite_tokens SET generations_left = generations_left + ? WHERE token = ?",
                (amount, session["token"]),
            )
            await db.commit()


def _error_page(message: str) -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>🍌 Ошибка — NeuroNanoBanana</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🍌</text></svg>"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet"/>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:#0a0a0f;color:#e8e8f0;
  display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}}
.card{{background:#13131a;border:1px solid rgba(255,255,255,.08);border-radius:16px;
  padding:40px 32px;text-align:center;max-width:480px;width:100%}}
.icon{{font-size:3rem;margin-bottom:16px}}
h2{{font-size:1.4rem;font-weight:700;color:#ff5252;margin-bottom:12px}}
p{{color:#7a7a9a;line-height:1.6;margin-bottom:24px}}
a{{display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#7c4dff,#00e5ff);
  border-radius:10px;color:#fff;font-weight:700;text-decoration:none}}
</style></head>
<body><div class="card">
<div class="icon">🔒</div>
<h2>Доступ ограничен</h2>
<p>{message}</p>
    <a href="/">Вернуться на главную</a>
</div></body></html>"""
    return HTMLResponse(content=html, status_code=403)


@router.post("/request-access")
async def request_access(request: Request):
    """Receive email from landing and notify admin."""
    try:
        data = await request.json()
        email = data.get("email", "").strip().lower()
        if not email or "@" not in email:
            return JSONResponse(status_code=400, content={"error": "Некорректный email"})

        # Prevent re-use of the same email
        if await database.is_email_used(email):
            return JSONResponse(
                status_code=400,
                content={"error": "Этот email уже использовался. Проверьте почту — ссылка уже была отправлена."},
            )

        await database.mark_email_used(email)

        # Notify admin
        if hasattr(request.app.state, 'bot_app'):
            from config import ADMIN_ID
            import base64
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            # Base64 encode email for callback data (safely)
            b64_email = base64.urlsafe_b64encode(email.encode()).decode().replace("=", "")
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Одобрить (3)", callback_data=f"em_app_{b64_email}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"em_den_{b64_email}")
                ]
            ])

            await request.app.state.bot_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📩 <b>Новый запрос доступа по почте!</b>\nEmail: <code>{email}</code>\n\nОдобрить доступ на 3 генерации?",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return JSONResponse(content={"status": "ok"})
        else:
            return JSONResponse(status_code=500, content={"error": "Bot is not running"})
    except Exception as e:
        # Generic error for request-access flow, do not crash app
        logger.exception("request_access failed: %s", e)
        return JSONResponse(status_code=500, content={"error": "Internal error"})


def _landing_html() -> str:
    return """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>NeuroNanoBanana — AI Generator</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🍌</text></svg>"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet"/>
<style>
  :root {
    --bg: #050712;
    --card: #0f1019;
    --accent: #8b5cf6;
    --accent-soft: rgba(139,92,246,0.08);
    --accent-strong: rgba(139,92,246,0.4);
    --border: rgba(148,163,184,0.35);
    --muted: #9ca3af;
    --muted-soft: #6b7280;
  }
  * { box-sizing: border-box; margin:0; padding:0; }
  body { font-family: 'Inter', sans-serif; background: radial-gradient(circle at top,#111827 0,var(--bg) 55%); color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 18px; }
  .shell { position: relative; max-width: 480px; width: 100%; }
  .glow { position:absolute; inset:-40px; background: radial-gradient(circle at top,#4c1d95 0,transparent 55%); opacity:0.45; filter: blur(32px); z-index:0; }
  .card { position:relative; z-index:1; padding: 32px 26px 26px; background: linear-gradient(145deg,rgba(15,23,42,0.96),rgba(15,23,42,0.98)); border-radius: 22px; border: 1px solid rgba(148,163,184,0.3); box-shadow: 0 22px 60px rgba(0,0,0,0.75); overflow:hidden; }
  .badge { display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:999px; background:rgba(15,23,42,0.9); border:1px solid rgba(148,163,184,0.4); font-size:0.72rem; color:var(--muted-soft); margin-bottom:14px; }
  .badge span.emoji { font-size:0.95rem; }
  h1 { margin-bottom:8px; font-weight:800; font-size:1.6rem; letter-spacing:-0.03em; background: linear-gradient(135deg,#e5e7eb,#a855f7); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
  .sub { color:var(--muted); margin-bottom:20px; line-height:1.55; font-size:0.94rem; }
  .pill-row { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px; font-size:0.76rem; }
  .pill { border-radius:999px; padding:5px 11px; border:1px solid rgba(148,163,184,0.45); color:var(--muted-soft); background:rgba(15,23,42,0.9); }
  .pill strong { color:#e5e7eb; }
  .btn-primary { display:flex; align-items:center; justify-content:center; gap:8px; width:100%; padding:13px 20px; margin-top:4px; margin-bottom:14px; border-radius:999px; border:none; background:linear-gradient(135deg,#a855f7,#6366f1); box-shadow:0 16px 40px rgba(79,70,229,0.55); color:#fff; font-weight:700; font-size:0.98rem; text-decoration:none; cursor:pointer; }
  .btn-primary span.emoji { font-size:1.1rem; }
  .btn-primary small { font-size:0.72rem; font-weight:500; opacity:0.9; }
  .links-grid { margin-top:4px; display:flex; flex-direction:column; gap:6px; font-size:0.8rem; }
  .link-row { display:flex; align-items:center; justify-content:space-between; padding:6px 10px; border-radius:10px; background:rgba(15,23,42,0.9); border:1px solid rgba(31,41,55,0.9); color:var(--muted-soft); text-decoration:none; }
  .link-row span.label { display:flex; align-items:center; gap:6px; }
  .link-row span.right { font-size:0.7rem; color:var(--muted-soft); }
  .link-row strong { color:#e5e7eb; font-weight:600; }
  .hint { font-size:0.75rem; color:var(--muted-soft); margin-top:14px; text-align:left; }
</style></head>
<body>
  <div class="shell">
    <div class="glow"></div>
    <div class="card">
      <div class="badge"><span class="emoji">🍌</span><span>Генератор иллюстраций для людей, а не для нейросетчиков</span></div>
      <h1>NeuroNanoBanana</h1>
      <p class="sub">Самый простой способ получить крутые визуалы: опиши идею словами, мы аккуратно доработаем промпт и отдадим готовую картинку.</p>
      <div class="pill-row">
        <div class="pill">🍌 <strong>Standard</strong> — дешевле, быстрее</div>
        <div class="pill">💎 <strong>Pro</strong> — 1К/2K 3 кредита, 4K 6 кредитов</div>
      </div>
      <a href="/web-login" class="btn-primary">
        <span class="emoji">✉️</span>
        <span>Войти в веб‑интерфейс</span>
        <small>прямой доступ по email и паролю</small>
      </a>
      <div class="links-grid">
        <a href="https://t.me/NanaoBananaBot" class="link-row">
          <span class="label">🍌 <strong>Перейти в Telegram‑бот</strong></span>
          <span class="right">диалоги и уведомления</span>
        </a>
        <a href="/web-admin-login" class="link-row">
          <span class="label">🔐 <strong>Войти как администратор (Web)</strong></span>
          <span class="right">только для владельца</span>
        </a>
        <a href="https://t.me/NeoAiAdm" class="link-row">
          <span class="label">📩 <strong>Запросить доступ</strong></span>
          <span class="right">@NeoAiAdm</span>
        </a>
      </div>
    <div class="hint">Доступ к веб‑версии выдаётся вручную, чтобы защитить сервис от спама и ботов.</div>
    </div>
  </div>
  <div style="position:fixed; left:16px; right:16px; bottom:16px; z-index:50; max-width:520px; margin:0 auto; display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 14px; border-radius:12px; background:rgba(15,23,42,0.96); border:1px solid rgba(148,163,184,0.5); font-size:0.8rem; color:#e5e7eb;">
    <span>Мы используем файлы cookie для корректной работы сервиса. Подробнее в <a href="/cookies" style="color:#38bdf8; text-decoration:none;">политике cookie</a>.</span>
  </div>
</body></html>"""

