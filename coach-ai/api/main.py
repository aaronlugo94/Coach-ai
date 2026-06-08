from __future__ import annotations
import asyncio, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from telegram.ext import Application

from db.database import init_db, verify_login_token, fetchall
from engine.body.healthconnect import exchange_code, esta_conectado, sync_usuario

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN","")
app  = FastAPI(title="Coach AI", docs_url=None, redoc_url=None)
_bot: Application | None = None

@app.on_event("startup")
async def startup():
    init_db()
    await _start_bot()
    _start_scheduler()
    logger.info("✅ Coach AI ready")

async def _start_bot():
    global _bot
    from bot.handlers import register_handlers
    _bot = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(_bot)
    await _bot.initialize()
    await _bot.start()
    asyncio.create_task(_bot.updater.start_polling(drop_pending_updates=True))
    logger.info("Bot polling activo")

def _start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from notifications.morning import enviar_recordatorios
    from notifications.night   import enviar_resumenes
    sch = AsyncIOScheduler(timezone="America/Phoenix")
    sch.add_job(enviar_recordatorios, "cron", minute="*", id="morning",
                kwargs={"bot": _bot.bot if _bot else None})
    sch.add_job(enviar_resumenes, "cron", hour=21, minute=0, id="night",
                kwargs={"bot": _bot.bot if _bot else None})
    sch.add_job(_sync_gfit_all, "cron", hour=6, minute=0, id="gfit")
    sch.start()

async def _sync_gfit_all():
    users = fetchall("SELECT user_id FROM usuarios WHERE google_fit_token IS NOT NULL", ())
    for u in users:
        uid = u["user_id"]
        if esta_conectado(uid):
            try: await sync_usuario(uid)
            except Exception as e: logger.error("GFit sync uid=%s: %s", uid, e)

@app.get("/health")
def health(): return {"status":"ok","service":"coach-ai"}

@app.get("/auth/google/callback")
async def google_callback(code: str=None, state: str=None, error: str=None):
    if error:
        return HTMLResponse("<html><body style='font-family:sans-serif;text-align:center;padding:40px;background:#000;color:#fff'><h2>❌ Autorización cancelada</h2><p>Vuelve al bot.</p></body></html>")
    if not code or not state:
        return HTMLResponse("<html><body>Error: parámetros faltantes</body></html>", status_code=400)
    try: uid = int(state)
    except ValueError:
        return HTMLResponse("<html><body>Error</body></html>", status_code=400)
    ok = await exchange_code(code, uid)
    if ok and _bot:
        try:
            await _bot.bot.send_message(chat_id=uid,
                text="✅ <b>Google Fit conectado</b>\n\nPasos, calorías y sueño del OnePlus Watch llegan automáticamente cada mañana 🧠",
                parse_mode="HTML")
        except Exception: pass
    if ok:
        return HTMLResponse("<html><body style='font-family:sans-serif;text-align:center;padding:40px;background:#000;color:#fff'><h2>✅ Conectado</h2><p>Puedes cerrar esta ventana.</p></body></html>")
    return HTMLResponse("<html><body><h2>❌ Error</h2><p>Intenta de nuevo con /conectar_fit</p></body></html>", status_code=500)

@app.get("/auth/login")
async def verify_login(token: str):
    uid = verify_login_token(token)
    if not uid: return JSONResponse({"error":"token inválido o expirado"}, status_code=401)
    return JSONResponse({"user_id": uid, "valid": True})

@app.on_event("shutdown")
async def shutdown():
    if _bot:
        await _bot.updater.stop()
        await _bot.stop()
        await _bot.shutdown()
