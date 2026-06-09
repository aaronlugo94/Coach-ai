from __future__ import annotations
import asyncio, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from telegram.ext import Application

from db.database import init_db, verify_login_token, fetchall
from engine.body.healthconnect import exchange_code, esta_conectado, sync_usuario
from api.routes import router

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN","")
FRONTEND_URL   = os.environ.get("FRONTEND_URL","https://coach-ai.vercel.app")

app  = FastAPI(title="Coach AI", docs_url=None, redoc_url=None)
_bot: Application | None = None

# CORS — permite la web app de Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción: [FRONTEND_URL]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir todas las rutas
app.include_router(router)


@app.on_event("startup")
async def startup():
    init_db()
    await _start_bot()
    _start_scheduler()
    logger.info("✅ Coach AI ready — FRONTEND: %s", FRONTEND_URL)


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
    sch = AsyncIOScheduler(timezone="America/Phoenix")
    sch.add_job(_send_recordatorios, "cron", minute="*", id="morning")
    sch.add_job(_send_resumenes,    "cron", hour=21, minute=0, id="night")
    sch.add_job(_sync_gfit_all, "cron", hour=6, minute=0, id="gfit")
    sch.start()


async def _send_recordatorios():
    if _bot:
        from notifications.morning import enviar_recordatorios
        await enviar_recordatorios(bot=_bot.bot)

async def _send_resumenes():
    if _bot:
        from notifications.night import enviar_resumenes
        await enviar_resumenes(bot=_bot.bot)

async def _sync_gfit_all():
    users = fetchall("SELECT user_id FROM usuarios WHERE google_fit_token IS NOT NULL", ())
    for u in users:
        uid = u["user_id"]
        if esta_conectado(uid):
            try: await sync_usuario(uid)
            except Exception as e: logger.error("GFit sync uid=%s: %s", uid, e)


@app.get("/health")
def health(): return {"status":"ok","service":"coach-ai"}


@app.get("/auth/login")
async def verify_web_login(token: str):
    """La web llama esto para verificar el magic link."""
    from db.database import fetchone, execute
    from datetime import datetime, timedelta
    r = fetchone("SELECT user_id, usado, created_at FROM login_tokens WHERE token=?", (token,))
    if not r:
        return JSONResponse({"error":"Token no encontrado"}, status_code=401)
    if r["usado"]:
        return JSONResponse({"error":"Token ya usado"}, status_code=401)
    created = datetime.fromisoformat(r["created_at"])
    if datetime.utcnow() - created > timedelta(minutes=10):  # 10 min para la web
        return JSONResponse({"error":"Token expirado"}, status_code=401)
    execute("UPDATE login_tokens SET usado=1 WHERE token=?", (token,))
    return JSONResponse({"user_id": r["user_id"], "valid": True})


@app.get("/auth/google/callback")
async def google_callback(code: str=None, state: str=None, error: str=None):
    if error:
        return HTMLResponse("<html><body style='font-family:sans-serif;text-align:center;padding:40px;background:#000;color:#fff'><h2>❌ Autorización cancelada</h2></body></html>")
    if not code or not state:
        return HTMLResponse("<html><body>Error</body></html>", status_code=400)
    try: uid = int(state)
    except ValueError:
        return HTMLResponse("<html><body>Error</body></html>", status_code=400)
    ok = await exchange_code(code, uid)
    if ok and _bot:
        try:
            await _bot.bot.send_message(chat_id=uid,
                text="✅ <b>Google Fit conectado</b>\n\nPasos, calorías y sueño del OnePlus Watch llegan automáticamente 🧠",
                parse_mode="HTML")
        except Exception: pass
    if ok:
        return HTMLResponse("<html><body style='font-family:sans-serif;text-align:center;padding:40px;background:#000;color:#fff'><h2>✅ Conectado</h2><p>Puedes cerrar esta ventana.</p></body></html>")
    return HTMLResponse("<html><body><h2>❌ Error</h2></body></html>", status_code=500)


@app.on_event("shutdown")
async def shutdown():
    if _bot:
        await _bot.updater.stop()
        await _bot.stop()
        await _bot.shutdown()
