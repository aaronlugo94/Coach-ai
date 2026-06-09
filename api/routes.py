"""
api/routes.py — Todos los endpoints que la web necesita.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from db.database import (
    get_usuario, upsert_usuario, get_allowed_users, add_allowed_user,
    get_estado, get_ejercicios_dia, get_peso_sugerido, get_ultimo_pesaje,
    get_pesajes_recientes, get_actividad_semana, get_analisis_historial,
    calcular_ajuste_calorico, necesita_refeed, insert_plan, set_estado,
    save_sesion, verify_login_token, create_login_token, fetchall
)
from engine.gym.planner import generar_plan
from engine.nutrition.macros import calcular_macros_dia
import gamification

logger  = logging.getLogger(__name__)
router  = APIRouter()
WEB_URL = os.environ.get("FRONTEND_URL", "https://coach-ai.vercel.app")


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_uid(authorization: str = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sin token")
    token = authorization.split(" ")[1]
    uid = verify_login_token(token)
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return uid


# ── Auth endpoints ────────────────────────────────────────────────────────────

class EmailLogin(BaseModel):
    email: str

@router.post("/auth/email")
async def login_email(body: EmailLogin):
    """
    Login con email — busca usuario por email y manda link.
    Si no existe, lo crea como pendiente de onboarding.
    """
    rows = fetchall("SELECT user_id FROM usuarios WHERE email=?", (body.email,))
    if not rows:
        raise HTTPException(status_code=404, detail="Email no registrado. Usa /login en Telegram primero.")
    uid   = rows[0]["user_id"]
    token = create_login_token(uid)
    url   = f"{WEB_URL}/login?token={token}"
    # En producción enviarías el email aquí
    # Por ahora retornamos el token para debug
    logger.info("Email login uid=%s url=%s", uid, url)
    return {"message": "Link enviado", "debug_url": url}


# ── User endpoints ────────────────────────────────────────────────────────────

@router.get("/api/me")
def get_me(authorization: str = Header(None)):
    uid = get_uid(authorization)
    u   = get_usuario(uid)
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # No exponer contraseñas
    safe = {k: v for k, v in u.items() if k not in ("renpho_password", "google_fit_token")}
    safe["google_fit_conectado"] = bool(u.get("google_fit_token"))
    return safe


class UpdateMe(BaseModel):
    nombre:        Optional[str] = None
    email:         Optional[str] = None
    peso_kg:       Optional[float] = None
    altura_cm:     Optional[float] = None
    hora_reminder: Optional[str] = None

@router.put("/api/me")
def update_me(body: UpdateMe, authorization: str = Header(None)):
    uid = get_uid(authorization)
    kw  = {k: v for k, v in body.dict().items() if v is not None}
    if kw:
        upsert_usuario(uid, **kw)
    return get_usuario(uid)


# ── Onboarding ────────────────────────────────────────────────────────────────

class OnboardingData(BaseModel):
    nombre:        Optional[str] = None
    email:         Optional[str] = None
    fecha_nac:     Optional[str] = None
    sexo:          Optional[str] = None
    peso_kg:       Optional[float] = None
    altura_cm:     Optional[float] = None
    objetivo_vida: Optional[str] = None
    nivel:         Optional[str] = None
    ambiente:      Optional[str] = None
    dias_semana:   Optional[int] = 4
    limitaciones:  Optional[str] = "ninguna"
    hora_reminder: Optional[str] = None
    tipo_dieta:    Optional[str] = "omnivoro"
    patron_comidas:Optional[str] = "3"
    ventana_ayuno: Optional[str] = None
    donde_come:    Optional[str] = "casa"
    cocina:        Optional[str] = "variada"
    alergias:      Optional[str] = "ninguna"
    suplementos:   Optional[str] = "ninguno"
    alcohol:       Optional[str] = "no"
    agua_litros:   Optional[float] = 2.0

@router.post("/api/onboarding")
def save_onboarding(body: OnboardingData, authorization: str = Header(None)):
    uid = get_uid(authorization)

    # Calcular BMR
    kw = body.dict(exclude_none=True)
    if kw.get("peso_kg") and kw.get("altura_cm"):
        peso    = float(kw["peso_kg"])
        altura  = float(kw["altura_cm"])
        sexo    = kw.get("sexo","hombre")
        edad    = 30
        if kw.get("fecha_nac"):
            try:
                edad = int((date.today() - date.fromisoformat(kw["fecha_nac"])).days / 365.25)
            except Exception:
                pass
        if sexo == "mujer":
            bmr = round(10*peso + 6.25*altura - 5*edad - 161)
        else:
            bmr = round(10*peso + 6.25*altura - 5*edad + 5)
        tdee = round(bmr * 1.375)
        kw["bmr"]  = bmr
        kw["tdee"] = tdee
        kw["edad"] = edad

    # Mapear objetivo_vida → objetivo_gym
    OBJ_MAP = {
        "bajar_grasa":   "peso",
        "ganar_musculo": "mamado",
        "recomposicion": "general",
        "gluteo_pierna": "gluteo",
        "salud":         "general",
        "competitivo":   "mamado",
    }
    if kw.get("objetivo_vida"):
        kw["objetivo_gym"] = OBJ_MAP.get(kw["objetivo_vida"], "general")

    kw["onboarding_done"] = 1

    upsert_usuario(uid, **kw)
    add_allowed_user(uid)

    usuario = get_usuario(uid)
    return {"usuario": usuario, "message": "Perfil guardado"}


@router.post("/api/plan/generar")
def gen_plan(authorization: str = Header(None)):
    uid = get_uid(authorization)
    u   = get_usuario(uid)
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    try:
        plan = generar_plan(
            nivel      = u.get("nivel","intermedio"),
            objetivo   = u.get("objetivo_gym","general"),
            dias       = int(u.get("dias_semana") or 4),
            ambiente   = u.get("ambiente","gym"),
            limitacion = u.get("limitaciones","ninguna"),
        )
        n = insert_plan(uid, plan)
        set_estado(uid, plan[0]["semana"], plan[0]["dias"][0]["dia"])
        return {"ejercicios": n, "semanas": 4, "message": "Plan creado"}
    except Exception as e:
        logger.error("Error generando plan uid=%s: %s", uid, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Gym endpoints ─────────────────────────────────────────────────────────────

@router.get("/api/hoy")
def get_hoy(authorization: str = Header(None)):
    uid = get_uid(authorization)
    semana, dia = get_estado(uid)
    ejs = get_ejercicios_dia(uid, semana, dia)
    grupo = ejs[0]["grupo"] if ejs else ""

    # Agregar peso sugerido a cada ejercicio
    for e in ejs:
        sug = get_peso_sugerido(uid, e["ejercicio_id"], e.get("reps","8-10"), e.get("patron",""))
        e["peso_sugerido"] = sug

    racha = gamification.get_racha(uid)

    # Días completados esta semana
    completados = [
        r["dia_idx"] for r in fetchall(
            "SELECT CASE dia WHEN 'lunes' THEN 0 WHEN 'martes' THEN 1 WHEN 'miercoles' THEN 2 "
            "WHEN 'jueves' THEN 3 WHEN 'viernes' THEN 4 WHEN 'sabado' THEN 5 WHEN 'domingo' THEN 6 END as dia_idx "
            "FROM sesiones WHERE user_id=? AND completada=1 AND fecha>=date('now','-7 days')",
            (uid,)
        )
    ]

    return {
        "semana":     semana,
        "dia":        dia,
        "grupo":      grupo,
        "ejercicios": ejs,
        "racha":      racha,
        "dias_completados": completados,
    }


@router.get("/api/manana")
def get_manana(authorization: str = Header(None)):
    uid = get_uid(authorization)
    from db.database import avanzar_dia
    semana, dia = get_estado(uid)
    sem_man, dia_man = avanzar_dia(uid, semana, dia)
    ejs = get_ejercicios_dia(uid, sem_man, dia_man)
    grupo = ejs[0]["grupo"] if ejs else ""
    return {"semana": sem_man, "dia": dia_man, "grupo": grupo, "ejercicios": ejs}


# ── Nutrición endpoints ───────────────────────────────────────────────────────

@router.get("/api/macros/hoy")
def get_macros_hoy(authorization: str = Header(None)):
    uid = get_uid(authorization)
    semana, dia = get_estado(uid)
    ejs = get_ejercicios_dia(uid, semana, dia)
    es_gym = bool(ejs)
    return calcular_macros_dia(uid, es_gym=es_gym)


@router.get("/api/nutricion")
def get_nutricion(authorization: str = Header(None)):
    uid = get_uid(authorization)
    from db.database import get_plan_nutricion_activo
    try:
        plan = get_plan_nutricion_activo(uid)
        if plan and plan.get("plan_json"):
            return json.loads(plan["plan_json"])
    except Exception:
        pass
    return {"dias": []}


# ── Cuerpo endpoints ──────────────────────────────────────────────────────────

@router.get("/api/pesajes")
def get_pesajes(n: int = 30, authorization: str = Header(None)):
    uid = get_uid(authorization)
    return get_pesajes_recientes(uid, n)


@router.get("/api/actividad")
def get_actividad(authorization: str = Header(None)):
    uid  = get_uid(authorization)
    rows = get_actividad_semana(uid, 1)
    return rows[0] if rows else {}


# ── Análisis ──────────────────────────────────────────────────────────────────

@router.get("/api/analisis")
def get_analisis(authorization: str = Header(None)):
    uid  = get_uid(authorization)
    rows = get_analisis_historial(uid, 1)
    return rows[0] if rows else {}


# ── Progreso ──────────────────────────────────────────────────────────────────

@router.get("/api/progreso")
def get_progreso(authorization: str = Header(None)):
    uid = get_uid(authorization)
    from db.database import fetchall as fa
    rows = fa("""
        SELECT p.ejercicio_id, r.ejercicio,
               MAX(p.peso_lbs) as peso_actual,
               MIN(p.peso_lbs) as peso_inicio,
               MAX(p.peso_lbs) - MIN(p.peso_lbs) as cambio,
               MAX(p.peso_lbs) as peso_max
        FROM pesos p
        JOIN rutinas r ON p.ejercicio_id = r.ejercicio_id AND r.user_id = p.user_id
        WHERE p.user_id=?
        GROUP BY p.ejercicio_id
        ORDER BY cambio DESC
        LIMIT 10
    """, (uid,))
    return {"ejercicios": rows}


@router.get("/api/resumen/semanal")
def get_resumen_semanal(authorization: str = Header(None)):
    uid = get_uid(authorization)
    from db.database import fetchone as fo, fetchall as fa

    semana, _ = get_estado(uid)
    racha = gamification.get_racha(uid)

    sesiones = fa(
        "SELECT COUNT(*) n FROM sesiones WHERE user_id=? AND completada=1 AND fecha>=date('now','-7 days')",
        (uid,)
    )
    completadas = sesiones[0]["n"] if sesiones else 0

    from db.database import get_ejercicios_dia as ged
    total_dias = fo(
        "SELECT COUNT(DISTINCT dia) n FROM rutinas WHERE user_id=? AND ciclo=(SELECT ciclo_actual FROM usuarios WHERE user_id=?)",
        (uid, uid)
    )
    total = total_dias["n"] if total_dias else 4

    pesajes = get_pesajes_recientes(uid, 14)
    cambio_peso = 0
    if len(pesajes) >= 2:
        cambio_peso = round(float(pesajes[0]["peso_kg"]) - float(pesajes[-1]["peso_kg"]), 2)

    analisis = get_analisis_historial(uid, 1)
    mensaje = analisis[0]["texto"] if analisis else ""

    return {
        "semana":               semana,
        "racha":                racha,
        "sesiones_completadas": completadas,
        "sesiones_total":       total,
        "cambio_peso":          cambio_peso,
        "cambio_grasa":         None,
        "mensaje":              mensaje,
    }


# ── Google Fit auth URL ───────────────────────────────────────────────────────

@router.get("/api/google-fit/auth-url")
def google_fit_auth_url(authorization: str = Header(None)):
    uid = get_uid(authorization)
    from engine.body.healthconnect import get_auth_url
    return {"url": get_auth_url(uid)}
