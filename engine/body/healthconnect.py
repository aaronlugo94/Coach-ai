"""
engine/body/healthconnect.py — Invisible Coach v2.0

Google Fit REST API + Health Connect.
OnePlus Watch 4 → Health Connect → Google Fit → Coach AI

Responsabilidades:
  1. OAuth2: generar URL, intercambiar código, refrescar token
  2. Sync diario: pasos, calorías, sueño, HRV, FC reposo
  3. Estimación de zona cardíaca y RER (cociente respiratorio)
  4. Actualizar modelo Bannister después de cada sync
  5. Actualizar baseline HRV/RHR

Llamar sync_usuario() cada mañana a las 6am desde el scheduler.
"""
from __future__ import annotations
import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from db.database import (
    get_usuario, save_actividad, upsert_usuario,
    actualizar_bannister, actualizar_baseline_hrv,
)

logger = logging.getLogger(__name__)

CLIENT_ID    = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET= os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")

SCOPES = " ".join([
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.body.read",
])

FITNESS_URL = "https://www.googleapis.com/fitness/v1/users/me"
TOKEN_URL   = "https://oauth2.googleapis.com/token"


# ══════════════════════════════════════════════════════════════════════════════
# OAUTH2
# ══════════════════════════════════════════════════════════════════════════════

def get_auth_url(uid: int) -> str:
    import urllib.parse
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         str(uid),
    })


