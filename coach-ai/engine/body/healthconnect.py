from __future__ import annotations
import json, logging, os
from datetime import date, datetime, timedelta, timezone
import httpx
from db.database import get_usuario, save_actividad, upsert_usuario

logger = logging.getLogger(__name__)
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID","")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET","")
REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI","")
SCOPES = " ".join([
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
])
FITNESS_URL = "https://www.googleapis.com/fitness/v1/users/me"
TOKEN_URL   = "https://oauth2.googleapis.com/token"

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

async def sync_usuario(uid: int, fecha: date = None) -> dict:
    if fecha is None: fecha = date.today() - timedelta(days=1)
    token = await _access_token(uid)
    if not token: return {}
    inicio = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc)
    fin    = datetime.combine(fecha, datetime.max.time(), tzinfo=timezone.utc)
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "aggregateBy": [
            {"dataTypeName": "com.google.step_count.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.active_minutes"},
        ],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": _ms(inicio), "endTimeMillis": _ms(fin),
    }
    datos = {"fecha": str(fecha), "fuente": "google_fit"}
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{FITNESS_URL}/dataset:aggregate", headers=headers, json=body, timeout=15)
    if r.status_code == 200:
        bucket = r.json().get("bucket",[{}])[0]
        for ds in bucket.get("dataset",[]):
            pts = ds.get("point",[])
            if not pts: continue
            v = pts[0].get("value",[{}])[0]
            tipo = ds.get("dataSourceId","")
            if "step_count" in tipo: datos["pasos"] = int(v.get("intVal",0))
            elif "calories" in tipo: datos["calorias_activas"] = int(v.get("fpVal",0))
            elif "active_minutes" in tipo: datos["minutos_actividad"] = int(v.get("intVal",0))
    save_actividad(uid, str(fecha), datos)
    return datos

def esta_conectado(uid: int) -> bool:
    u = get_usuario(uid)
    if not u or not u.get("google_fit_token"): return False
    try: return bool(json.loads(u["google_fit_token"]).get("refresh_token"))
    except Exception: return False
