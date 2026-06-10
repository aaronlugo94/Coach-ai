"""
engine/nutrition/macros.py — Invisible Coach v3.0

Ciencia aplicada:
  - Mifflin-St Jeor para BMR (validado Frankenfield 2005)
  - TDEE × factor actividad real del usuario
  - Proteína: 2.2g/kg peso total (Phillips 2016)
  - Timing: 4 tomas × (proteína/4)g separadas 3-4h (Moore 2015)
  - Caseína nocturna: +40g antes de dormir (Snijders 2015)
  - SISO semanal: ajuste ±150-200 kcal según báscula
  - Refeed automático: 3+ semanas déficit (Dirlewanger 2000)
  - RER: ajusta distribución de carbos/grasas según zona cardíaca del día
  - Estrés alto: reduce déficit para proteger músculo (cortisol)
"""
from __future__ import annotations
import logging
from datetime import date
from db.database import (
    get_usuario, calcular_ajuste_calorico, necesita_refeed,
    get_actividad_dia,
)

logger = logging.getLogger(__name__)

# ── Factores de actividad (TDEE multipliers) ──────────────────────────────────
ACTIVIDAD_FACTOR = {
    "sedentario": 1.2,
    "moderado":   1.375,
    "activo":     1.55,
    "muy_activo": 1.725,
}

# ── Déficit/superávit calórico según objetivo ─────────────────────────────────
# Basado en tasa óptima de cambio corporal
# Déficit agresivo máximo: -25% TDEE (evitar catabolismo muscular)
OBJETIVO_MULT = {
    "peso":    0.82,   # déficit ~18% → -0.5%/semana peso corporal
    "mamado":  1.10,   # superávit ~10% → lean bulk +0.3%/semana
    "gluteo":  0.90,   # déficit ligero para recomposición
    "general": 0.90,   # déficit conservador
}

# ── Distribución de macros por tipo de día ────────────────────────────────────
# Carbos más altos en días de gym → glucógeno muscular
# Grasas más altas en días de descanso → sensibilidad insulínica
MACRO_DIST = {
    "gym": {
        "prot_pct": None,   # fijo por kg
        "carbs_pct": 0.45,
        "grasa_min_g_kg": 0.7,
    },
    "descanso": {
        "prot_pct": None,
        "carbs_pct": 0.30,
        "grasa_min_g_kg": 1.0,
    },
}


