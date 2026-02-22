"""
Admin Panel: FastAPI app with Jinja2 templates.
"""

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import APIKeyCookie
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

def get_current_user(admin_session: str = Depends(cookie_sec)):
    if admin_session != ADMIN_PASSWORD:
        return None
    return "admin"

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_post(response: Response, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key=COOKIE_NAME, value=ADMIN_PASSWORD)
        return response
    return RedirectResponse(url="/login?error=1", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie(COOKIE_NAME)
    return response

@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    stats = await database.get_stats()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "stats": stats,
        "page": "dashboard"
    })

@app.get("/admin/users", response_class=HTMLResponse)
async def users_list(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    users = await database.get_all_users()
    return templates.TemplateResponse("users.html", {
        "request": request, 
        "users": users,
        "page": "users"
    })

@app.post("/admin/users/{tid}/limit")
async def update_limit(tid: int, limit: int = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.set_user_limit(tid, limit)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{tid}/block")
async def block_user(tid: int, blocked: bool = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.set_user_block(tid, blocked)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/pricing", response_class=HTMLResponse)
async def pricing_list(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    pricing = await database.get_pricing()
    return templates.TemplateResponse("pricing.html", {
        "request": request, 
        "pricing": pricing,
        "page": "pricing"
    })

@app.post("/admin/pricing/{pid}")
async def update_pricing_route(pid: int, api_cost: float = Form(...), sale_price: float = Form(...), user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    await database.update_pricing(pid, api_cost, sale_price)
    return RedirectResponse(url="/admin/pricing", status_code=status.HTTP_303_SEE_OTHER)
