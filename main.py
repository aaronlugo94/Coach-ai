"""
api/main.py — FastAPI + Telegram bot + APScheduler

Endpoints:
  GET  /health
  GET  /auth/google/callback   ← recibe código OAuth2 de Google
  GET  /login                  ← verifica token de login web
  POST /webhook                ← webhook de Telegram (opcional)
"""
from __future__ import annotations
import asyncio
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from telegram.ext import Application

from db.database import init_db, verify_login_token
from engine.body.healthconnect import exchange_code

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ADMIN_ID       = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))

app = FastAPI(title="Coach AI", docs_url=None)


# ── Startup ────────────────────────────────────────────────────────────────────

bot_app: Application | None = None

@app.on_event("startup")
async def startup():
    init_db()
    await _start_bot()
    _start_scheduler()
    logger.info("Coach AI ready")


async def _start_bot():
    global bot_app
    from bot.handlers import register_handlers

    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(bot_app)
    await bot_app.initialize()
    await bot_app.start()
    asyncio.create_task(bot_app.updater.start_polling(drop_pending_updates=True))
    logger.info("Bot polling activo")


def _start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from notifications.morning import enviar_recordatorios
    from notifications.night   import enviar_resumenes
    from engine.body.renpho    import sync_all_users as renpho_sync

    tz = "America/Phoenix"
    scheduler = AsyncIOScheduler(timezone=tz)

    # Recordatorio mañana — hora configurada por usuario
    scheduler.add_job(enviar_recordatorios, "cron",
                      minute="*", id="morning",
                      kwargs={"bot": bot_app.bot if bot_app else None})

    # Resumen nocturno — 9pm fijo
    scheduler.add_job(enviar_resumenes, "cron",
                      hour=21, minute=0, id="night",
                      kwargs={"bot": bot_app.bot if bot_app else None})

    # Sync Renpho báscula — cada hora
    scheduler.add_job(renpho_sync, "interval",
                      minutes=60, id="renpho")

    # Sync Google Fit — cada mañana a las 6am
    scheduler.add_job(_sync_google_fit_all, "cron",
                      hour=6, minute=0, id="google_fit")

    scheduler.start()
    logger.info("Scheduler iniciado")


async def _sync_google_fit_all():
    """Sincroniza Google Fit para todos los usuarios conectados."""
    from db.database import fetchall
    from engine.body.healthconnect import sync_usuario, esta_conectado
    users = fetchall(
        "SELECT user_id FROM usuarios WHERE google_fit_token IS NOT NULL", ()
    )
    for u in users:
        uid = u["user_id"]
        if esta_conectado(uid):
            try:
                await sync_usuario(uid)
            except Exception as e:
                logger.error("Error sync Google Fit uid=%s: %s", uid, e)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "coach-ai"}


@app.get("/auth/google/callback")
async def google_callback(code: str = None, state: str = None, error: str = None):
    """
    Google redirige aquí después de que el usuario autoriza.
    state = user_id del usuario de Telegram.
    """
    if error:
        logger.warning("Google OAuth error: %s", error)
        return HTMLResponse("""
            <html><body style="font-family:sans-serif;text-align:center;padding:40px">
            <h2>❌ Autorización cancelada</h2>
            <p>Puedes volver a intentarlo en el bot.</p>
            </body></html>
        """)

    if not code or not state:
        return HTMLResponse("<html><body>Error: parámetros faltantes</body></html>", status_code=400)

    try:
        uid = int(state)
    except ValueError:
        return HTMLResponse("<html><body>Error: estado inválido</body></html>", status_code=400)

    success = await exchange_code(code, uid)

    if success and bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=uid,
                text=(
                    "✅ <b>Google Fit conectado</b>\n\n"
                    "Ahora el bot recibe tus pasos, calorías, sueño y frecuencia "
                    "cardíaca del OnePlus Watch 4 automáticamente.\n\n"
                    "Gemini los usará en el análisis nocturno 🧠"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Error notificando conexión uid=%s: %s", uid, e)

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
    """Verifica token de login para la web app."""
    uid = verify_login_token(token)
    if not uid:
        return JSONResponse({"error": "token inválido o expirado"}, status_code=401)
    return JSONResponse({"user_id": uid, "valid": True})


@app.on_event("shutdown")
async def shutdown():
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
