"""
engine/body/healthconnect.py — Invisible Coach v4.0 (Sesión 14b)

Integración con Google Fit (Fitness REST API v1).

FIX CRÍTICO: sync_usuario() antes solo traía pasos/calorías/minutos
activos. Sueño, HRV, FC reposo y peso NUNCA se traían — por eso el
dashboard mostraba "Sueño 0h" y los anillos en 0 aunque Google Fit
estuviera conectado.

Ahora sync_usuario():
  1. Pasos / calorías / minutos activos (igual que antes)
  2. Sueño total + etapas (profundo/REM/ligero) vía Sessions API
  3. HRV promedio (si el dispositivo lo expone)
  4. FC en reposo (mínimo de FC del día)
  5. Peso (si el usuario se pesó con una báscula conectada a Fit)
     → auto-actualiza usuarios.peso_kg, sin preguntar de nuevo
  6. Calcula zona_fc_predominante (Karvonen) y rer_estimado
  7. Llama actualizar_baseline_hrv() y actualizar_bannister()

Cada fetch está aislado en try/except — si un tipo de dato no está
disponible para el dispositivo del usuario (p.ej. HRV no soportado),
esa pieza queda en None y el resto del sync continúa normal.
"""
from __future__ import annotations
import json, logging, os
from datetime import date, datetime, timedelta, timezone
import httpx
from db.database import (get_usuario, save_actividad, upsert_usuario,
                          actualizar_baseline_hrv, actualizar_bannister)

logger = logging.getLogger(__name__)
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID","")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET","")
REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI","")
SCOPES = " ".join([
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.body.read",
])
FITNESS_URL = "https://www.googleapis.com/fitness/v1/users/me"
TOKEN_URL   = "https://oauth2.googleapis.com/token"

# Segmentos de sueño según Google Fit (com.google.sleep.segment)
SLEEP_LIGERO = {4}
SLEEP_PROFUNDO = {5}
SLEEP_REM = {6}
SLEEP_ALL = {1,2,3,4,5,6}

# RER estimado por zona de FC (Karvonen) — para distribución de carbos/grasas
RER_POR_ZONA = {1: 0.72, 2: 0.78, 3: 0.85, 4: 0.92, 5: 1.00}


def get_auth_url(uid: int) -> str:
    import urllib.parse
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": SCOPES,
        "access_type": "offline", "prompt": "consent", "state": str(uid),
    })


async def exchange_code(code: str, uid: int) -> bool:
    async with httpx.AsyncClient() as c:
        r = await c.post(TOKEN_URL, data={
            "code": code, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
        })
    if r.status_code != 200:
        logger.error("OAuth error uid=%s: %s", uid, r.text)
        return False
    data = r.json()
    data["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in",3600))).isoformat()
    upsert_usuario(uid, google_fit_token=json.dumps(data))

    # Sync historico inmediato — ultimos 30 dias de actividad + pesajes
    try:
        for i in range(30):
            fecha = date.today() - timedelta(days=i)
            await sync_usuario(uid, fecha)
    except Exception as e:
        logger.warning("Sync historico inicial parcial uid=%s: %s", uid, e)

    return True


async def _access_token(uid: int) -> str | None:
    u = get_usuario(uid)
    if not u or not u.get("google_fit_token"): return None
    data = json.loads(u["google_fit_token"])
    exp = datetime.fromisoformat(data.get("expires_at","2000-01-01T00:00:00+00:00"))
    if datetime.now(timezone.utc) >= exp - timedelta(minutes=5):
        async with httpx.AsyncClient() as c:
            r = await c.post(TOKEN_URL, data={
                "refresh_token": data["refresh_token"], "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET, "grant_type": "refresh_token",
            })
        if r.status_code != 200: return None
        new = r.json()
        new["refresh_token"] = data["refresh_token"]
        new["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=new.get("expires_in",3600))).isoformat()
        upsert_usuario(uid, google_fit_token=json.dumps(new))
        data = new
    return data.get("access_token")


def _ms(dt): return int(dt.timestamp()*1000)
def _ns(dt): return int(dt.timestamp()*1_000_000_000)


# ══════════════════════════════════════════════════════════════════════════════
# FETCHERS — cada uno aislado, retorna {} si el dato no está disponible
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_actividad(c, headers, inicio, fin) -> dict:
    """Pasos, calorías, minutos activos."""
    body = {
        "aggregateBy": [
            {"dataTypeName": "com.google.step_count.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.active_minutes"},
        ],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": _ms(inicio), "endTimeMillis": _ms(fin),
    }
    out = {}
    try:
        r = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body, timeout=15)
        if r.status_code == 200:
            for bucket in r.json().get("bucket", []):
                for ds in bucket.get("dataset", []):
                    pts = ds.get("point", [])
                    if not pts: continue
                    v = pts[0].get("value", [{}])[0]
                    tipo = ds.get("dataSourceId","")
                    if "step_count" in tipo: out["pasos"] = int(v.get("intVal",0))
                    elif "calories" in tipo: out["calorias_activas"] = int(v.get("fpVal",0))
                    elif "active_minutes" in tipo: out["minutos_actividad"] = int(v.get("intVal",0))
    except Exception as e:
        logger.warning("Fit actividad fetch falló: %s", e)
    return out


