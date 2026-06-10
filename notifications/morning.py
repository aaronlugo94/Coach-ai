"""
notifications/morning.py — Invisible Coach v3.0

Briefing matutino adaptativo.
Se envía a la hora configurada por el usuario (hora_reminder),
calculada automáticamente como 2h antes de su hora de gym.

Contenido:
  - Estado SNC desde modelo Bannister
  - Rutina del día con pesos sugeridos
  - Macros del día (gym o descanso)
  - Ajuste automático si hay fatiga SNC

El APScheduler llama a enviar_recordatorios() cada minuto.
La función verifica qué usuarios tienen esa hora configurada.
"""
from __future__ import annotations
import logging
from datetime import datetime, date, timedelta

from db.database import (
    fetchall, get_usuario, get_estado, get_ejercicios_dia,
    get_peso_sugerido, get_estado_bannister, get_actividad_dia,
)
from engine.nutrition.macros import calcular_macros_dia
from ai.coach import generar_briefing
import gamification

logger = logging.getLogger(__name__)

GRUPO_ICON = {
    "empuje": "💪", "tiron": "🏋️", "pierna": "🦵",
    "gluteo": "🍑", "core":  "🎯", "cardio": "🏃",
}


def _hora_actual_local(timezone_offset: int = -7) -> str:
    """
    Hora actual en formato HH:MM.
    timezone_offset: -7 = MST (Arizona), -6 = CST, etc.
    Por ahora usamos UTC-7 (Arizona/Tucson). En el futuro del perfil del usuario.
    """
    ahora = datetime.utcnow() + timedelta(hours=timezone_offset)
    return ahora.strftime("%H:%M")


async def enviar_recordatorios(bot=None):
    """
    Llamada cada minuto por el scheduler.
    Envía briefing a los usuarios cuya hora_reminder coincide con la hora actual.
    """
    if not bot:
        return

    hora_actual = _hora_actual_local()

    usuarios = fetchall("""
        SELECT u.user_id, u.hora_reminder
        FROM usuarios u
        JOIN usuarios_permitidos p ON u.user_id = p.user_id
        WHERE u.onboarding_done = 1
          AND u.hora_reminder IS NOT NULL
    """, ())

    for u in usuarios:
        hora = u.get("hora_reminder", "")
        if not hora or hora.startswith("PAUSA"):
            continue
        if hora != hora_actual:
            continue

        try:
            msg = await _construir_briefing(u["user_id"])
            if msg:
                await bot.send_message(
                    chat_id=u["user_id"],
                    text=msg,
                    parse_mode="HTML",
                )
                logger.info("Briefing enviado uid=%s hora=%s", u["user_id"], hora_actual)
        except Exception as e:
            logger.error("Error briefing uid=%s: %s", u["user_id"], e)


async def _construir_briefing(uid: int) -> str:
    """Construye el briefing matutino con todos los datos reales."""
    u        = get_usuario(uid)
    if not u:
        return ""

    semana, dia     = get_estado(uid)
    ejs             = get_ejercicios_dia(uid, semana, dia)
    ejs_fuerza      = [e for e in ejs if not e.get("es_cardio")]
    grupo           = ejs_fuerza[0]["grupo"] if ejs_fuerza else ""
    es_gym          = bool(ejs_fuerza)
    bann            = get_estado_bannister(uid)
    racha           = gamification.get_racha(uid)
    macros          = calcular_macros_dia(uid, es_gym=es_gym)
    activ_ayer      = get_actividad_dia(uid)

    # Agregar pesos sugeridos a cada ejercicio
    for e in ejs_fuerza:
        sug = get_peso_sugerido(
            uid, e["ejercicio_id"], e.get("reps","8-10"), e.get("patron","")
        )
        e["peso_sugerido"]  = sug
        e["es_nuevo_peso"]  = False
        if sug:
            # Detectar si el peso subió vs última sesión
            from db.database import get_historial_peso
            hist = get_historial_peso(uid, e["ejercicio_id"], 1)
            if hist and float(hist[0]["peso_lbs"]) < sug:
                e["es_nuevo_peso"] = True

    # Datos para Gemini
    datos = {
        "usuario":   u,
        "bannister": bann,
        "macros":    macros,
        "hoy": {
            "semana":     semana,
            "dia":        dia,
            "grupo":      grupo,
            "label":      _get_label_semana(semana, u.get("nivel","intermedio")),
            "ejercicios": ejs_fuerza,
            "es_gym":     es_gym,
        },
        "actividad_ayer": activ_ayer or {},
        "racha": racha,
    }

    texto = await generar_briefing(datos)

    # Agregar racha si hay
    if racha >= 3:
        texto = f"🔥 {racha} días de racha\n\n" + texto

    return texto


def _get_label_semana(semana: int, nivel: str) -> str:
    labels = {
        "principiante": {1:"MEV",2:"MAV",3:"MRV",4:"Deload"},
        "intermedio":   {1:"MEV",2:"MAV",3:"MRV",4:"Deload"},
        "avanzado":     {1:"MEV",2:"MAV",3:"MRV",4:"Deload"},
    }
    return labels.get(nivel,{}).get(semana,"")
