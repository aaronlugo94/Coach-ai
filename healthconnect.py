"""
engine/body/healthconnect.py

Google Fit REST API + Health Connect.
El OnePlus Watch 4 sincroniza a Health Connect → Google Fit.

Flujo OAuth2:
1. Usuario toca /conectar_fit
2. Bot genera URL de autorización
3. Usuario autoriza en Google
4. Callback llega a Railway (/auth/google/callback)
5. Se guarda refresh_token en DB
6. Cada mañana se llaman los endpoints y se guardan en actividad_diaria
"""
from __future__ import annotations
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from db.database import get_usuario, save_actividad, upsert_usuario

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI", "")
SCOPES        = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.body.read",
]

TOKEN_URL  = "https://oauth2.googleapis.com/token"
FITNESS_URL = "https://www.googleapis.com/fitness/v1/users/me"


# ══════════════════════════════════════════════════════════════════════════════
# OAUTH2 — GENERACIÓN DE URL Y EXCHANGE
# ══════════════════════════════════════════════════════════════════════════════

def get_auth_url(uid: int) -> str:
    """Genera la URL de autorización OAuth2 para Google Fit."""
    import urllib.parse
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         str(uid),  # para identificar al usuario en el callback
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


async def exchange_code(code: str, uid: int) -> bool:
    """
    Intercambia el código de autorización por access_token + refresh_token.
    Guarda el token en la DB.
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(TOKEN_URL, data={
            "code":          code,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        })

    if r.status_code != 200:
        logger.error("Error intercambiando código: %s", r.text)
        return False

    token_data = r.json()
    # Agregar timestamp de expiración
    token_data["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
    ).isoformat()

    upsert_usuario(uid, google_fit_token=json.dumps(token_data))
    logger.info("Google Fit conectado para uid=%s", uid)
    return True


async def _get_access_token(uid: int) -> str | None:
    """
    Obtiene un access_token válido.
    Si expiró, lo refresca automáticamente con el refresh_token.
    """
    usuario = get_usuario(uid)
    if not usuario or not usuario.get("google_fit_token"):
        return None

    token_data = json.loads(usuario["google_fit_token"])
    expires_at = datetime.fromisoformat(token_data.get("expires_at","2000-01-01"))

    # Si expira en menos de 5 minutos → refrescar
    if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
        refreshed = await _refresh_token(uid, token_data)
        if not refreshed:
            return None
        token_data = refreshed

    return token_data.get("access_token")


async def _refresh_token(uid: int, token_data: dict) -> dict | None:
    """Refresca el access_token usando el refresh_token."""
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        logger.error("Sin refresh_token para uid=%s", uid)
        return None

    async with httpx.AsyncClient() as client:
        r = await client.post(TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type":    "refresh_token",
        })

    if r.status_code != 200:
        logger.error("Error refrescando token uid=%s: %s", uid, r.text)
        return None

    new_data = r.json()
    new_data["refresh_token"] = refresh_token  # Google no siempre lo devuelve
    new_data["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=new_data.get("expires_in", 3600))
    ).isoformat()

    upsert_usuario(uid, google_fit_token=json.dumps(new_data))
    return new_data


# ══════════════════════════════════════════════════════════════════════════════
# LECTURA DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

def _nanos(dt: datetime) -> int:
    """Convierte datetime a nanosegundos (formato Google Fit)."""
    return int(dt.timestamp() * 1_000_000_000)


def _millis(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


async def fetch_actividad_dia(uid: int, fecha: date = None) -> dict | None:
    """
    Obtiene pasos, calorías, minutos de actividad y distancia de Google Fit
    para una fecha dada (default: ayer).
    """
    if fecha is None:
        fecha = date.today() - timedelta(days=1)

    access_token = await _get_access_token(uid)
    if not access_token:
        logger.warning("Sin token Google Fit para uid=%s", uid)
        return None

    inicio = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc)
    fin    = datetime.combine(fecha, datetime.max.time(), tzinfo=timezone.utc)

    headers = {"Authorization": f"Bearer {access_token}"}

    # Dataset aggregado — una sola llamada para múltiples métricas
    body = {
        "aggregateBy": [
            {"dataTypeName": "com.google.step_count.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.active_minutes"},
            {"dataTypeName": "com.google.distance.delta"},
        ],
        "bucketByTime": {"durationMillis": 86400000},  # 1 día
        "startTimeMillis": _millis(inicio),
        "endTimeMillis":   _millis(fin),
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{FITNESS_URL}/dataset:aggregate",
            headers=headers,
            json=body,
            timeout=15,
        )

    if r.status_code != 200:
        logger.error("Error Google Fit actividad uid=%s: %s", uid, r.status_code)
        return None

    data   = r.json()
    bucket = data.get("bucket", [{}])[0]

    resultado = {"fecha": str(fecha), "fuente": "google_fit"}

    for dataset in bucket.get("dataset", []):
        tipo  = dataset.get("dataSourceId","")
        punto = dataset.get("point", [])
        if not punto:
            continue
        valor = punto[0].get("value", [{}])[0]

        if "step_count" in tipo:
            resultado["pasos"] = int(valor.get("intVal", 0))
        elif "calories" in tipo:
            resultado["calorias_activas"] = int(valor.get("fpVal", 0))
        elif "active_minutes" in tipo:
            resultado["minutos_actividad"] = int(valor.get("intVal", 0))
        elif "distance" in tipo:
            resultado["distancia_km"] = round(float(valor.get("fpVal", 0)) / 1000, 2)

    return resultado


async def fetch_sueño_dia(uid: int, fecha: date = None) -> dict | None:
    """
    Obtiene datos de sueño de Google Fit para una fecha dada.
    El OnePlus Watch 4 sincroniza sueño a Health Connect → Google Fit.
    """
    if fecha is None:
        fecha = date.today() - timedelta(days=1)

    access_token = await _get_access_token(uid)
    if not access_token:
        return None

    # Sueño: buscar desde las 6pm del día anterior hasta las 12pm del día
    inicio = datetime.combine(fecha - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).replace(hour=18)
    fin    = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc).replace(hour=12)

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{FITNESS_URL}/sessions",
            headers=headers,
            params={
                "startTime": inicio.isoformat(),
                "endTime":   fin.isoformat(),
                "activityType": 72,  # 72 = sleep
            },
            timeout=15,
        )

    if r.status_code != 200:
        logger.warning("Error sueño Google Fit uid=%s: %s", uid, r.status_code)
        return None

    sessions = r.json().get("session", [])
    if not sessions:
        return None

    # Obtener detalle de etapas de sueño
    total_min     = 0
    profundo_min  = 0
    rem_min       = 0
    ligero_min    = 0

    for session in sessions:
        dur_ms = int(session.get("endTimeMillis",0)) - int(session.get("startTimeMillis",0))
        total_min += dur_ms // 60000

    # Para etapas necesitamos el dataset de sleep stages
    # com.google.sleep.segment
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.sleep.segment"}],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": _millis(inicio),
        "endTimeMillis":   _millis(fin),
    }

    async with httpx.AsyncClient() as client:
        r2 = await client.post(
            f"{FITNESS_URL}/dataset:aggregate",
            headers=headers,
            json=body,
            timeout=15,
        )

    if r2.status_code == 200:
        for bucket in r2.json().get("bucket", []):
            for dataset in bucket.get("dataset", []):
                for punto in dataset.get("point", []):
                    dur   = (int(punto.get("endTimeNanos",0)) - int(punto.get("startTimeNanos",0))) // 60_000_000_000
                    stage = punto.get("value",[{}])[0].get("intVal", 0)
                    # Stages: 1=awake, 2=sleep, 3=out-of-bed, 4=light, 5=deep, 6=REM
                    if stage == 5:
                        profundo_min += dur
                    elif stage == 6:
                        rem_min += dur
                    elif stage == 4:
                        ligero_min += dur

    return {
        "fecha":              str(fecha),
        "sueño_total_min":    total_min,
        "sueño_profundo_min": profundo_min,
        "sueño_rem_min":      rem_min,
        "sueño_ligero_min":   ligero_min,
        "fuente":             "google_fit",
    }


async def fetch_hrv_fc(uid: int, fecha: date = None) -> dict:
    """
    Frecuencia cardíaca en reposo y HRV del OnePlus Watch 4.
    El OnePlus sincroniza FC a Google Fit vía Health Connect.
    HRV solo disponible si el reloj lo soporta.
    """
    if fecha is None:
        fecha = date.today() - timedelta(days=1)

    access_token = await _get_access_token(uid)
    if not access_token:
        return {}

    inicio = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc)
    fin    = datetime.combine(fecha, datetime.max.time(), tzinfo=timezone.utc)
    headers = {"Authorization": f"Bearer {access_token}"}

    body = {
        "aggregateBy": [
            {"dataTypeName": "com.google.heart_rate.bpm"},
        ],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": _millis(inicio),
        "endTimeMillis":   _millis(fin),
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{FITNESS_URL}/dataset:aggregate",
            headers=headers,
            json=body,
            timeout=15,
        )

    resultado = {}
    if r.status_code == 200:
        for bucket in r.json().get("bucket", []):
            for dataset in bucket.get("dataset", []):
                for punto in dataset.get("point", []):
                    vals = punto.get("value", [])
                    if len(vals) >= 2:
                        resultado["fc_reposo"] = int(vals[1].get("fpVal", 0))  # min HR ≈ resting

    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# SYNC DIARIO — llamar cada mañana desde el scheduler
# ══════════════════════════════════════════════════════════════════════════════

async def sync_usuario(uid: int, fecha: date = None) -> dict:
    """
    Sincroniza todos los datos de Google Fit para un usuario.
    Llamar una vez por día, a las 6am.
    """
    if fecha is None:
        fecha = date.today() - timedelta(days=1)

    logger.info("Syncing Google Fit uid=%s fecha=%s", uid, fecha)

    datos = {"fecha": str(fecha), "fuente": "google_fit"}

    # Actividad
    actividad = await fetch_actividad_dia(uid, fecha)
    if actividad:
        datos.update(actividad)

    # Sueño
    sueño = await fetch_sueño_dia(uid, fecha)
    if sueño:
        datos.update(sueño)

    # FC y HRV
    hrv_fc = await fetch_hrv_fc(uid, fecha)
    if hrv_fc:
        datos.update(hrv_fc)

    # Guardar en DB
    save_actividad(uid, str(fecha), datos)
    logger.info("Sync OK uid=%s: pasos=%s, sueño=%smin, FC=%s",
                uid, datos.get("pasos"), datos.get("sueño_total_min"), datos.get("fc_reposo"))

    return datos


def esta_conectado(uid: int) -> bool:
    """Verifica si el usuario tiene Google Fit conectado."""
    usuario = get_usuario(uid)
    if not usuario:
        return False
    token = usuario.get("google_fit_token")
    if not token:
        return False
    try:
        data = json.loads(token)
        return bool(data.get("refresh_token"))
    except Exception:
        return False