async def _fetch_heart_rate(c, headers, inicio, fin) -> dict:
    """FC promedio y FC en reposo (mínimo del día)."""
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.heart_rate.bpm"}],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": _ms(inicio), "endTimeMillis": _ms(fin),
    }
    out = {}
    try:
        r = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body, timeout=15)
        if r.status_code == 200:
            for bucket in r.json().get("bucket", []):
                for ds in bucket.get("dataset", []):
                    for pt in ds.get("point", []):
                        # El summary de heart_rate.bpm trae mapVal con
                        # average/min/max, o fpVal simple según dispositivo
                        for v in pt.get("value", []):
                            mv = v.get("mapVal")
                            if mv:
                                for kv in mv:
                                    if kv.get("key") == "average":
                                        out["fc_promedio"] = round(kv["value"].get("fpVal",0))
                                    elif kv.get("key") == "min":
                                        out["fc_reposo"] = round(kv["value"].get("fpVal",0))
                            elif "fpVal" in v:
                                # Punto simple — usar como ambos si no hay summary
                                val = round(v["fpVal"])
                                out.setdefault("fc_promedio", val)
                                out["fc_reposo"] = min(out.get("fc_reposo", val), val)
    except Exception as e:
        logger.warning("Fit heart_rate fetch falló: %s", e)
    return out


async def _fetch_hrv(c, headers, inicio, fin) -> dict:
    """HRV promedio (rMSSD) — no todos los dispositivos lo exponen."""
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.heart_rate.variability.rmssd"}],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": _ms(inicio), "endTimeMillis": _ms(fin),
    }
    out = {}
    try:
        r = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body, timeout=15)
        if r.status_code == 200:
            for bucket in r.json().get("bucket", []):
                for ds in bucket.get("dataset", []):
                    pts = ds.get("point", [])
                    if not pts: continue
                    v = pts[0].get("value", [{}])[0]
                    fpval = v.get("fpVal")
                    if fpval:
                        out["hrv_promedio"] = round(fpval, 1)
    except Exception as e:
        logger.debug("Fit HRV no disponible: %s", e)
    return out


async def _fetch_peso(c, headers, inicio, fin) -> dict:
    """Último peso registrado en Fit (báscula conectada)."""
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.weight"}],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": _ms(inicio), "endTimeMillis": _ms(fin),
    }
    out = {}
    try:
        r = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body, timeout=15)
        if r.status_code == 200:
            for bucket in r.json().get("bucket", []):
                for ds in bucket.get("dataset", []):
                    pts = ds.get("point", [])
                    if not pts: continue
                    v = pts[-1].get("value", [{}])[0]  # más reciente
                    fpval = v.get("fpVal")
                    if fpval:
                        out["peso_kg"] = round(fpval, 1)
    except Exception as e:
        logger.debug("Fit peso no disponible: %s", e)
    return out


