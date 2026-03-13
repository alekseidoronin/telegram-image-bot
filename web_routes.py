"""
Web Routes — публичный веб-интерфейс для генерации изображений.

Эндпоинты:
  GET  /                  → редирект на /try?token=... или промпт-страница
  GET  /try?token=<tok>   → валидация токена, выдача сессии
  POST /web-generate      → генерация изображения (требует cookie-сессии)
  POST /web-buy?package=  → создание платёжной ссылки YooMoney
"""

import base64
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import database
import image_service
from image_service import text_to_image
from config import YOOMONEY_WALLET, YOOMONEY_SECRET, ADMIN_URL


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
    payment_url = await _build_payment_url("standard", f"web_{token[:8]}")

    response = templates.TemplateResponse("web_app.html", {
        "request": request,
        "remaining": remaining,
        "payment_url": payment_url,
        "error": None,
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

    # Claim slot
    if "balance" in session:
        # It's a WebSessions row
        async with aiosqlite.connect(database.DB_PATH) as db:
            cursor = await db.execute("UPDATE WebSessions SET balance = balance - 1 WHERE token = ? AND balance > 0", (session["token"],))
            await db.commit()
            if cursor.rowcount == 0:
                 return JSONResponse(status_code=402, content={"error": "Генерации закончились."})
    else:
        # It's an invite_tokens row
        ok = await database.claim_invite_generation(session["token"])
        if not ok:
            return JSONResponse(status_code=402, content={"error": "Генерации закончились."})

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
        await _refund_generation(session["token"])
        return JSONResponse(status_code=500, content={"error": "Ошибка генерации, попробуйте снова."})

    if not image_bytes:
        await _refund_generation(session["token"])
        return JSONResponse(status_code=500, content={"error": "Изображение не сгенерировано. Попробуйте другой промпт."})

    img_b64_out   = base64.b64encode(image_bytes).decode()
    new_remaining = await database.get_invite_generations_left(session["token"])
    return JSONResponse(content={"image_b64": img_b64_out, "remaining": new_remaining})


# ── POST /web-buy?package=<pkg> ───────────────────────────────────────────────

@router.post("/web-buy")
async def web_buy(request: Request, package: str = "standard"):
    """Create a YooMoney payment link and record the pending transaction."""
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
            gateway="yoomoney_web",
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

    payment_url = await _build_payment_url_from_pkg(pkg, order_id)
    return JSONResponse(content={"payment_url": payment_url, "order_id": order_id})


# ── GET /web-profile ──────────────────────────────────────────────────────────

@router.get("/web-profile")
async def web_profile(request: Request):
    """Return profile data for the current web session."""
    session = await _get_session(request)
    if not session:
        return JSONResponse(status_code=401, content={"error": "No session"})

    token = session["token"]
    remaining = session.get("generations_left", 0)

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

    # Stats
    total_used = max(0, (3 + bought_gens) - remaining)

    # Expiry format
    expires_at_fmt = ""
    expired = False
    try:
        exp = datetime.fromisoformat(session["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        expired = datetime.now(timezone.utc) > exp
        expires_at_fmt = exp.strftime("%d.%m.%Y в %H:%M UTC")
    except Exception:
        pass

    return JSONResponse(content={
        "remaining": remaining,
        "total_used": total_used,
        "bought_gens": bought_gens,
        "expired": expired,
        "expires_at_fmt": expires_at_fmt,
        "transactions": tx_history,
    })



# ── Admin: create invite tokens ───────────────────────────────────────────────

@router.post("/admin/invite/create")
async def create_invite(request: Request, hours: int = 48, email: str = None):
    """
    Admin-only: generate a new one-time invite link for a specific email.
    Requires admin session cookie.
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

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Email is required to generate a link."})

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    await database.create_invite_token(token, expires_at, email=email)

    base_url = await database.get_setting("ADMIN_URL") or ADMIN_URL or "https://neuronanobanana.duckdns.org"
    invite_url = f"{base_url}/try?token={token}"

    return JSONResponse(content={
        "token": token,
        "invite_url": invite_url,
        "expires_at": expires_at,
    })


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


async def _refund_generation(token: str):
    """Increment generations_left back by 1 on error."""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "UPDATE invite_tokens SET generations_left = generations_left + 1 WHERE token = ?",
            (token,),
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
def _landing_html() -> str:
    return """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>NeuroNanoBanana — AI Generator</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
  body { font-family: 'Inter', sans-serif; background: #08080e; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; text-align: center; }
  .card { max-width: 400px; padding: 40px; background: #13131a; border-radius: 20px; border: 1px solid rgba(255,255,255,0.05); }
  h1 { margin-bottom: 20px; font-weight: 900; background: linear-gradient(135deg,#7c4dff,#00e5ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  p { color: #8a8aa8; margin-bottom: 30px; line-height: 1.6; }
  .btn { display: inline-block; padding: 12px 24px; background: #7c4dff; color: #fff; text-decoration: none; border-radius: 10px; font-weight: 700; }
</style></head>
<body>
  <div class="card">
    <h1>NeuroNanoBanana</h1>
    <p>Веб-версия генератора доступна только по персональным ссылкам.</p>
    <a href="https://t.me/NanaoBananaBot" class="btn">Перейти в Telegram-бот</a>
  </div>
</body></html>"""