def calcular_macros_dia(uid: int, es_gym: bool = False) -> dict:
    """
    Calcula los macros del día con toda la ciencia aplicada.

    Orden de operaciones:
    1. BMR (Mifflin-St Jeor) × factor actividad = TDEE
    2. TDEE × multiplicador objetivo = kcal base
    3. Ajuste SISO desde báscula (semanal)
    4. Override refeed si 3+ semanas en déficit
    5. Ajuste por estrés (estrés alto → reduce déficit)
    6. Ajuste RER: si RER alto (glucosa) → más carbos, si RER bajo → más grasas
    7. Distribución en 4+1 tomas con threshold de leucina
    """
    u = get_usuario(uid)
    if not u:
        return {}

    peso   = float(u.get("peso_kg")   or 80)
    altura = float(u.get("altura_cm") or 170)
    edad   = int(u.get("edad")        or 30)
    sexo   = u.get("sexo", "hombre")
    act    = u.get("actividad_nivel", "moderado")
    obj    = u.get("objetivo_gym", "general")
    estres = u.get("nivel_estres", "moderado")
    sueño  = float(u.get("sueño_horas") or 7)

    # ── 1. BMR + TDEE ─────────────────────────────────────────────────────────
    if sexo == "mujer":
        bmr = round(10*peso + 6.25*altura - 5*edad - 161)
    else:
        bmr = round(10*peso + 6.25*altura - 5*edad + 5)

    factor = ACTIVIDAD_FACTOR.get(act, 1.375)
    tdee   = round(bmr * factor)

    # ── 2. Calorías objetivo ──────────────────────────────────────────────────
    mult   = OBJETIVO_MULT.get(obj, 0.90)
    kcal   = round(tdee * mult)

    # ── 3. Ajuste SISO ────────────────────────────────────────────────────────
    ajuste = calcular_ajuste_calorico(uid)
    delta  = {
        "subir":   ajuste["kcal"],
        "reducir": -ajuste["kcal"],
        "mantener": 0,
    }.get(ajuste["accion"], 0)
    kcal += delta

    # ── 4. Refeed override ────────────────────────────────────────────────────
    es_refeed = necesita_refeed(uid)
    if es_refeed:
        kcal  = tdee  # semana de mantenimiento
        delta = 0

    # ── 5. Ajuste por estrés (cortisol) ──────────────────────────────────────
    # Estrés alto eleva cortisol → mayor catabolismo muscular en déficit
    # Reducimos el déficit para proteger la masa magra
    if estres in ("alto", "muy_alto") and obj in ("peso", "gluteo"):
        deficit_actual = tdee - kcal
        deficit_max    = tdee * 0.15  # máx 15% déficit con estrés alto
        if deficit_actual > deficit_max:
            kcal = round(tdee - deficit_max)

    # ── 6. Ajuste por sueño ───────────────────────────────────────────────────
    # Sueño < 6h: reducir déficit (menos recuperación = más riesgo catabólico)
    if sueño < 6.0 and obj in ("peso", "gluteo"):
        deficit_actual = tdee - kcal
        deficit_max    = tdee * 0.10  # máx 10% con sueño muy malo
        if deficit_actual > deficit_max:
            kcal = round(tdee - deficit_max)

    # ── 7. Proteína (Phillips 2016: 2.2g/kg) ─────────────────────────────────
    prot_g  = round(peso * 2.2)
    toma_g  = round(prot_g / 4)  # 4 tomas principales

    # Caseína nocturna: 40g adicionales si el usuario tiene dairy permitido
    alergias    = u.get("alergias","") or ""
    tiene_dairy = "lacteos" not in alergias and "vegano" not in alergias
    caseina_g   = 40 if tiene_dairy else 0

    # ── 8. Carbohidratos (ajustado por RER del día) ───────────────────────────
    activ_ayer = get_actividad_dia(uid)
    rer        = activ_ayer.get("rer_estimado") if activ_ayer else None
    zona_fc    = activ_ayer.get("zona_fc_predominante", 1) if activ_ayer else 1

    dist_tipo = "gym" if es_gym else "descanso"

    # Ajuste RER: si alta intensidad ayer → más carbos hoy (reposición glucógeno)
    carbs_pct = MACRO_DIST[dist_tipo]["carbs_pct"]
    if rer and rer >= 0.90:   # zona 4-5 ayer → glucosa predominante
        carbs_pct = min(carbs_pct + 0.10, 0.55)
    elif rer and rer <= 0.75: # zona 1-2 ayer → lipolisis
        carbs_pct = max(carbs_pct - 0.05, 0.20)

    carbs_g  = round((kcal * carbs_pct) / 4)

    # ── 9. Grasas (resto calórico, mínimo 0.7-1.0g/kg) ───────────────────────
    grasas_g = round((kcal - (prot_g * 4) - (carbs_g * 4)) / 9)
    min_grasas = round(peso * MACRO_DIST[dist_tipo]["grasa_min_g_kg"])
    grasas_g = max(grasas_g, min_grasas)

    # Recalcular kcal reales
    kcal_real = (prot_g * 4) + (carbs_g * 4) + (grasas_g * 9)

    # ── 10. Distribución en 4 tomas (threshold leucina 3-4h) ─────────────────
    distribucion = _distribucion_tomas(
        prot_g=prot_g, carbs_g=carbs_g,
        es_gym=es_gym, hora_gym=u.get("hora_gym","17:00"),
        tiene_dairy=tiene_dairy, caseina_g=caseina_g,
        proteinas_favoritas=u.get("proteinas_favoritas","pollo,huevo,atun") or "pollo,huevo,atun",
        donde_come=u.get("donde_come","casa") or "casa",
    )

    return {
        "kcal":              kcal_real,
        "kcal_tdee":         tdee,
        "proteina_g":        prot_g,
        "carbs_g":           carbs_g,
        "grasas_g":          grasas_g,
        "toma_proteina":     toma_g,
        "caseina_nocturna":  caseina_g,
        "es_gym":            es_gym,
        "es_refeed":         es_refeed,
        "ajuste_siso":       ajuste,
        "rer_hoy":           rer,
        "zona_fc_hoy":       zona_fc,
        "distribucion":      distribucion,
        "deficit_pct":       round(((tdee - kcal_real) / tdee) * 100, 1) if tdee > 0 else 0,
    }


