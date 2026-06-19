"""
bot/handlers/__init__.py — Invisible Coach v5.0
Router central de callbacks.
"""
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                           MessageHandler, filters)
from db.database import get_allowed_users
from .menu import (cmd_start, cmd_reset_plan, cmd_login, cmd_conectar_fit,
                   cmd_conectar_renpho, cmd_sethorario, cmd_help,
                   cmd_adduser, handler_texto, handle_menu, handle_rst, handle_horario)
from .onboarding import (
    handle_bienvenida, handle_wear_init, handle_wear_check, handle_prefill,
    handle_bloque, handle_quiere,
    handle_ob, handle_cal, handle_num, handle_sexo,
    handle_nv, handle_dy, handle_dur, handle_gym_hora, handle_am, handle_lm,
    handle_dt, handle_cocina, handle_n_comidas, handle_t_comida, handle_t_comida_back,
    handle_prot, handle_rt, handle_suple, handle_alcohol, handle_elec,
    handle_sueño_hab, handle_trabajo, handle_estres, handle_ra,
    handle_generar_final,
)
from .gym import (handle_ej_start, handle_prev, handle_pw, handle_ej_ok,
                  handle_fb, handle_sue, handle_skip,
                  handle_ej_swap, handle_ej_swap_pick)
from .checkin import handle_ci
import logging

logger = logging.getLogger(__name__)

# Prefijos que no requieren estar en lista de permitidos
ONBOARDING_PREFIXES = (
    "bienvenida:", "wear_init:", "wear_check:", "prefill:", "bloque:", "quiere:",
    "ob:", "cal:", "num:", "sexo:",
    "nv:", "dy:", "dur:", "gym_hora:", "am:", "lm:",
    "dt:", "cocina:", "n_comidas:", "t_comida:",
    "prot:", "rt:", "suple:", "alcohol:", "elec:",
    "sueño_hab:", "trabajo:", "estres:", "ra:",
    "generar:",
)


async def callback_router(update, context):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data or ""

    es_onboarding = any(data.startswith(p) for p in ONBOARDING_PREFIXES)

    if not es_onboarding and uid not in get_allowed_users():
        await query.answer("Completa el setup primero con /start")
        return

    try:
        await query.answer()
    except Exception:
        pass

    try:
        # ── Menú ──────────────────────────────────────────────────────────────
        if   data.startswith("m:"):          await handle_menu(query, uid, context)
        elif data.startswith("rst:"):        await handle_rst(query, uid, context)
        elif data.startswith("horario:"):    await handle_horario(query, uid)

        # ── Onboarding — inicio ───────────────────────────────────────────────
        elif data.startswith("bienvenida:"): await handle_bienvenida(query, uid, context)
        elif data.startswith("wear_init:"):  await handle_wear_init(query, uid, context)
        elif data.startswith("wear_check:"): await handle_wear_check(query, uid, context)
        elif data.startswith("prefill:"):    await handle_prefill(query, uid, context)
        elif data.startswith("bloque:"):     await handle_bloque(query, uid, context)
        elif data.startswith("quiere:"):     await handle_quiere(query, uid, context)

        # ── Onboarding — Bloque 1 ─────────────────────────────────────────────
        elif data.startswith("ob:"):         await handle_ob(query, uid, context)
        elif data.startswith("cal:"):        await handle_cal(query, uid, context)
        elif data.startswith("num:"):        await handle_num(query, uid, context)
        elif data.startswith("sexo:"):       await handle_sexo(query, uid, context)

        # ── Onboarding — Bloque 2 ─────────────────────────────────────────────
        elif data.startswith("nv:"):         await handle_nv(query, uid, context)
        elif data.startswith("dy:"):         await handle_dy(query, uid, context)
        elif data.startswith("dur:"):        await handle_dur(query, uid, context)
        elif data.startswith("gym_hora:"):   await handle_gym_hora(query, uid, context)
        elif data.startswith("am:"):         await handle_am(query, uid, context)
        elif data.startswith("lm:"):         await handle_lm(query, uid, context)

        # ── Onboarding — Bloque 3 ─────────────────────────────────────────────
        elif data.startswith("dt:"):         await handle_dt(query, uid, context)
        elif data.startswith("cocina:"):     await handle_cocina(query, uid, context)
        elif data.startswith("n_comidas:"):  await handle_n_comidas(query, uid, context)
        elif data.startswith("t_comida_back:"): await handle_t_comida_back(query, uid, context)
        elif data.startswith("t_comida:"):   await handle_t_comida(query, uid, context)
        elif data.startswith("prot:"):       await handle_prot(query, uid, context)
        elif data.startswith("rt:"):         await handle_rt(query, uid, context)
        elif data.startswith("suple:"):      await handle_suple(query, uid, context)
        elif data.startswith("alcohol:"):    await handle_alcohol(query, uid, context)
        elif data.startswith("elec:"):       await handle_elec(query, uid, context)

        # ── Onboarding — Bloque 4 ─────────────────────────────────────────────
        elif data.startswith("sueño_hab:"):  await handle_sueño_hab(query, uid, context)
        elif data.startswith("trabajo:"):    await handle_trabajo(query, uid, context)
        elif data.startswith("estres:"):     await handle_estres(query, uid, context)
        elif data.startswith("ra:"):         await handle_ra(query, uid, context)

        # ── Onboarding — Final ────────────────────────────────────────────────
        elif data.startswith("generar:"):    await handle_generar_final(query, uid, context)

        # ── Gym ───────────────────────────────────────────────────────────────
        elif data.startswith("ej_start:"):   await handle_ej_start(query, uid, context)
        elif data.startswith("prev:"):       await handle_prev(query, uid, context)
        elif data.startswith("pw:"):         await handle_pw(query, uid, context)
        elif data.startswith("ej_ok:"):      await handle_ej_ok(query, uid, context)
        elif data.startswith("ej_swp2:"):    await handle_ej_swap_pick(query, uid, context)
        elif data.startswith("ej_swap:"):    await handle_ej_swap(query, uid, context)
        elif data.startswith("fb:"):         await handle_fb(query, uid)
        elif data.startswith("sue:"):        await handle_sue(query, uid)
        elif data.startswith("skip:"):       await handle_skip(query, uid)

        # ── Check-in nocturno ─────────────────────────────────────────────────
        elif data.startswith("ci:"):         await handle_ci(query, uid, context)

        else:
            logger.debug("Callback no manejado: %s", data)

    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.error("callback [%s] uid=%s: %s", data, uid, e, exc_info=True)
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"Error interno. Escribe /start\n{str(e)[:100]}",
                    parse_mode="HTML")
            except Exception:
                pass


def register_handlers(app: Application):
    logger.info("Invisible Coach handlers v5.0")
    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("login",          cmd_login))
    app.add_handler(CommandHandler("sethorario",     cmd_sethorario))
    app.add_handler(CommandHandler("reset_plan",     cmd_reset_plan))
    app.add_handler(CommandHandler("conectar_fit",   cmd_conectar_fit))
    app.add_handler(CommandHandler("conectar_renpho",cmd_conectar_renpho))
    app.add_handler(CommandHandler("help",           cmd_help))
    app.add_handler(CommandHandler("adduser",        cmd_adduser))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler_texto))