async def exchange_code(code: str, uid: int) -> bool:
    """Intercambia el código OAuth2 por tokens. Guarda en DB."""
    async with httpx.AsyncClient() as c:
        r = await c.post(TOKEN_URL, data={
            "code":          code,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
    if r.status_code != 200:
        logger.error("OAuth exchange error uid=%s: %s", uid, r.text)
        return False
    data = r.json()
    data["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
    ).isoformat()
    upsert_usuario(uid, google_fit_token=json.dumps(data))
    logger.info("Google Fit conectado uid=%s", uid)
    return True


async def _get_access_token(uid: int) -> str | None:
    """Retorna un access_token válido. Refresca si expiró."""
    u = get_usuario(uid)
    if not u or not u.get("google_fit_token"):
        return None
    data = json.loads(u["google_fit_token"])
    exp  = datetime.fromisoformat(data.get("expires_at", "2000-01-01T00:00:00+00:00"))

    if datetime.now(timezone.utc) >= exp - timedelta(minutes=5):
        refreshed = await _refresh_token(uid, data)
        if not refreshed:
            return None
        data = refreshed

    return data.get("access_token")


async def _refresh_token(uid: int, token_data: dict) -> dict | None:
    refresh = token_data.get("refresh_token")
    if not refresh:
        logger.error("Sin refresh_token uid=%s", uid)
        return None
    async with httpx.AsyncClient() as c:
        r = await c.post(TOKEN_URL, data={
            "refresh_token": refresh,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type":    "refresh_token",
        })
    if r.status_code != 200:
        logger.error("Token refresh error uid=%s: %s", uid, r.status_code)
        return None
    new = r.json()
    new["refresh_token"] = refresh
    new["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=new.get("expires_in", 3600))
    ).isoformat()
    upsert_usuario(uid, google_fit_token=json.dumps(new))
    return new


def esta_conectado(uid: int) -> bool:
    u = get_usuario(uid)
    if not u or not u.get("google_fit_token"):
        return False
    try:
        return bool(json.loads(u["google_fit_token"]).get("refresh_token"))
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)

def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


# ══════════════════════════════════════════════════════════════════════════════
# FETCH ACTIVIDAD (pasos, calorías, minutos)
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_actividad(token: str, inicio: datetime, fin: datetime) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "aggregateBy": [
            {"dataTypeName": "com.google.step_count.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.active_minutes"},
            {"dataTypeName": "com.google.distance.delta"},
        ],
        "bucketByTime":  {"durationMillis": 86_400_000},
        "startTimeMillis": _ms(inicio),
        "endTimeMillis":   _ms(fin),
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body)

    if r.status_code != 200:
        logger.warning("Actividad fetch error: %s", r.status_code)
        return {}

    resultado = {}
    bucket = r.json().get("bucket", [{}])[0]
    for ds in bucket.get("dataset", []):
        pts  = ds.get("point", [])
        if not pts: continue
        val  = pts[0].get("value", [{}])[0]
        tipo = ds.get("dataSourceId", "")
        if "step_count"     in tipo: resultado["pasos"]             = int(val.get("intVal", 0))
        elif "calories"     in tipo: resultado["calorias_activas"]  = int(val.get("fpVal", 0))
        elif "active_minutes"in tipo: resultado["minutos_actividad"] = int(val.get("intVal", 0))
        elif "distance"     in tipo: resultado["distancia_km"]      = round(float(val.get("fpVal", 0)) / 1000, 2)

    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# FETCH SUEÑO
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_sueño(token: str, inicio: datetime, fin: datetime) -> dict:
    headers = {"Authorization": f"Bearer {token}"}

    # Sesiones de sueño
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{FITNESS_URL}/sessions", headers=headers, params={
            "startTime":    inicio.isoformat(),
            "endTime":      fin.isoformat(),
            "activityType": 72,  # sleep
        })

    total_min = 0
    if r.status_code == 200:
        for s in r.json().get("session", []):
            dur_ms = int(s.get("endTimeMillis", 0)) - int(s.get("startTimeMillis", 0))
            total_min += dur_ms // 60_000

    # Etapas de sueño
    deep_min = rem_min = light_min = 0
    body = {
        "aggregateBy":   [{"dataTypeName": "com.google.sleep.segment"}],
        "bucketByTime":  {"durationMillis": 86_400_000},
        "startTimeMillis": _ms(inicio),
        "endTimeMillis":   _ms(fin),
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r2 = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body)

    if r2.status_code == 200:
        for bucket in r2.json().get("bucket", []):
            for ds in bucket.get("dataset", []):
                for pt in ds.get("point", []):
                    dur   = (int(pt.get("endTimeNanos", 0)) - int(pt.get("startTimeNanos", 0))) // 60_000_000_000
                    stage = pt.get("value", [{}])[0].get("intVal", 0)
                    # Google Fit sleep stages: 4=light, 5=deep, 6=REM
                    if   stage == 5: deep_min  += dur
                    elif stage == 6: rem_min   += dur
                    elif stage == 4: light_min += dur

    return {
        "sueño_total_min":    total_min,
        "sueño_profundo_min": deep_min,
        "sueño_rem_min":      rem_min,
        "sueño_ligero_min":   light_min,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FETCH FRECUENCIA CARDÍACA + HRV
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_fc_hrv(token: str, inicio: datetime, fin: datetime) -> dict:
    """
    Obtiene FC mínima (≈ FC reposo) y estima HRV desde variabilidad de BPM.
    El OnePlus Watch 4 sincroniza FC a Google Fit via Health Connect.
    """
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.heart_rate.bpm"}],
        "bucketByTime": {"durationMillis": 3_600_000},  # por hora para más datos
        "startTimeMillis": _ms(inicio),
        "endTimeMillis":   _ms(fin),
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body)

    if r.status_code != 200:
        return {}

    fc_vals = []
    for bucket in r.json().get("bucket", []):
        for ds in bucket.get("dataset", []):
            for pt in ds.get("point", []):
                vals = pt.get("value", [])
                # value[0]=avg, value[1]=min, value[2]=max
                if len(vals) >= 2:
                    fc_min = vals[1].get("fpVal", 0)
                    if fc_min > 30:  # filtrar ruido
                        fc_vals.append(fc_min)

    if not fc_vals:
        return {}

    fc_reposo = round(min(fc_vals))  # mínima del día ≈ FC reposo

    # Estimar HRV desde variabilidad de lecturas de FC
    # Proxy: HRV ≈ 1000/FC_reposo × factor_variabilidad
    # Más preciso que nada cuando el reloj no reporta HRV directamente
    if len(fc_vals) > 3:
        media = sum(fc_vals) / len(fc_vals)
        varianza = sum((x - media)**2 for x in fc_vals) / len(fc_vals)
        std = math.sqrt(varianza)
        # RMSSD proxy: HRV estimado en ms
        hrv_estimado = round((1000 / fc_reposo) * (1 + std / 10), 1)
        hrv_estimado = max(20, min(hrv_estimado, 120))  # rango fisiológico
    else:
        hrv_estimado = None

    return {
        "fc_reposo":    fc_reposo,
        "hrv_promedio": hrv_estimado,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ZONA CARDÍACA Y RER (Cociente Respiratorio)
# ══════════════════════════════════════════════════════════════════════════════

def _calcular_zona_fc(fc_media: float, edad: int) -> int:
    """
    Zona cardíaca según % de FCmáx (Karvonen).
    FCmáx estimada = 220 - edad
    """
    if not fc_media or not edad:
        return 1
    fc_max = 220 - edad
    pct    = (fc_media / fc_max) * 100
    if   pct < 50: return 1   # muy ligero
    elif pct < 60: return 2   # quema grasas (zona 2 - aeróbico base)
    elif pct < 70: return 3   # aeróbico moderado
    elif pct < 85: return 4   # umbral anaeróbico
    else:          return 5   # máximo / HIIT


def _calcular_rer(zona: int) -> float:
    """
    Estima el Cociente Respiratorio (RER) según zona cardíaca.
    RER ~0.7 = oxidación predominante de lípidos
    RER ~1.0 = oxidación predominante de glucosa

    Brooks & Fahey (1984), revisado McArdle (2015):
    Zona 1-2: lípidos dominan (RER 0.70-0.75)
    Zona 3:   mix 50/50 (RER 0.85)
    Zona 4-5: glucosa domina (RER 0.95-1.00)
    """
    tabla = {1: 0.70, 2: 0.75, 3: 0.85, 4: 0.95, 5: 1.00}
    return tabla.get(zona, 0.85)


def interpretar_rer(rer: float) -> dict:
    """
    Traduce el RER a recomendaciones de macros para esa noche.
    Usado por Gemini en el análisis nocturno.
    """
    if rer <= 0.75:
        return {
            "sustrato":     "lípidos",
            "carbos_noche": "bajos",
            "nota":         "Día de baja intensidad — prioriza grasas en cena, carbos mínimos",
        }
    elif rer <= 0.85:
        return {
            "sustrato":     "mixto",
            "carbos_noche": "moderados",
            "nota":         "Actividad moderada — distribución normal de macros",
        }
    else:
        return {
            "sustrato":     "glucosa",
            "carbos_noche": "altos",
            "nota":         "Alta intensidad — recarga carbos post-entreno y en cena",
        }


# ══════════════════════════════════════════════════════════════════════════════
# SYNC COMPLETO — llamar cada mañana a las 6am
# ══════════════════════════════════════════════════════════════════════════════

async def sync_usuario(uid: int, fecha: date = None) -> dict:
    """
    Sincroniza todos los datos de Google Fit para el usuario.
    Después del sync: actualiza baseline HRV y modelo Bannister.

    Flujo:
    1. Fetch actividad (pasos, calorías, minutos)
    2. Fetch sueño (total + etapas)
    3. Fetch FC (reposo + HRV estimado)
    4. Calcular zona cardíaca y RER
    5. Guardar en actividad_diaria
    6. Actualizar baseline HRV (promedio 30 días)
    7. Actualizar modelo Bannister
    """
    if fecha is None:
        fecha = date.today() - timedelta(days=1)

    token = await _get_access_token(uid)
    if not token:
        logger.warning("Sin token Google Fit uid=%s", uid)
        return {}

    # Ventana de tiempo: día completo en UTC
    inicio = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc)
    fin    = datetime.combine(fecha, datetime.max.time(), tzinfo=timezone.utc)

    logger.info("Google Fit sync uid=%s fecha=%s", uid, fecha)

    datos = {"fecha": str(fecha), "fuente": "google_fit"}

    # 1. Actividad
    act = await _fetch_actividad(token, inicio, fin)
    datos.update(act)

    # 2. Sueño (ventana amplia: 6pm del día anterior a 12pm del día)
    inicio_sueño = inicio - timedelta(hours=6)
    fin_sueño    = inicio + timedelta(hours=12)
    sueño = await _fetch_sueño(token, inicio_sueño, fin_sueño)
    datos.update(sueño)

    # 3. FC y HRV
    fc_hrv = await _fetch_fc_hrv(token, inicio, fin)
    datos.update(fc_hrv)

    # 4. Zona cardíaca y RER
    u = get_usuario(uid)
    if u and fc_hrv.get("fc_reposo"):
        edad = int(u.get("edad") or 30)
        # FC media del día para la zona (aproximamos con fc_reposo × 1.3 si no tenemos más)
        fc_media = fc_hrv["fc_reposo"] * 1.3
        zona = _calcular_zona_fc(fc_media, edad)
        rer  = _calcular_rer(zona)
        datos["zona_fc_predominante"] = zona
        datos["rer_estimado"]         = rer

    # 5. Guardar en DB
    save_actividad(uid, str(fecha), datos)

    # 6. Actualizar baseline HRV (cada sync)
    actualizar_baseline_hrv(uid)

    # 7. Actualizar modelo Bannister
    resultado_bannister = actualizar_bannister(uid, str(fecha))

    logger.info(
        "Sync OK uid=%s | pasos=%s sueño=%smin FC=%s HRV=%s | bannister=%s",
        uid,
        datos.get("pasos", 0),
        datos.get("sueño_total_min", 0),
        datos.get("fc_reposo"),
        datos.get("hrv_promedio"),
        resultado_bannister,
    )

    return {**datos, "bannister": resultado_bannister}


async def sync_all_users():
    """Sync Google Fit para todos los usuarios conectados. Llamar a las 6am."""
    from db.database import fetchall
    users = fetchall(
        "SELECT user_id FROM usuarios WHERE google_fit_token IS NOT NULL "
        "AND onboarding_done=1", ()
    )
    resultados = []
    for u in users:
        uid = u["user_id"]
        if esta_conectado(uid):
            try:
                res = await sync_usuario(uid)
                resultados.append({"uid": uid, "ok": True, "datos": res})
            except Exception as e:
                logger.error("Sync error uid=%s: %s", uid, e)
                resultados.append({"uid": uid, "ok": False, "error": str(e)})
    return resultados