async def _fetch_sueño(c, headers, inicio, fin) -> dict:
    """
    Sueño total + etapas, vía Sessions API.
    Busca sesiones de sueño (activityType=72) que terminen en la ventana.
    """
    out = {}
    try:
        params = {
            "startTime": inicio.isoformat(),
            "endTime":   fin.isoformat(),
            "activityType": 72,  # sleep
        }
        r = await c.get(f"{FITNESS_URL}/sessions", headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return out
        sesiones = r.json().get("session", [])
        if not sesiones:
            return out

        # Sesión más larga del día = sueño principal de la noche
        sesion = max(sesiones, key=lambda s: int(s.get("endTimeMillis",0)) - int(s.get("startTimeMillis",0)))
        start_ms, end_ms = int(sesion["startTimeMillis"]), int(sesion["endTimeMillis"])
        total_min = round((end_ms - start_ms) / 60000)
        out["sueño_total_min"] = total_min

        # Etapas — dataset de sleep.segment para la ventana de la sesión
        ds_id = "derived:com.google.sleep.segment:com.google.android.gms:merged"
        start_ns, end_ns = start_ms * 1_000_000, end_ms * 1_000_000
        rds = await c.get(
            f"{FITNESS_URL}/dataSources/{ds_id}/datasets/{start_ns}-{end_ns}",
            headers=headers, timeout=15,
        )
        if rds.status_code == 200:
            profundo = rem = ligero = 0
            for pt in rds.json().get("point", []):
                tipo = pt.get("value", [{}])[0].get("intVal")
                dur_min = (int(pt["endTimeNanos"]) - int(pt["startTimeNanos"])) / 60_000_000_000
                if tipo in SLEEP_PROFUNDO: profundo += dur_min
                elif tipo in SLEEP_REM:    rem += dur_min
                elif tipo in SLEEP_LIGERO: ligero += dur_min
            if profundo or rem or ligero:
                out["sueño_profundo_min"] = round(profundo)
                out["sueño_rem_min"]      = round(rem)
                out["sueño_ligero_min"]   = round(ligero)
    except Exception as e:
        logger.warning("Fit sueño fetch falló: %s", e)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# ZONA FC / RER — derivados de FC promedio + baseline de reposo
# ══════════════════════════════════════════════════════════════════════════════

def _calcular_zona_y_rer(fc_promedio: float | None, fc_reposo: float | None, edad: int) -> dict:
    """Karvonen: %HRR = (FC - FCreposo) / (FCmax - FCreposo)."""
    if not fc_promedio or not fc_reposo:
        return {}
    fc_max = 220 - edad
    if fc_max <= fc_reposo:
        return {}
    pct_hrr = (fc_promedio - fc_reposo) / (fc_max - fc_reposo) * 100

    if pct_hrr < 60:   zona = 1
    elif pct_hrr < 70: zona = 2
    elif pct_hrr < 80: zona = 3
    elif pct_hrr < 90: zona = 4
    else:              zona = 5

    return {
        "zona_fc_predominante": zona,
        "rer_estimado": RER_POR_ZONA.get(zona, 0.80),
    }


# ══════════════════════════════════════════════════════════════════════════════
# SYNC PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

async def sync_usuario(uid: int, fecha: date = None) -> dict:
    if fecha is None: fecha = date.today() - timedelta(days=1)
    token = await _access_token(uid)
    if not token: return {}

    inicio = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc)
    fin    = datetime.combine(fecha, datetime.max.time(), tzinfo=timezone.utc)
    headers = {"Authorization": f"Bearer {token}"}

    datos = {"fecha": str(fecha), "fuente": "google_fit"}

    async with httpx.AsyncClient() as c:
        datos.update(await _fetch_actividad(c, headers, inicio, fin))

        hr = await _fetch_heart_rate(c, headers, inicio, fin)
        if "fc_reposo" in hr: datos["fc_reposo"] = hr["fc_reposo"]

        hrv = await _fetch_hrv(c, headers, inicio, fin)
        datos.update(hrv)

        sueño = await _fetch_sueño(c, headers, inicio, fin)
        datos.update(sueño)

        peso = await _fetch_peso(c, headers, inicio, fin)

    # Zona FC / RER (necesita edad del usuario)
    u = get_usuario(uid) or {}
    edad = int(u.get("edad") or 30)
    fc_avg = hr.get("fc_promedio")
    datos.update(_calcular_zona_y_rer(fc_avg, datos.get("fc_reposo"), edad))

    save_actividad(uid, str(fecha), datos)

    # Auto-actualizar peso si la báscula lo reportó a Fit — sin preguntar
    if peso.get("peso_kg"):
        peso_anterior = float(u.get("peso_kg") or 0)
        nuevo = peso["peso_kg"]
        if abs(nuevo - peso_anterior) > 0.05:  # evitar updates ruidosos idénticos
            upsert_usuario(uid, peso_kg=nuevo)
            logger.info("Peso auto-actualizado desde Fit uid=%s: %.1fkg", uid, nuevo)

    # Recalibrar baseline HRV/RHR y modelo Bannister con el dato fresco
    try:
        actualizar_baseline_hrv(uid)
        actualizar_bannister(uid)
    except Exception as e:
        logger.error("Error actualizando Bannister tras sync uid=%s: %s", uid, e)

    return datos


def esta_conectado(uid: int) -> bool:
    u = get_usuario(uid)
    if not u or not u.get("google_fit_token"): return False
    try: return bool(json.loads(u["google_fit_token"]).get("refresh_token"))
    except Exception: return False
