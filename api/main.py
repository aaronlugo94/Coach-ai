from __future__ import annotations
import asyncio, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from db.database import init_db, verify_login_token, fetchall, get_usuario
from engine.body.healthconnect import exchange_code, esta_conectado, sync_usuario
from api.routes import router

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN","")
FRONTEND_URL   = os.environ.get("FRONTEND_URL","https://coach-ai.vercel.app")

app  = FastAPI(title="Invisible Coach", docs_url=None, redoc_url=None)
_bot: Application | None = None

# CORS — debe estar ANTES del router
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Explicit OPTIONS handler para preflight requests
from fastapi import Request
from fastapi.responses import Response

@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request, rest_of_path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.on_event("startup")
async def startup():
    init_db()
    await _start_bot()
    _start_scheduler()
    logger.info("✅ Invisible Coach ready — %s", FRONTEND_URL)


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

    # Cada minuto: verificar qué usuarios tienen notificación en este momento
    sch.add_job(_tick_notificaciones, "cron", minute="*", id="tick")

    # Cada mañana a las 9am: evaluar notificaciones de enganche
    sch.add_job(_engagement, "cron", hour=9, minute=0, id="engagement")

    # Cada domingo a las 6pm: generar plan de nutrición de la siguiente semana
    sch.add_job(_generar_planes_nutricion, "cron", day_of_week="sun", hour=18, minute=0, id="plan_nutricion")

    # Cada domingo a las 8pm: resumen semanal
    sch.add_job(_resumen_dominical, "cron", day_of_week="sun", hour=20, minute=0, id="resumen")

    # Sync Google Fit: cada usuario a su hora (6am por defecto)
    sch.add_job(_sync_gfit_all, "cron", minute="*/30", id="gfit")

    # Sync Renpho: máximo 1 intento/hora, ventana 6am-10am (rate-limit safe)
    sch.add_job(_sync_renpho_all, "cron", hour="6-10", minute=0, id="renpho")

    sch.start()
    logger.info("Scheduler iniciado — notificaciones adaptativas")


async def _tick_notificaciones():
    """
    Corre cada minuto. Verifica briefing Y check-in para cada usuario.
    Los horarios son individuales por usuario, no globales.
    """
    if not _bot:
        return
    from notifications.morning import enviar_recordatorios
    from notifications.night   import enviar_resumenes, enviar_resumen_dominical
    await enviar_recordatorios(bot=_bot.bot)
    await enviar_resumenes(bot=_bot.bot)


async def _engagement():
    if not _bot:
        return
    from notifications.engagement import evaluar_y_enviar
    await evaluar_y_enviar(bot=_bot.bot)


async def _generar_planes_nutricion():
    """
    Domingo 6pm: genera el plan de nutrición de la próxima semana
    para cada usuario activo, usando Gemini.
    """
    from db.database import (fetchall, get_estado, get_ejercicios_dia,
                             save_plan_nutricion, get_ciclo)
    from engine.nutrition.macros import calcular_macros_dia
    from ai.coach import generar_plan_nutricion

    usuarios = fetchall("""
        SELECT user_id FROM usuarios u
        JOIN usuarios_permitidos p ON u.user_id=p.user_id
        WHERE u.onboarding_done=1
    """, ())

    for u in usuarios:
        uid = u["user_id"]
        try:
            usuario = get_usuario(uid)

            # Determinar días de gym de la próxima semana
            ciclo  = get_ciclo(uid)
            semana, _ = get_estado(uid)
            dias_rutina = fetchall(
                "SELECT DISTINCT dia FROM rutinas WHERE user_id=? AND ciclo=? AND semana=?",
                (uid, ciclo, semana)
            )
            dias_gym = [r["dia"] for r in dias_rutina] or ["lunes","miercoles","viernes","domingo"]

            # Macros base (día de gym, para que Gemini tenga referencia)
            macros = calcular_macros_dia(uid, es_gym=True)

            datos = {
                "usuario":  usuario,
                "macros":   macros,
                "dias_gym": dias_gym,
            }

            plan_json = await generar_plan_nutricion(datos)
            if plan_json:
                save_plan_nutricion(uid, plan_json, macros)
                logger.info("Plan nutrición generado uid=%s", uid)
            else:
                logger.warning("Plan nutrición vacío uid=%s — Gemini no devolvió JSON válido", uid)
        except Exception as e:
            logger.error("Error generando plan nutrición uid=%s: %s", uid, e, exc_info=True)


async def _resumen_dominical():
    if not _bot:
        return
    from notifications.night import enviar_resumen_dominical
    await enviar_resumen_dominical(bot=_bot.bot)


async def _sync_renpho_all():
    """Sync Renpho — máximo 1/hora, ventana 6-10am, se detiene tras éxito diario."""
    from engine.body.renpho import sync_all_renpho
    await sync_all_renpho(bot=_bot.bot if _bot else None)


async def _sync_gfit_all():
    """Sync Google Fit para todos los usuarios conectados."""
    users = fetchall(
        "SELECT user_id FROM usuarios WHERE google_fit_token IS NOT NULL AND onboarding_done=1", ()
    )
    for u in users:
        uid = u["user_id"]
        if esta_conectado(uid):
            try:
                await sync_usuario(uid)
            except Exception as e:
                logger.error("GFit sync uid=%s: %s", uid, e)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "invisible-coach"}


# /auth/login moved to routes.py for CORS support


@app.get("/auth/google/callback")
async def google_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;"
            "padding:40px;background:#000;color:#fff'>"
            "<h2>❌ Autorización cancelada</h2></body></html>")
    if not code or not state:
        return HTMLResponse("<html><body>Error</body></html>", status_code=400)
    try:
        uid = int(state)
    except ValueError:
        return HTMLResponse("<html><body>Error</body></html>", status_code=400)

    ok = await exchange_code(code, uid)
    if ok and _bot:
        try:
            from db.database import get_usuario
            u = get_usuario(uid) or {}
            en_onboarding = not bool(u.get("onboarding_done"))

            if en_onboarding:
                # El usuario está a mitad del setup — darle continuidad
                # directa en vez de un mensaje fijo sin acción.
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                await _bot.bot.send_message(
                    chat_id=uid,
                    text="✅ <b>Google Fit conectado</b>\n\n"
                         "Importando tus datos de los últimos 7 días...",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Continuar con el setup →", callback_data="wear_check:google_fit")
                    ]]))
            else:
                # Conexión vía /conectar_fit fuera del onboarding
                await _bot.bot.send_message(
                    chat_id=uid,
                    text="✅ <b>Google Fit conectado</b>\n\n"
                         "Pasos, sueño, HRV y FC reposo del OnePlus Watch "
                         "llegan automáticamente cada mañana 🧠\n\n"
                         "El modelo Bannister empieza a calibrarse con tus datos.",
                    parse_mode="HTML")
        except Exception as e:
            logger.error("Error notificando conexion Fit uid=%s: %s", uid, e)

    if ok:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;"
            "padding:40px;background:#000;color:#fff'>"
            "<h2>✅ Google Fit conectado</h2>"
            "<p>Puedes cerrar esta ventana.</p></body></html>")
    return HTMLResponse("<html><body><h2>❌ Error</h2></body></html>", status_code=500)


# ── Handler del check-in (callback ci:) ───────────────────────────────────────
# Este endpoint no es HTTP — es manejado por el bot de Telegram
# Se registra en bot/handlers/__init__.py como callback_router

@app.on_event("shutdown")
async def shutdown():
    if _bot:
        await _bot.updater.stop()
        await _bot.stop()
        await _bot.shutdown()
