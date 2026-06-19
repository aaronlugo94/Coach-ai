"""
bot/handlers/checkin.py — Invisible Coach v3.0

Maneja los callbacks del check-in nocturno (ci:).
Los botones los genera notifications/night.py.
"""
from __future__ import annotations
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def handle_ci(query, uid: int, context):
    """
    Procesa el check-in nocturno.
    callback_data: ci:tipo:valor:semana:dia
    Tipos: rutina | dieta | sueño
    El tap de sueño solo se pide si el usuario NO tiene Google Fit
    conectado — si lo tiene, el dato ya llega automático cada mañana
    y preguntarlo de nuevo sería redundante.
    """
    parts = query.data.split(":")
    tipo  = parts[1] if len(parts) > 1 else ""

    # Acumulamos en user_data hasta tener todas las respuestas necesarias
    ci = context.user_data.get("checkin", {})

    if tipo == "rutina":
        valor  = parts[2] if len(parts) > 2 else "no"
        semana = int(parts[3]) if len(parts) > 3 else 1
        dia    = parts[4]     if len(parts) > 4 else "lunes"
        ci["rutina"]  = valor
        ci["semana"]  = semana
        ci["dia"]     = dia

    elif tipo == "dieta":
        valor = parts[2] if len(parts) > 2 else "no"
        ci["dieta"] = valor

    elif tipo == "sueño":
        horas = parts[2] if len(parts) > 2 else "7.5"
        ci["sueño"] = float(horas)
        from db.database import upsert_usuario
        upsert_usuario(uid, sueño_horas=float(horas))

    context.user_data["checkin"] = ci

    from engine.body.healthconnect import esta_conectado
    necesita_sueño = not esta_conectado(uid)
    campos_requeridos = {"rutina", "dieta"} | ({"sueño"} if necesita_sueño else set())

    if campos_requeridos.issubset(ci.keys()):
        context.user_data["checkin"] = {}  # reset
        await _procesar_completo(query, uid, context, ci)
    else:
        TAP_LABEL = {"rutina": "✅", "dieta": "🥗", "sueño": "😴"}
        tap = TAP_LABEL.get(tipo, "✅")
        try:
            await query.edit_message_text(
                query.message.text + f"\n\n{tap} Registrado — toca la siguiente opción 👆",
                reply_markup=query.message.reply_markup,
                parse_mode="HTML",
            )
        except Exception:
            pass


async def _procesar_completo(query, uid: int, context, ci: dict):
    """Genera el análisis con Gemini y actualiza el estado."""
    try:
        await query.edit_message_text(
            "🔄 Analizando tu día...", parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        from notifications.night import procesar_checkin
        semana = ci.get("semana", 1)
        dia    = ci.get("dia", "lunes")
        rutina = ci.get("rutina", "no")
        dieta  = ci.get("dieta", "no")

        texto = await procesar_checkin(uid, rutina, dieta, semana, dia, context)

        if not texto:
            texto = "Día registrado ✅\nDescansa bien esta noche."

        # Avanzar al siguiente día
        from db.database import avanzar_dia, set_estado
        if rutina == "si":
            sem_new, dia_new = avanzar_dia(uid, semana, dia)
            set_estado(uid, sem_new, dia_new)

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💪 Ver rutina de mañana", callback_data="m:hoy")
        ]])

        try:
            await query.edit_message_text(
                f"🌙 <b>Análisis del día</b>\n\n{texto}",
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🌙 <b>Análisis del día</b>\n\n{texto}",
                reply_markup=kb,
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error("Error procesando check-in uid=%s: %s", uid, e, exc_info=True)
        try:
            await query.edit_message_text("✅ Día registrado. Análisis en camino.")
        except Exception:
            pass