def _distribucion_tomas(prot_g: int, carbs_g: int, es_gym: bool,
                        hora_gym: str, tiene_dairy: bool, caseina_g: int,
                        proteinas_favoritas: str, donde_come: str) -> dict:
    """
    Distribuye los macros en 4-5 tomas según el horario real del usuario.
    Timing periworkout: carbos antes y después del gym.
    Caseína al dormir para síntesis proteica nocturna (Snijders 2015).
    """
    toma = round(prot_g / 4)
    prots = [p.strip() for p in proteinas_favoritas.split(",")]
    prot1 = prots[0] if len(prots) > 0 else "pollo"
    prot2 = prots[1] if len(prots) > 1 else "huevo"
    prot3 = prots[2] if len(prots) > 2 else "atún"

    # Calcular hora de gym y tomas periworkout
    try:
        h_gym = int(hora_gym.split(":")[0])
    except Exception:
        h_gym = 17

    h_pre  = (h_gym - 1) % 24
    h_post = (h_gym + 1) % 24

    # Distribución de carbos: más en periworkout si es día de gym
    if es_gym:
        carbs_pre  = round(carbs_g * 0.30)  # 30% antes
        carbs_post = round(carbs_g * 0.30)  # 30% después
        carbs_resto = carbs_g - carbs_pre - carbs_post
        carbs_des  = round(carbs_resto * 0.50)
        carbs_cena = carbs_g - carbs_pre - carbs_post - carbs_des
    else:
        carbs_des  = round(carbs_g * 0.35)
        carbs_pre  = round(carbs_g * 0.35)
        carbs_post = 0
        carbs_cena = carbs_g - carbs_des - carbs_pre

    # Adaptación por dónde come
    on_the_go = donde_come in ("fuera", "rapido")

    tomas = {}

    tomas["desayuno"] = {
        "hora":     "7-9 am",
        "prot":     toma,
        "carbs":    carbs_des,
        "nota":     f"{prot2.capitalize()} + avena/fruta" if not on_the_go else "Yogur griego + fruta",
    }

    if es_gym:
        tomas["pre_workout"] = {
            "hora":  f"{h_pre}:00",
            "prot":  toma,
            "carbs": carbs_pre,
            "nota":  f"Carbos de digestión media · {prot3.capitalize()} o arroz + {prot1.capitalize()}",
        }
        tomas["post_workout"] = {
            "hora":  f"{h_post}:00",
            "prot":  toma,
            "carbs": carbs_post,
            "nota":  "Proteína + carbos rápidos · ventana anabólica 0-2h post",
        }
    else:
        tomas["almuerzo"] = {
            "hora":  "12-2 pm",
            "prot":  toma,
            "carbs": carbs_pre,
            "nota":  f"{prot1.capitalize()} + carbos complejos" if not on_the_go else f"{prot1.capitalize()} + opción restaurante",
        }
        tomas["merienda"] = {
            "hora":  "3-5 pm",
            "prot":  toma,
            "carbs": 0,
            "nota":  "Snack proteico · queso cottage o yogur griego",
        }

    tomas["cena"] = {
        "hora":  "7-9 pm",
        "prot":  toma,
        "carbs": carbs_cena,
        "nota":  f"{prot1.capitalize()} + verduras + carbos bajos",
    }

    if tiene_dairy and caseina_g > 0:
        tomas["caseina_nocturna"] = {
            "hora":  "30 min antes de dormir",
            "prot":  caseina_g,
            "carbs": 0,
            "nota":  "Yogur griego 200g o requesón · síntesis proteica nocturna +22% (Snijders 2015)",
        }

    return tomas
