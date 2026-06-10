"""
notifications/engagement.py — Invisible Coach v3.0

Notificaciones de enganche automáticas.
El scheduler las evalúa cada mañana a las 9am.

Tipos:
  1. Sin entrenar 3+ días → menciona el peso exacto que le espera
  2. HRV bajo → acción concreta de recuperación
  3. Progresión semanal → proyecta cuándo llega a la meta
  4. Racha → reconocimiento con número real
  5. Refeed activado → explicación científica simple
"""
from __future__ import annotations
import logging
from datetime import date, timedelta

from db.database import (
    fetchall, get_usuario, get_estado, get_ejercicios_dia,
    get_peso_sugerido, get_estado_bannister, get_pesajes_recientes,
)
from ai.coach import generar_notificacion
import gamification

logger = logging.getLogger(__name__)


async def evaluar_y_enviar(bot=None):
    """
    Evaluada cada mañana a las 9am.
    Para cada usuario activo, verifica si aplica alguna notificación.
    Máximo 1 notificación por usuario por día.
    """
    if not bot:
        return

    usuarios = fetchall("""
        SELECT u.user_id FROM usuarios u
        JOIN usuarios_permitidos p ON u.user_id=p.user_id
        WHERE u.onboarding_done=1
    """, ())

    for u in usuarios:
        uid = u["user_id"]
        try:
            msg = await _evaluar_usuario(uid)
            if msg:
                await bot.send_message(
                    chat_id=uid,
                    text=msg,
                    parse_mode="HTML",
                )
                logger.info("Notificación enganche enviada uid=%s", uid)
        except Exception as e:
            logger.error("Error engagement uid=%s: %s", uid, e)


async def _evaluar_usuario(uid: int) -> str | None:
    """
    Evalúa qué notificación aplica para el usuario hoy.
    Prioridad: HRV bajo > Sin entrenar > Racha > Progresión.
    Retorna None si no aplica ninguna.
    """
    u     = get_usuario(uid)
    bann  = get_estado_bannister(uid)
    racha = gamification.get_racha(uid)

    # ── 1. HRV bajo (prioridad máxima — salud primero) ────────────────────────
    if bann.get("fatiga_snc") and bann.get("snc_pct", 100) < 75:
        datos = {
            "usuario":       u,
            "hrv":           _get_hrv_ayer(uid),
            "hrv_baseline":  u.get("hrv_baseline", 60),
        }
        return await generar_notificacion("hrv_bajo", datos)

    # ── 2. Sin entrenar 3+ días ───────────────────────────────────────────────
    dias_sin_gym = _dias_sin_entrenar(uid)
    if dias_sin_gym >= 3:
        semana, dia = get_estado(uid)
        ejs = get_ejercicios_dia(uid, semana, dia)
        ejs_fuerza = [e for e in ejs if not e.get("es_cardio")]
        primer_ej = ejs_fuerza[0] if ejs_fuerza else None
        peso_sug  = None
        if primer_ej:
            peso_sug = get_peso_sugerido(
                uid, primer_ej["ejercicio_id"],
                primer_ej.get("reps","8-10"), primer_ej.get("patron","")
            )
        datos = {
            "usuario":            u,
            "dias_sin_gym":       dias_sin_gym,
            "ejercicio_proximo":  primer_ej["ejercicio"] if primer_ej else "",
            "peso_sugerido":      peso_sug or 0,
        }
        return await generar_notificacion("sin_entrenar", datos)

    # ── 3. Racha notable (3, 7, 14, 21, 30 días) ─────────────────────────────
    RACHAS_NOTABLES = {3, 7, 14, 21, 30, 60, 90}
    if racha in RACHAS_NOTABLES:
        progresiones = _get_progresiones_semana(uid)
        logro = ""
        if progresiones:
            p = progresiones[0]
            logro = f"{p['ejercicio']} {p['peso_inicio']}→{p['peso_actual']} lbs"
        datos = {
            "usuario": u,
            "racha":   racha,
            "logro_reciente": logro,
        }
        return await generar_notificacion("racha", datos)

    # ── 4. Progresión semanal (cada lunes) ────────────────────────────────────
    if date.today().weekday() == 0:  # lunes
        progresiones = _get_progresiones_semana(uid)
        if progresiones:
            datos = {
                "usuario":      u,
                "semana":       _get_semana_actual(uid),
                "progresiones": progresiones,
            }
            return await generar_notificacion("progresion_semanal", datos)

    return None


def _dias_sin_entrenar(uid: int) -> int:
    """Días desde la última sesión completada."""
    rows = fetchall("""
        SELECT fecha FROM sesiones
        WHERE user_id=? AND completada=1
        ORDER BY fecha DESC LIMIT 1
    """, (uid,))
    if not rows:
        return 999
    ultima = rows[0]["fecha"]
    try:
        delta = (date.today() - date.fromisoformat(ultima)).days
        return delta
    except Exception:
        return 999


def _get_hrv_ayer(uid: int) -> float:
    """HRV del día anterior."""
    from db.database import get_actividad_dia
    ayer = str(date.today() - timedelta(days=1))
    activ = get_actividad_dia(uid, ayer)
    return activ.get("hrv_promedio", 0) if activ else 0


def _get_progresiones_semana(uid: int) -> list[dict]:
    """Progresiones de fuerza de los últimos 7 días."""
    rows = fetchall("""
        SELECT p.ejercicio_id, r.ejercicio,
               MAX(p.peso_lbs) peso_actual, MIN(p.peso_lbs) peso_inicio,
               MAX(p.peso_lbs) - MIN(p.peso_lbs) cambio
        FROM pesos p
        JOIN rutinas r ON p.ejercicio_id=r.ejercicio_id AND r.user_id=p.user_id
        WHERE p.user_id=? AND p.fecha >= date('now','-7 days')
        GROUP BY p.ejercicio_id
        HAVING cambio > 0
        ORDER BY cambio DESC LIMIT 3
    """, (uid,))
    return [
        {"ejercicio": r["ejercicio"], "peso_inicio": r["peso_inicio"],
         "peso_actual": r["peso_actual"], "cambio": r["cambio"]}
        for r in rows
    ]


def _get_semana_actual(uid: int) -> int:
    from db.database import get_estado
    semana, _ = get_estado(uid)
    return semana
