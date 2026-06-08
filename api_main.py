"""
api/main.py — FastAPI entry point.
Arranca limpio. Los módulos se agregan sprint por sprint.
"""
from __future__ import annotations
import logging
import os
import sys

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# Asegurar path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import init_db, verify_login_token
from engine.body.healthconnect import exchange_code, get_auth_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Coach AI", docs_url=None, redoc_url=None)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ADMIN_ID       = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("✅ Coach AI started — DB initialized")


@app.get("/health")
def health():
    return {"status": "ok", "service": "coach-ai"}


@app.get("/auth/google/callback")
async def google_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return HTMLResponse("""
            <html><body style="font-family:sans-serif;text-align:center;padding:40px;background:#000;color:#fff">
            <h2>❌ Autorización cancelada</h2><p>Vuelve al bot e intenta de nuevo.</p>
            </body></html>
        """)

    if not code or not state:
        return HTMLResponse("<html><body>Error: parámetros faltantes</body></html>", status_code=400)

    try:
        uid = int(state)
    except ValueError:
        return HTMLResponse("<html><body>Error: estado inválido</body></html>", status_code=400)

    success = await exchange_code(code, uid)

    if success:
        return HTMLResponse("""
            <html><body style="font-family:sans-serif;text-align:center;padding:40px;background:#000;color:#fff">
            <h2>✅ Google Fit conectado</h2>
            <p>Puedes cerrar esta ventana y volver al bot.</p>
            </body></html>
        """)
    else:
        return HTMLResponse("""
            <html><body style="font-family:sans-serif;text-align:center;padding:40px">
            <h2>❌ Error conectando Google Fit</h2>
            <p>Intenta de nuevo con /conectar_fit en el bot.</p>
            </body></html>
        """, status_code=500)


@app.get("/auth/login")
async def verify_web_login(token: str):
    uid = verify_login_token(token)
    if not uid:
        return JSONResponse({"error": "token inválido o expirado"}, status_code=401)
    return JSONResponse({"user_id": uid, "valid": True})
