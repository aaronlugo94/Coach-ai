"""
ai/coach.py — Interfaz con Gemini.
"""
from __future__ import annotations
import logging, os
import google.generativeai as genai
from .prompts import prompt_coach_nocturno, prompt_plan_nutricion

logger = logging.getLogger(__name__)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY",""))
MODEL = genai.GenerativeModel("gemini-2.0-flash")

async def analisis_nocturno(datos: dict) -> str:
    try:
        prompt = prompt_coach_nocturno(datos)
        r = await MODEL.generate_content_async(prompt)
        return r.text.strip()
    except Exception as e:
        logger.error("Gemini error: %s", e)
        return _fallback(datos)

async def generar_plan_nutricion(datos: dict) -> str:
    try:
        prompt = prompt_plan_nutricion(datos)
        r = await MODEL.generate_content_async(prompt)
        return r.text.strip()
    except Exception as e:
        logger.error("Gemini nutricion error: %s", e)
        return ""

def _fallback(datos: dict) -> str:
    grupo = datos.get("grupo","")
    fatiga = datos.get("fatiga",2)
    if fatiga >= 4:
        return "Sesión completada. Fatiga alta — prioriza sueño y proteína esta noche. Mañana empieza fuerte."
    return f"Sesión de {grupo} completada. Revisa los pesos usados y sube si llegaste al tope de reps."
