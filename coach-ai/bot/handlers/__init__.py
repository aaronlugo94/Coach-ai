"""
bot/handlers/__init__.py — Registra todos los handlers.
"""
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                           MessageHandler, filters)
from db.database import get_allowed_users
from .menu import (cmd_start, cmd_reset_plan, cmd_login, cmd_conectar_fit,
                   cmd_sethorario, cmd_help, cmd_adduser, handler_texto,
                   handle_menu, handle_rst, handle_horario)
from .onboarding import handle_ob, handle_nv, handle_am, handle_dy, handle_lm, handle_hr, handle_dt, handle_rt
from .gym import handle_ej_start, handle_pw, handle_ej_ok, handle_fb, handle_sue, handle_skip
import logging

logger = logging.getLogger(__name__)


async def callback_router(update, context):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data or ""

    if uid not in get_allowed_users():
        await query.answer("Sin acceso.")
        return
    try: await query.answer()
    except Exception: pass

    try:
        # Aliases para compatibilidad
        if data.startswith("menu:"): data = "m:" + data.split(":",1)[1]

        if data.startswith("m:"):         await handle_menu(query, uid, context)
        elif data.startswith("rst:"):     await handle_rst(query, uid, context)
        elif data.startswith("ob:"):      await handle_ob(query, uid, context)
        elif data.startswith("nv:"):      await handle_nv(query, uid)
        elif data.startswith("am:"):      await handle_am(query, uid)
        elif data.startswith("dy:"):      await handle_dy(query, uid)
        elif data.startswith("lm:"):      await handle_lm(query, uid)
        elif data.startswith("hr:"):      await handle_hr(query, uid, context)
        elif data.startswith("dt:"):      await handle_dt(query, uid, context)
        elif data.startswith("rt:"):      await handle_rt(query, uid, context)
        elif data.startswith("ej_start:"): await handle_ej_start(query, uid, context)
        elif data.startswith("pw:"):      await handle_pw(query, uid, context)
        elif data.startswith("ej_ok:"):   await handle_ej_ok(query, uid, context)
        elif data.startswith("fb:"):      await handle_fb(query, uid)
        elif data.startswith("sue:"):     await handle_sue(query, uid)
        elif data.startswith("skip:"):    await handle_skip(query, uid)
        elif data.startswith("horario:"): await handle_horario(query, uid)
        else: logger.debug("Callback no manejado: %s", data)

    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.error("callback [%s] uid=%s: %s", data, uid, e, exc_info=True)
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"❌ Error. Escribe /start\n<code>{str(e)[:100]}</code>",
                    parse_mode="HTML")
            except Exception: pass


def register_handlers(app: Application):
    allowed = get_allowed_users()
    logger.info("Usuarios permitidos: %s", allowed)
    logger.info("Coach AI handlers v1.0")

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("login",        cmd_login))
    app.add_handler(CommandHandler("sethorario",   cmd_sethorario))
    app.add_handler(CommandHandler("reset_plan",   cmd_reset_plan))
    app.add_handler(CommandHandler("conectar_fit", cmd_conectar_fit))
    app.add_handler(CommandHandler("help",         cmd_help))
    app.add_handler(CommandHandler("adduser",      cmd_adduser))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler_texto))
