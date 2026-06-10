"""
api/routes.py — Invisible Coach v3.0
Todos los endpoints que la web necesita.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from db.database import (
    get_usuario, upsert_usuario, get_allowed_users, add_allowed_user,
    get_estado, get_ejercicios_dia, get_peso_sugerido, get_historial_peso,
    get_ultimo_pesaje, get_pesajes_recientes, get_actividad_dia,
    get_actividad_semana, get_analisis_historial, get_plan_nutricion_activo,
    calcular_ajuste_calorico, necesita_refeed, insert_plan, set_estado,
    save_sesion, verify_login_token, create_login_token, fetchall, fetchone,
    get_estado_bannister, get_ciclo, avanzar_dia,
)
from engine.gym.planner import generar_plan
from engine.nutrition.macros import calcular_macros_dia
import gamification

logger  = logging.getLogger(__name__)
router  = APIRouter()
WEB_URL = os.environ.get("FRONTEND_URL", "https://invisible-coach.vercel.app")

LABEL_SEMANA = {
    "principiante": {1:"MEV", 2:"MAV", 3:"MRV", 4:"Deload"},
    "intermedio":   {1:"MEV", 2:"MAV", 3:"MRV", 4:"Deload"},
    "avanzado":     {1:"MEV", 2:"MAV", 3:"MRV", 4:"Deload"},
}


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_uid(authorization: str = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sin token")
    token = authorization.split(" ")[1]
    # El token de sesión web nunca expira — solo verificamos que exista
    r = fetchone("SELECT user_id FROM login_tokens WHERE token=?", (token,))
    if not r:
        raise HTTPException(status_code=401, detail="Token no encontrado")
    return r["user_id"]


# ── Auth endpoints ────────────────────────────────────────────────────────────

class EmailLogin(BaseModel):
    email: str

@router.post("/auth/email")
async def login_email(body: EmailLogin):
    rows = fetchall("SELECT user_id FROM usuarios WHERE email=?", (body.email,))
    if not rows:
        raise HTTPException(status_code=404, detail="Email no registrado. Usa /login en Telegram.")
    uid   = rows[0]["user_id"]
    token = create_login_token(uid)
    url   = f"{WEB_URL}/login?token={token}"
    logger.info("Email login uid=%s", uid)
    # En producción enviar email real. Por ahora retornar URL para desarrollo.
    return {"message": "Link enviado", "url": url}


# ── User endpoints ────────────────────────────────────────────────────────────

@router.get("/api/me")
def get_me(authorization: str = Header(None)):
    uid = get_uid(authorization)
    u   = get_usuario(uid)
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    safe = {k: v for k, v in u.items() if k not in ("renpho_password",)}
    safe["google_fit_conectado"] = bool(u.get("google_fit_token"))
    safe["google_fit_token"] = bool(u.get("google_fit_token"))  # solo bool a la web
    return safe


class UpdateMe(BaseModel):
    nombre:         Optional[str]   = None
    email:          Optional[str]   = None
    peso_kg:        Optional[float] = None
    altura_cm:      Optional[float] = None
    hora_gym:       Optional[str]   = None
    hora_reminder:  Optional[str]   = None
    hora_checkin:   Optional[str]   = None

@router.put("/api/me")
def update_me(body: UpdateMe, authorization: str = Header(None)):
    uid = get_uid(authorization)
    kw  = {k: v for k, v in body.dict().items() if v is not None}
    if kw:
        upsert_usuario(uid, **kw)
    return get_me(authorization)


# ── Onboarding ────────────────────────────────────────────────────────────────

class OnboardingData(BaseModel):
    nombre:              Optional[str]   = None
    email:               Optional[str]   = None
    fecha_nac:           Optional[str]   = None
    sexo:                Optional[str]   = None
    peso_kg:             Optional[float] = None
    altura_cm:           Optional[float] = None
    objetivo_vida:       Optional[str]   = None
    nivel:               Optional[str]   = None
    ambiente:            Optional[str]   = None
    dias_semana:         Optional[int]   = 4
    duracion_sesion:     Optional[int]   = 60
    limitaciones:        Optional[str]   = "ninguna"
    hora_gym:            Optional[str]   = "17:00"
    hora_reminder:       Optional[str]   = None
    hora_checkin:        Optional[str]   = None
    tipo_dieta:          Optional[str]   = "omnivoro"
    proteinas_favoritas: Optional[str]   = None
    cocina:              Optional[str]   = "variada"
    alergias:            Optional[str]   = "ninguna"
    donde_come:          Optional[str]   = "casa"
    suplementos:         Optional[str]   = "ninguno"
    alcohol:             Optional[str]   = "no"
    sueño_horas:         Optional[float] = 7.5
    actividad_nivel:     Optional[str]   = "moderado"
    nivel_estres:        Optional[str]   = "moderado"
    wearable:            Optional[str]   = "ninguno"
    factor_estres:       Optional[float] = 1.0

@router.post("/api/onboarding")
def save_onboarding(body: OnboardingData, authorization: str = Header(None)):
    uid = get_uid(authorization)
    kw  = body.dict(exclude_none=True)

    # Calcular BMR/TDEE
    if kw.get("peso_kg") and kw.get("altura_cm"):
        peso   = float(kw["peso_kg"])
        altura = float(kw["altura_cm"])
        sexo   = kw.get("sexo","hombre")
        edad   = 30
        if kw.get("fecha_nac"):
            try:
                edad = int((date.today() - date.fromisoformat(kw["fecha_nac"])).days / 365.25)
                kw["edad"] = edad
            except Exception:
                pass
        bmr = round(10*peso + 6.25*altura - 5*edad + (5 if sexo=="hombre" else -161))
        FACT = {"sedentario":1.2,"moderado":1.375,"activo":1.55,"muy_activo":1.725}
        tdee = round(bmr * FACT.get(kw.get("actividad_nivel","moderado"), 1.375))
        kw["bmr"]  = bmr
        kw["tdee"] = tdee

    # Mapear objetivo_vida → objetivo_gym
    OBJ = {
        "recomposicion": "general",
        "deficit":       "peso",
        "volumen":       "mamado",
        "gluteo":        "gluteo",
        "salud":         "general",
    }
    if kw.get("objetivo_vida"):
        kw["objetivo_gym"] = OBJ.get(kw["objetivo_vida"], "general")

    # Calcular factor_estres si no viene
    FEST = {"bajo":1.0,"moderado":1.1,"alto":1.25,"muy_alto":1.4}
    if kw.get("nivel_estres") and "factor_estres" not in kw:
        kw["factor_estres"] = FEST.get(kw["nivel_estres"], 1.0)

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
        raise HTTPException(status_code=404)
    try:
        plan = generar_plan(
            nivel      = u.get("nivel","intermedio"),
            objetivo   = u.get("objetivo_gym","general"),
            dias       = int(u.get("dias_semana") or 4),
            ambiente   = u.get("ambiente","gym"),
            limitacion = u.get("limitaciones","ninguna"),
            duracion   = int(u.get("duracion_sesion") or 60),
        )
        n = insert_plan(uid, plan)
        set_estado(uid, plan[0]["semana"], plan[0]["dias"][0]["dia"])
        return {"ejercicios": n, "semanas": 4, "message": "Plan creado"}
    except Exception as e:
        logger.error("Error gen_plan uid=%s: %s", uid, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Gym endpoints ─────────────────────────────────────────────────────────────

@router.get("/api/hoy")
def get_hoy(authorization: str = Header(None)):
    uid = get_uid(authorization)
    semana, dia  = get_estado(uid)
    ejs          = get_ejercicios_dia(uid, semana, dia)
    ejs_fuerza   = [e for e in ejs if not e.get("es_cardio")]
    grupo        = ejs_fuerza[0]["grupo"] if ejs_fuerza else ""
    u            = get_usuario(uid)
    nivel        = u.get("nivel","intermedio") if u else "intermedio"
    bann         = get_estado_bannister(uid)
    racha        = gamification.get_racha(uid)

    # Agregar peso sugerido y flag de nuevo peso
    for e in ejs_fuerza:
        sug  = get_peso_sugerido(uid, e["ejercicio_id"], e.get("reps","8-10"), e.get("patron",""))
        e["peso_sugerido"] = sug
        e["es_nuevo_peso"] = False
        if sug:
            hist = get_historial_peso(uid, e["ejercicio_id"], 2)
            if len(hist) >= 2 and float(hist[0]["peso_lbs"]) > float(hist[1]["peso_lbs"]):
                e["es_nuevo_peso"] = True

    # Días completados esta semana (para la card de semana)
    inicio_semana = str(date.today() - timedelta(days=date.today().weekday()))
    completados_raw = fetchall("""
        SELECT CASE dia
            WHEN 'lunes'     THEN 0 WHEN 'martes'   THEN 1
            WHEN 'miercoles' THEN 2 WHEN 'jueves'   THEN 3
            WHEN 'viernes'   THEN 4 WHEN 'sabado'   THEN 5
            WHEN 'domingo'   THEN 6
        END as idx
        FROM sesiones
        WHERE user_id=? AND completada=1 AND fecha>=?
    """, (uid, inicio_semana))
    completados = [r["idx"] for r in completados_raw if r["idx"] is not None]

    # Días de gym de esta semana (para mostrar en la card)
    dias_gym_raw = fetchall("""
        SELECT DISTINCT CASE dia
            WHEN 'lunes'     THEN 0 WHEN 'martes'   THEN 1
            WHEN 'miercoles' THEN 2 WHEN 'jueves'   THEN 3
            WHEN 'viernes'   THEN 4 WHEN 'sabado'   THEN 5
            WHEN 'domingo'   THEN 6
        END as idx
        FROM rutinas WHERE user_id=? AND ciclo=? AND semana=?
    """, (uid, get_ciclo(uid), semana))
    dias_gym = [r["idx"] for r in dias_gym_raw if r["idx"] is not None]

    return {
        "semana":          semana,
        "dia":             dia,
        "grupo":           grupo,
        "ejercicios":      ejs_fuerza,
        "label":           LABEL_SEMANA.get(nivel,{}).get(semana,""),
        "racha":           racha,
        "snc_pct":         bann.get("snc_pct", 85),
        "rec_volumen":     bann.get("rec_volumen","normal"),
        "fatiga_snc":      bann.get("fatiga_snc", False),
        "dias_completados": completados,
        "dias_gym":        dias_gym,
    }


@router.get("/api/manana")
def get_manana(authorization: str = Header(None)):
    uid = get_uid(authorization)
    semana, dia  = get_estado(uid)
    sem_man, dia_man = avanzar_dia(uid, semana, dia)
    ejs = get_ejercicios_dia(uid, sem_man, dia_man)
    grupo = ejs[0]["grupo"] if ejs and not ejs[0].get("es_cardio") else ""
    return {"semana": sem_man, "dia": dia_man, "grupo": grupo, "ejercicios": ejs}


# ── Macros / Nutrición ────────────────────────────────────────────────────────

@router.get("/api/macros/hoy")
def get_macros_hoy(authorization: str = Header(None)):
    uid = get_uid(authorization)
    semana, dia = get_estado(uid)
    ejs = get_ejercicios_dia(uid, semana, dia)
    es_gym = bool([e for e in ejs if not e.get("es_cardio")])
    return calcular_macros_dia(uid, es_gym=es_gym)


@router.get("/api/nutricion")
def get_nutricion(authorization: str = Header(None)):
    uid = get_uid(authorization)
    try:
        plan = get_plan_nutricion_activo(uid)
        if plan and plan.get("plan_json"):
            return json.loads(plan["plan_json"])
    except Exception:
        pass
    return {"semana": {}}


# ── Cuerpo ────────────────────────────────────────────────────────────────────

@router.get("/api/pesajes")
def get_pesajes(n: int = 30, authorization: str = Header(None)):
    uid = get_uid(authorization)
    return get_pesajes_recientes(uid, n)


@router.get("/api/actividad")
def get_actividad(authorization: str = Header(None)):
    uid  = get_uid(authorization)
    # Intentar ayer primero, luego hoy
    ayer = str(date.today() - timedelta(days=1))
    activ = get_actividad_dia(uid, ayer)
    if not activ:
        activ = get_actividad_dia(uid, str(date.today()))
    return activ or {}


# ── Análisis Gemini ───────────────────────────────────────────────────────────

@router.get("/api/analisis")
def get_analisis(authorization: str = Header(None)):
    uid  = get_uid(authorization)
    rows = get_analisis_historial(uid, 1)
    return rows[0] if rows else {}


# ── Progreso ──────────────────────────────────────────────────────────────────

@router.get("/api/progreso")
def get_progreso(authorization: str = Header(None)):
    uid = get_uid(authorization)
    rows = fetchall("""
        SELECT p.ejercicio_id, r.ejercicio,
               MAX(p.peso_lbs) peso_actual,
               MIN(p.peso_lbs) peso_inicio,
               MAX(p.peso_lbs) - MIN(p.peso_lbs) cambio,
               MAX(p.peso_lbs) peso_max
        FROM pesos p
        JOIN rutinas r ON p.ejercicio_id=r.ejercicio_id AND r.user_id=p.user_id
        WHERE p.user_id=?
        GROUP BY p.ejercicio_id
        ORDER BY cambio DESC LIMIT 8
    """, (uid,))
    return {"ejercicios": rows}


@router.get("/api/resumen/semanal")
def get_resumen_semanal(authorization: str = Header(None)):
    uid = get_uid(authorization)
    semana, _ = get_estado(uid)
    racha     = gamification.get_racha(uid)
    u         = get_usuario(uid)
    nivel     = u.get("nivel","intermedio") if u else "intermedio"

    # Sesiones completadas esta semana
    inicio = str(date.today() - timedelta(days=date.today().weekday()))
    row    = fetchone(
        "SELECT COUNT(*) n FROM sesiones WHERE user_id=? AND completada=1 AND fecha>=?",
        (uid, inicio)
    )
    completadas = row["n"] if row else 0
    total_dias  = int(u.get("dias_semana") or 4) if u else 4

    # Cambio de peso semanal
    pesajes      = get_pesajes_recientes(uid, 14)
    cambio_peso  = 0
    cambio_grasa = None
    grasa_actual = None
    if len(pesajes) >= 2:
        cambio_peso = round(float(pesajes[0]["peso_kg"]) - float(pesajes[-1]["peso_kg"]), 2)
    if len(pesajes) >= 2 and pesajes[0].get("grasa_pct") and pesajes[-1].get("grasa_pct"):
        cambio_grasa = round(float(pesajes[0]["grasa_pct"]) - float(pesajes[-1]["grasa_pct"]), 1)
        grasa_actual = float(pesajes[0]["grasa_pct"])

    # Último análisis de Gemini como mensaje
    analisis = get_analisis_historial(uid, 1)
    mensaje  = analisis[0]["texto"][:200] if analisis else ""

    return {
        "semana":               semana,
        "label":                LABEL_SEMANA.get(nivel,{}).get(semana,""),
        "racha":                racha,
        "sesiones_completadas": completadas,
        "sesiones_total":       total_dias,
        "cambio_peso":          cambio_peso,
        "cambio_grasa":         cambio_grasa,
        "grasa_pct_actual":     grasa_actual,
        "mensaje":              mensaje,
    }


# ── Coach conversacional ──────────────────────────────────────────────────────

class CoachAsk(BaseModel):
    pregunta: str

@router.post("/api/coach/ask")
async def coach_ask(body: CoachAsk, authorization: str = Header(None)):
    uid = get_uid(authorization)
    if not body.pregunta.strip():
        raise HTTPException(status_code=400, detail="Pregunta vacía")
    try:
        from ai.coach import responder_pregunta
        respuesta = await responder_pregunta(uid, body.pregunta)
        return {"respuesta": respuesta}
    except Exception as e:
        logger.error("Coach ask uid=%s: %s", uid, e)
        return {"respuesta": "No pude procesar tu pregunta. Intenta de nuevo."}


# ── Google Fit ────────────────────────────────────────────────────────────────

@router.get("/api/google-fit/auth-url")
def google_fit_auth_url(authorization: str = Header(None)):
    uid = get_uid(authorization)
    from engine.body.healthconnect import get_auth_url
    return {"url": get_auth_url(uid)}
