"""
notifications/night.py — Invisible Coach v3.0

Check-in nocturno de 2 taps + análisis Gemini.
Se envía 2h después de la hora de gym del usuario.

Flujo:
  1. Bot envía mensaje con 4 botones (2×2)
  2. Usuario toca 2 botones en <10 segundos
  3. Bot genera análisis con Gemini y responde inmediatamente
  4. Actualiza modelo Bannister con los datos del día
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db.database import (
    fetchall, get_usuario, get_estado, get_ejercicios_dia,
    get_historial_peso, get_estado_bannister, get_actividad_dia,
    save_sesion, actualizar_bannister,
)
from engine.nutrition.macros import calcular_macros_dia
from ai.coach import generar_checkin
import gamification

logger = logging.getLogger(__name__)


def _hora_actual_local(tz_offset: int = -7) -> str:
    return (datetime.utcnow() + timedelta(hours=tz_offset)).strftime("%H:%M")


async def enviar_resumenes(bot=None):
    """
    Llamada cada minuto por el scheduler.
    Envía check-in a los usuarios cuya hora_checkin coincide con ahora.
    """
    if not bot:
        return

    hora_actual = _hora_actual_local()

    usuarios = fetchall("""
        SELECT u.user_id, u.hora_checkin
        FROM usuarios u
        JOIN usuarios_permitidos p ON u.user_id = p.user_id
        WHERE u.onboarding_done = 1
          AND u.hora_checkin IS NOT NULL
    """, ())

    for u in usuarios:
        hora = u.get("hora_checkin","")
        if not hora or hora != hora_actual:
            continue
        try:
            await _enviar_checkin(bot, u["user_id"])
        except Exception as e:
            logger.error("Error check-in uid=%s: %s", u["user_id"], e)


async def _enviar_checkin(bot, uid: int):
    """Envía el mensaje de check-in con los botones.
    El tap de sueño solo se incluye si el usuario NO tiene Google Fit
    conectado — si lo tiene, el dato ya llega automático."""
    semana, dia = get_estado(uid)
    ejs         = get_ejercicios_dia(uid, semana, dia)
    es_gym      = bool([e for e in ejs if not e.get("es_cardio")])

    from engine.body.healthconnect import esta_conectado
    pedir_sueño = not esta_conectado(uid)

    if es_gym:
        texto = (
            "🌙 <b>Check-in de hoy</b>\n\n"
            "¿Cómo fue tu día? Unos taps y listo 👇"
        )
        rows = [
            [
                InlineKeyboardButton("💪 Rutina completada", callback_data=f"ci:rutina:si:{semana}:{dia}"),
                InlineKeyboardButton("🛏️ Descanso",          callback_data=f"ci:rutina:no:{semana}:{dia}"),
            ],
            [
                InlineKeyboardButton("🥗 Dieta en punto",    callback_data="ci:dieta:si"),
                InlineKeyboardButton("📊 Hubo variación",    callback_data="ci:dieta:no"),
            ],
        ]
    else:
        texto = (
            "🌙 <b>Check-in — día de descanso</b>\n\n"
            "¿Cómo estuvo tu recuperación?"
        )
        rows = [
            [
                InlineKeyboardButton("✅ Bien descansado",   callback_data=f"ci:rutina:descanso:{semana}:{dia}"),
                InlineKeyboardButton("😓 Cansado igual",     callback_data=f"ci:rutina:cansado:{semana}:{dia}"),
            ],
            [
                InlineKeyboardButton("🥗 Comí bien",        callback_data="ci:dieta:si"),
                InlineKeyboardButton("📊 Comí diferente",   callback_data="ci:dieta:no"),
            ],
        ]

    if pedir_sueño:
        texto += "\n\n<i>Sin reloj conectado — dinos cuánto dormiste anoche</i>"
        rows.append([
            InlineKeyboardButton("😫 <6h",  callback_data="ci:sueño:5.5"),
            InlineKeyboardButton("😐 6-7h", callback_data="ci:sueño:6.5"),
            InlineKeyboardButton("✅ 7-8h", callback_data="ci:sueño:7.5"),
            InlineKeyboardButton("🌟 8h+",  callback_data="ci:sueño:8.5"),
        ])

    kb = InlineKeyboardMarkup(rows)

    await bot.send_message(
        chat_id=uid,
        text=texto,
        reply_markup=kb,
        parse_mode="HTML",
    )


async def procesar_checkin(uid: int, rutina: str, dieta: str,
                           semana: int, dia: str, context) -> str:
    """
    Procesa el check-in y genera el análisis nocturno.
    Llamado desde el handler de callbacks ci: en handlers/__init__.py
    """
    u         = get_usuario(uid)
    bann      = get_estado_bannister(uid)
    activ     = get_actividad_dia(uid)
    semana_n, dia_s = get_estado(uid)
    ejs       = get_ejercicios_dia(uid, semana_n, dia_s)
    ejs_fuerza= [e for e in ejs if not e.get("es_cardio")]
    es_gym    = bool(ejs_fuerza)

    # Datos de pesos usados hoy
    pesos_usados = []
    for e in ejs_fuerza[:4]:
        hist = get_historial_peso(uid, e["ejercicio_id"], 2)
        if hist:
            peso_hoy  = float(hist[0]["peso_lbs"])
            peso_prev = float(hist[1]["peso_lbs"]) if len(hist) > 1 else peso_hoy
            pesos_usados.append({
                "ejercicio":   e["ejercicio"],
                "peso_lbs":    peso_hoy,
                "reps":        hist[0].get("reps_completadas",""),
                "es_nuevo_peso": peso_hoy > peso_prev,
            })

    # Guardar sesión en DB
    rutina_ok  = rutina in ("si","descanso")
    completada = rutina == "si"
    save_sesion(uid, semana, dia,
                completada=1 if completada else 0,
                fatiga_global=2,
                grupo=ejs_fuerza[0]["grupo"] if ejs_fuerza else "descanso")

    # Actualizar modelo Bannister
    actualizar_bannister(uid)

    # Datos para mañana
    from db.database import avanzar_dia
    sem_man, dia_man = avanzar_dia(uid, semana, dia)
    ejs_man = get_ejercicios_dia(uid, sem_man, dia_man)
    grupo_man = ejs_man[0]["grupo"] if ejs_man and not ejs_man[0].get("es_cardio") else ""

    macros = calcular_macros_dia(uid, es_gym=bool(ejs_man))
    racha  = gamification.get_racha(uid)

    datos = {
        "usuario":     u,
        "bannister":   bann,
        "sesion":      {"completada": completada, "fatiga_global": 2},
        "dieta_ok":    dieta == "si",
        "pesos_usados": pesos_usados,
        "actividad":   activ or {},
        "macros":      macros,
        "manana":      {"grupo": grupo_man, "semana": sem_man, "dia": dia_man},
        "racha":       racha,
    }

    texto = await generar_checkin(datos)

    # Agregar KB para mañana
    return texto


async def generar_resumen_dominical(uid: int, bot=None) -> str:
    """
    Resumen del domingo — se envía automáticamente cada domingo a las 8pm.
    Incluye progresión de fuerza, cambio de peso y proyección de meta.
    """
    from db.database import (get_pesajes_recientes, fetchall as fa)
    from ai.coach import generar_resumen_semanal

    u        = get_usuario(uid)
    semana, _ = get_estado(uid)
    pesajes  = get_pesajes_recientes(uid, 14)
    racha    = gamification.get_racha(uid)

    # Cambio de peso semanal
    cambio_peso = 0
    if len(pesajes) >= 2:
        cambio_peso = round(float(pesajes[0]["peso_kg"]) - float(pesajes[-1]["peso_kg"]), 2)

    cambio_grasa = None
    if len(pesajes) >= 2 and pesajes[0].get("grasa_pct") and pesajes[-1].get("grasa_pct"):
        cambio_grasa = round(float(pesajes[0]["grasa_pct"]) - float(pesajes[-1]["grasa_pct"]), 1)

    # Sesiones completadas esta semana
    sesiones = fa("""
        SELECT COUNT(*) n FROM sesiones
        WHERE user_id=? AND completada=1
        AND fecha >= date('now','-7 days')
    """, (uid,))
    completadas = sesiones[0]["n"] if sesiones else 0

    # Progresión de fuerza
    progs_raw = fa("""
        SELECT p.ejercicio_id, r.ejercicio,
               MAX(p.peso_lbs) peso_actual, MIN(p.peso_lbs) peso_inicio,
               MAX(p.peso_lbs) - MIN(p.peso_lbs) cambio
        FROM pesos p
        JOIN rutinas r ON p.ejercicio_id=r.ejercicio_id AND r.user_id=p.user_id
        WHERE p.user_id=? AND p.fecha >= date('now','-30 days')
        GROUP BY p.ejercicio_id
        HAVING cambio > 0
        ORDER BY cambio DESC LIMIT 4
    """, (uid,))

    progresiones = [
        {"ejercicio": r["ejercicio"], "peso_inicio": r["peso_inicio"],
         "peso_actual": r["peso_actual"], "cambio": r["cambio"]}
        for r in progs_raw
    ]

    datos = {
        "usuario":            u,
        "semana":             semana,
        "sesiones_completadas": completadas,
        "sesiones_total":     int(u.get("dias_semana") or 4),
        "cambio_peso_kg":     cambio_peso,
        "cambio_grasa_pct":   cambio_grasa,
        "grasa_pct_actual":   float(pesajes[0]["grasa_pct"]) if pesajes and pesajes[0].get("grasa_pct") else None,
        "progresiones_fuerza": progresiones,
        "racha":              racha,
    }

    return await generar_resumen_semanal(datos)


async def enviar_resumen_dominical(bot=None):
    """
    Cron: cada domingo a las 20:00 hora local.
    """
    if not bot:
        return

    hora_actual = _hora_actual_local()
    if hora_actual != "20:00":
        return

    from datetime import date as _date
    if _date.today().weekday() != 6:  # 6 = domingo
        return

    usuarios = fetchall("""
        SELECT u.user_id FROM usuarios u
        JOIN usuarios_permitidos p ON u.user_id=p.user_id
        WHERE u.onboarding_done=1
    """, ())

    for u in usuarios:
        try:
            msg = await generar_resumen_dominical(u["user_id"])
            if msg:
                await bot.send_message(
                    chat_id=u["user_id"],
                    text=f"📊 <b>Resumen semanal</b>\n\n{msg}",
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error("Error resumen dominical uid=%s: %s", u["user_id"], e)
