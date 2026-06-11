"""
engine/body/renpho.py — Invisible Coach v3.0

Sync con báscula Renpho.
LÍMITE CRÍTICO: máximo 1 intento por hora, ventana 6am-10am.
Se detiene en cuanto obtiene un pesaje del día — evita rate limiting / bloqueos.

API no oficial de Renpho (qnclub) — endpoints reverse-engineered.
Si Renpho cambia su API, esto puede requerir actualización.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timezone

import httpx

from db.database import (
    get_usuario, upsert_usuario, save_pesaje,
    calcular_ajuste_calorico,
)

logger = logging.getLogger(__name__)

BASE_URL  = "https://renpho.qnclub.com/api/v3"
LOGIN_URL = f"{BASE_URL}/users/sign_in.json"
MEAS_URL  = f"{BASE_URL}/measurements/list.json"

# Ventana de sync: solo entre estas horas (hora local del usuario)
SYNC_HORA_INICIO = 6
SYNC_HORA_FIN    = 10


async def _login(email: str, password: str) -> str | None:
    """Login a Renpho. Retorna terminal_user_session_key o None."""
    payload = {
        "secure_flag": 1,
        "email":       email,
        "password":    password,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(LOGIN_URL, params=payload)
        if r.status_code != 200:
            logger.warning("Renpho login HTTP %s", r.status_code)
            return None
        data = r.json()
        if data.get("status_code") != "20000":
            logger.warning("Renpho login error: %s", data.get("status_message"))
            return None
        return data.get("terminal_user_session_key")
    except Exception as e:
        logger.error("Renpho login exception: %s", e)
        return None


async def _fetch_ultimo_pesaje(session_key: str, email: str) -> dict | None:
    """Obtiene la medición más reciente."""
    params = {
        "terminal_user_session_key": session_key,
        "user_id":     email,
        "last_at":     int(datetime.now(timezone.utc).timestamp()) + 86400,
        "locale":      "es",
        "app_id":      "Renpho",
        "fit_indicator": 0,
        "limit":       1,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(MEAS_URL, params=params)
        if r.status_code != 200:
            logger.warning("Renpho measurements HTTP %s", r.status_code)
            return None
        data = r.json()
        items = data.get("last_ary", []) or data.get("measurements", [])
        if not items:
            return None
        return items[0]
    except Exception as e:
        logger.error("Renpho fetch exception: %s", e)
        return None


def _parse_medicion(raw: dict) -> dict:
    """Convierte la respuesta de Renpho al formato de save_pesaje()."""
    ts = raw.get("time_stamp") or raw.get("createtime", 0)
    fecha = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    return {
        "Fecha":            fecha,
        "Timestamp":        int(ts),
        "Peso_kg":          raw.get("weight"),
        "Grasa_Porcentaje": raw.get("bodyfat"),
        "Musculo_Pct":      raw.get("muscle"),
        "Musculo_kg":       (raw.get("weight",0) * raw.get("muscle",0) / 100)
                             if raw.get("weight") and raw.get("muscle") else None,
        "Agua":             raw.get("water"),
        "VisFat":           raw.get("visfat"),
        "BMR":              raw.get("bmr"),
        "BMI":              raw.get("bmi"),
        "EdadMetabolica":   raw.get("bodyage"),
        "Proteina":         raw.get("protein"),
    }


async def sync_usuario(uid: int) -> dict:
    """
    Sincroniza el último pesaje de Renpho para el usuario.
    Retorna {"ok": bool, "nuevo": bool, "datos": dict|None, "razon": str}
    """
    u = get_usuario(uid)
    if not u or not u.get("renpho_email") or not u.get("renpho_password"):
        return {"ok": False, "nuevo": False, "razon": "sin credenciales Renpho"}

    session_key = await _login(u["renpho_email"], u["renpho_password"])
    if not session_key:
        return {"ok": False, "nuevo": False, "razon": "login falló"}

    raw = await _fetch_ultimo_pesaje(session_key, u["renpho_email"])
    if not raw:
        return {"ok": True, "nuevo": False, "razon": "sin mediciones nuevas"}

    datos  = _parse_medicion(raw)
    es_nuevo = save_pesaje(uid, datos)

    if es_nuevo:
        logger.info(
            "Renpho sync uid=%s: %.1fkg %.1f%% grasa (nuevo)",
            uid, datos.get("Peso_kg") or 0, datos.get("Grasa_Porcentaje") or 0
        )
    else:
        logger.info("Renpho sync uid=%s: sin cambios (ya registrado)", uid)

    return {"ok": True, "nuevo": es_nuevo, "datos": datos if es_nuevo else None}


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULER — máximo 1 intento por hora, ventana 6am-10am
# ══════════════════════════════════════════════════════════════════════════════

def _hora_actual_local(tz_offset: int = -7) -> int:
    """Hora actual (0-23) en zona horaria local. Default Arizona (UTC-7)."""
    from datetime import timedelta
    return (datetime.utcnow() + timedelta(hours=tz_offset)).hour


async def sync_all_renpho(bot=None):
    """
    Llamado por el scheduler cada hora entre 6am-10am.
    Para cada usuario:
      - Si ya sincronizó hoy → skip
      - Si está fuera de la ventana 6-10am → skip
      - Si sync exitoso y hay dato nuevo → marca renpho_last_sync = hoy,
        recalcula SISO, notifica si hay ajuste relevante
    """
    from db.database import fetchall

    hora_actual = _hora_actual_local()
    if not (SYNC_HORA_INICIO <= hora_actual <= SYNC_HORA_FIN):
        return  # fuera de ventana — no hacer nada

    hoy = str(date.today())

    usuarios = fetchall("""
        SELECT user_id, renpho_last_sync FROM usuarios
        WHERE renpho_email IS NOT NULL
          AND renpho_password IS NOT NULL
          AND onboarding_done = 1
    """, ())

    for u in usuarios:
        uid = u["user_id"]

        # Ya sincronizó hoy — skip
        if u.get("renpho_last_sync") == hoy:
            continue

        try:
            resultado = await sync_usuario(uid)
        except Exception as e:
            logger.error("Renpho sync error uid=%s: %s", uid, e)
            continue

        if not resultado.get("ok"):
            logger.warning("Renpho uid=%s: %s", uid, resultado.get("razon"))
            continue

        if resultado.get("nuevo"):
            # Marcar como sincronizado hoy — no reintentar hasta mañana
            upsert_usuario(uid, renpho_last_sync=hoy)

            # Recalcular SISO con el nuevo peso
            ajuste = calcular_ajuste_calorico(uid)

            # Notificar solo si hay ajuste relevante (no "mantener")
            if bot and ajuste.get("accion") != "mantener":
                datos = resultado["datos"]
                emoji = "📉" if ajuste["accion"] == "reducir" else "📈"
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"⚖️ <b>Báscula sincronizada</b>\n\n"
                            f"Peso: {datos['Peso_kg']:.1f} kg"
                            + (f" · Grasa: {datos['Grasa_Porcentaje']:.1f}%" if datos.get("Grasa_Porcentaje") else "")
                            + f"\n\n{emoji} Ajuste SISO: {ajuste['kcal']} kcal — {ajuste['razon']}"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error("Notif Renpho uid=%s: %s", uid, e)
        # Si no hay dato nuevo, NO marcamos renpho_last_sync —
        # así reintenta la próxima hora dentro de la ventana 6-10am
