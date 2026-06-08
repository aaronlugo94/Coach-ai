"""
engine/nutrition/macros.py
Cálculo de macros basado en ciencia (Mifflin-St Jeor + ajuste SISO).
Sin delegar cálculos a Gemini.
"""
from __future__ import annotations
from db.database import get_usuario, calcular_ajuste_calorico, necesita_refeed

ACTIVIDAD_FACTOR = {
    "sedentario": 1.2,
    "moderado":   1.375,
    "activo":     1.55,
}

def calcular_tdee(uid: int) -> dict:
    u = get_usuario(uid)
    if not u: return {}
    peso   = float(u.get("peso_kg") or 80)
    altura = float(u.get("altura_cm") or 170)
    edad   = int(u.get("edad") or 30)
    sexo   = u.get("sexo","hombre")
    act    = u.get("actividad_nivel","sedentario")

    # Mifflin-St Jeor
    if sexo == "hombre":
        bmr = round(10*peso + 6.25*altura - 5*edad + 5)
    else:
        bmr = round(10*peso + 6.25*altura - 5*edad - 161)

    tdee = round(bmr * ACTIVIDAD_FACTOR.get(act, 1.2))
    return {"bmr": bmr, "tdee": tdee, "peso": peso}


def calcular_macros_dia(uid: int, es_gym: bool = False) -> dict:
    """
    Calcula macros del día con ajuste SISO y refeed automático.
    Proteína: 2.2g/kg LBM | 4 tomas de 35-40g
    Carbos: más en días de gym, menos en descanso
    """
    u = get_usuario(uid)
    if not u: return {}

    tdee_data = calcular_tdee(uid)
    if not tdee_data: return {}

    tdee   = tdee_data["tdee"]
    peso   = tdee_data["peso"]
    obj    = u.get("objetivo_gym","general")

    # Déficit/superávit según objetivo
    MULTIPLICADORES = {
        "peso":    0.82,
        "mamado":  1.10,
        "gluteo":  0.90,
        "general": 0.90,
    }
    mult = MULTIPLICADORES.get(obj, 0.90)

    # Ajuste SISO desde báscula
    ajuste = calcular_ajuste_calorico(uid)
    ajuste_kcal = ajuste["kcal"] * (1 if ajuste["accion"]=="subir" else -1 if ajuste["accion"]=="reducir" else 0)

    # Refeed override
    es_refeed = necesita_refeed(uid)
    if es_refeed:
        mult = 1.0
        ajuste_kcal = 0

    kcal_base = round(tdee * mult) + ajuste_kcal

    # Proteína: 2.2g/kg (estimamos LBM como 75% del peso si no hay datos de grasa)
    proteina_g = round(peso * 2.2)

    # Distribución de macros según día
    if es_gym:
        # Día de gym: más carbos periworkout
        carbs_g  = round((kcal_base * 0.45) / 4)
        grasas_g = round((kcal_base - (proteina_g * 4) - (carbs_g * 4)) / 9)
    else:
        # Día de descanso: menos carbos, más grasas
        carbs_g  = round((kcal_base * 0.30) / 4)
        grasas_g = round((kcal_base - (proteina_g * 4) - (carbs_g * 4)) / 9)

    grasas_g = max(grasas_g, round(peso * 0.7))  # mínimo 0.7g/kg

    # Recalcular kcal reales
    kcal_real = (proteina_g * 4) + (carbs_g * 4) + (grasas_g * 9)

    # Distribución en 4 tomas (threshold de leucina cada 3-4h)
    toma = round(proteina_g / 4)

    return {
        "kcal":         kcal_real,
        "proteina_g":   proteina_g,
        "carbs_g":      carbs_g,
        "grasas_g":     grasas_g,
        "toma_proteina": toma,
        "es_gym":       es_gym,
        "es_refeed":    es_refeed,
        "ajuste_siso":  ajuste,
        "distribucion": {
            "comida_1": {"proteina": toma, "carbos": round(carbs_g*0.25), "nota": "Desayuno — carbos medios"},
            "comida_2": {"proteina": toma, "carbos": round(carbs_g*0.30) if es_gym else round(carbs_g*0.25), "nota": "Pre-workout" if es_gym else "Almuerzo"},
            "comida_3": {"proteina": toma, "carbos": round(carbs_g*0.30) if es_gym else round(carbs_g*0.25), "nota": "Post-workout" if es_gym else "Comida 3"},
            "comida_4": {"proteina": toma, "carbos": round(carbs_g*0.15), "nota": "Cena + 30-40g caseína nocturna"},
        }
    }
