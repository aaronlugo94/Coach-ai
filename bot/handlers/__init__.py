"""
bot/handlers/__init__.py — Invisible Coach v4.0
Router central de callbacks. Registra todos los handlers.
"""
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                           MessageHandler, filters)
from db.database import get_allowed_users
from .menu import (cmd_start, cmd_reset_plan, cmd_login, cmd_conectar_fit,
                   cmd_conectar_renpho,
                   cmd_sethorario, cmd_help, cmd_adduser, handler_texto,
                   handle_menu, handle_rst, handle_horario)
from .onboarding import (
    handle_ob, handle_cal, handle_num, handle_sexo,
    handle_nv, handle_dy, handle_dur, handle_gym_hora, handle_am, handle_lm,
    handle_dt, handle_prot, handle_rt, handle_prep, handle_elec,
    handle_sueño_hab, handle_trabajo, handle_estres, handle_ra, handle_wear,
)
from .gym import handle_ej_start, handle_pw, handle_ej_ok, handle_fb, handle_sue, handle_skip
from .checkin import handle_ci
import logging

logger = logging.getLogger(__name__)


async def callback_router(update, context):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data or ""

    # Onboarding no requiere estar en lista de permitidos
    ONBOARDING_PREFIXES = (
        "ob:","cal:","num:","sexo:",
        "nv:","dy:","dur:","gym_hora:","am:","lm:",
        "dt:","prot:","rt:","prep:","elec:",
        "sueño_hab:","trabajo:","estres:","ra:","wear:",
    )
    es_onboarding = any(data.startswith(p) for p in ONBOARDING_PREFIXES)

    if not es_onboarding and uid not in get_allowed_users():
        await query.answer("Sin acceso. Completa el setup primero.")
        return

    try:
        await query.answer()
    except Exception:
        pass

    try:
        # Alias legacy
        if data.startswith("menu:"): data = "m:" + data.split(":",1)[1]

        # ── Menú principal ────────────────────────────────────────────────
        if   data.startswith("m:"):          await handle_menu(query, uid, context)
        elif data.startswith("rst:"):        await handle_rst(query, uid, context)
        elif data.startswith("horario:"):    await handle_horario(query, uid)

        # ── Onboarding — Bloque 1: Perfil biológico ───────────────────────
        elif data.startswith("ob:"):         await handle_ob(query, uid, context)
        elif data.startswith("cal:"):        await handle_cal(query, uid, context)
        elif data.startswith("num:"):        await handle_num(query, uid, context)
        elif data.startswith("sexo:"):       await handle_sexo(query, uid)

        # ── Onboarding — Bloque 2: Experiencia y capacidad mecánica ──────
        elif data.startswith("nv:"):         await handle_nv(query, uid)
        elif data.startswith("dy:"):         await handle_dy(query, uid)
        elif data.startswith("dur:"):        await handle_dur(query, uid)
        elif data.startswith("gym_hora:"):   await handle_gym_hora(query, uid)
        elif data.startswith("am:"):         await handle_am(query, uid)
        elif data.startswith("lm:"):         await handle_lm(query, uid, context)

        # ── Onboarding — Bloque 3: Nutrición ─────────────────────────────
        elif data.startswith("dt:"):         await handle_dt(query, uid, context)
        elif data.startswith("prot:"):       await handle_prot(query, uid, context)
        elif data.startswith("rt:"):         await handle_rt(query, uid, context)
        elif data.startswith("prep:"):       await handle_prep(query, uid)
        elif data.startswith("elec:"):       await handle_elec(query, uid, context)

        # ── Onboarding — Bloque 4: Recuperación ──────────────────────────
        elif data.startswith("sueño_hab:"):  await handle_sueño_hab(query, uid)
        elif data.startswith("trabajo:"):    await handle_trabajo(query, uid)
        elif data.startswith("estres:"):     await handle_estres(query, uid)
        elif data.startswith("ra:"):         await handle_ra(query, uid, context)
        elif data.startswith("wear:"):       await handle_wear(query, uid, context)

        # ── Gym: sesión activa ────────────────────────────────────────────
        elif data.startswith("ej_start:"):   await handle_ej_start(query, uid, context)
        elif data.startswith("pw:"):         await handle_pw(query, uid, context)
        elif data.startswith("ej_ok:"):      await handle_ej_ok(query, uid, context)
        elif data.startswith("fb:"):         await handle_fb(query, uid)
        elif data.startswith("sue:"):        await handle_sue(query, uid)
        elif data.startswith("skip:"):       await handle_skip(query, uid)

        # ── Check-in nocturno ─────────────────────────────────────────────
        elif data.startswith("ci:"):          await handle_ci(query, uid, context)

        else:
            logger.debug("Callback no manejado: %s", data)

    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.error("callback [%s] uid=%s: %s", data, uid, e, exc_info=True)
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"❌ Error interno. Escribe /start\n<code>{str(e)[:100]}</code>",
                    parse_mode="HTML")
            except Exception:
                pass


def register_handlers(app: Application):
    allowed = get_allowed_users()
    logger.info("Usuarios permitidos: %s", allowed)
    logger.info("Invisible Coach handlers v4.0")

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("login",        cmd_login))
    app.add_handler(CommandHandler("sethorario",   cmd_sethorario))
    app.add_handler(CommandHandler("reset_plan",   cmd_reset_plan))
    app.add_handler(CommandHandler("conectar_fit", cmd_conectar_fit))
    app.add_handler(CommandHandler("conectar_renpho", cmd_conectar_renpho))
    app.add_handler(CommandHandler("help",         cmd_help))
    app.add_handler(CommandHandler("adduser",      cmd_adduser))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler_texto))
