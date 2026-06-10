"""
ai/coach.py — Invisible Coach v3.0

Interfaz con Gemini 2.0 Flash.
Maneja todos los tipos de análisis y notificaciones.
"""
from __future__ import annotations
import json
import logging
import os
import re

import google.generativeai as genai

from .prompts import (
    prompt_briefing_matutino,
    prompt_checkin_nocturno,
    prompt_notificacion_enganche,
    prompt_resumen_semanal,
    prompt_plan_nutricion,
)

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
MODEL = genai.GenerativeModel("gemini-2.0-flash")

# ── Configuración de generación ───────────────────────────────────────────────
CONFIG_TEXTO = genai.types.GenerationConfig(
    temperature=0.4,      # bajo para respuestas más consistentes
    max_output_tokens=300,
)
CONFIG_JSON = genai.types.GenerationConfig(
    temperature=0.2,      # más determinista para JSON
    max_output_tokens=4000,
)


async def _generar(prompt: str, config=None) -> str:
    try:
        r = await MODEL.generate_content_async(
            prompt,
            generation_config=config or CONFIG_TEXTO,
        )
        return r.text.strip()
    except Exception as e:
        logger.error("Gemini error: %s", e)
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# ANÁLISIS DIARIOS
# ══════════════════════════════════════════════════════════════════════════════

async def generar_briefing(datos: dict) -> str:
    """
    Briefing matutino — se envía a la hora configurada por el usuario.
    Máximo 4 líneas, datos reales, acción concreta.
    """
    prompt = prompt_briefing_matutino(datos)
    texto  = await _generar(prompt)
    if not texto:
        return _fallback_briefing(datos)
    return texto


async def generar_checkin(datos: dict) -> str:
    """
    Análisis nocturno post check-in de 2 taps.
    """
    prompt = prompt_checkin_nocturno(datos)
    texto  = await _generar(prompt)
    if not texto:
        return _fallback_checkin(datos)
    return texto


async def generar_resumen_semanal(datos: dict) -> str:
    """
    Resumen del domingo con números reales y proyección de meta.
    """
    prompt = prompt_resumen_semanal(datos)
    return await _generar(prompt) or "Semana completada. Revisa tu progreso en la web."


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICACIONES DE ENGANCHE
# ══════════════════════════════════════════════════════════════════════════════

async def generar_notificacion(tipo: str, datos: dict) -> str:
    """
    Notificaciones automáticas con copy generado por Gemini.
    tipos: sin_entrenar | progresion_semanal | hrv_bajo | racha
    """
    prompt = prompt_notificacion_enganche(tipo, datos)
    texto  = await _generar(prompt)
    if not texto:
        return _fallback_notificacion(tipo, datos)
    return texto


# ══════════════════════════════════════════════════════════════════════════════
# PLAN DE NUTRICIÓN SEMANAL
# ══════════════════════════════════════════════════════════════════════════════

async def generar_plan_nutricion(datos: dict) -> dict | None:
    """
    Genera el plan de nutrición semanal completo.
    Retorna dict JSON o None si falla.
    """
    prompt = prompt_plan_nutricion(datos)
    texto  = await _generar(prompt, config=CONFIG_JSON)

    if not texto:
        return None

    # Limpiar posibles backticks de markdown
    texto = re.sub(r"```(?:json)?", "", texto).strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        logger.error("JSON decode error en plan nutrición: %s", e)
        # Intentar extraer el JSON del texto
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return None


# ══════════════════════════════════════════════════════════════════════════════
# COACH CONVERSACIONAL (responde preguntas del usuario)
# ══════════════════════════════════════════════════════════════════════════════

async def responder_pregunta(uid: int, pregunta: str) -> str:
    """
    Coach conversacional: el usuario puede preguntar cualquier cosa.
    Gemini responde con contexto completo del perfil.
    """
    from db.database import (get_usuario, get_estado_bannister,
                              get_ultimo_pesaje, get_actividad_dia)

    u      = get_usuario(uid)
    bann   = get_estado_bannister(uid) if u else {}
    pesaje = get_ultimo_pesaje(uid)

    if not u:
        return "Completa el setup primero con /start"

    nombre  = (u.get("nombre") or "").split()[0]
    peso    = pesaje.get("peso_kg") if pesaje else u.get("peso_kg","?")
    grasa   = pesaje.get("grasa_pct") if pesaje else "?"
    obj     = u.get("objetivo_vida","")
    nivel   = u.get("nivel","intermedio")
    snc_pct = bann.get("snc_pct", 85)

    prompt = f"""Eres el coach personal de {nombre}. Responde su pregunta con base en su perfil real.

PERFIL ACTUAL:
Peso: {peso} kg | Grasa: {grasa}% | Objetivo: {obj}
Nivel: {nivel} | SNC: {snc_pct}%

PREGUNTA: {pregunta}

INSTRUCCIONES:
- Responde directamente sin intro ("Claro que sí" o similar)
- Si tiene aplicación directa a su perfil → menciona sus datos reales
- Máximo 3 párrafos cortos
- Si no sabes algo → di que no tienes suficientes datos
- Tono: coach experto y directo, no terapeuta
Solo en español."""

    texto = await _generar(prompt, config=genai.types.GenerationConfig(
        temperature=0.5, max_output_tokens=400
    ))
    return texto or "No pude generar una respuesta. Intenta de nuevo."


# ══════════════════════════════════════════════════════════════════════════════
# FALLBACKS (si Gemini falla, el usuario ve algo útil)
# ══════════════════════════════════════════════════════════════════════════════

def _fallback_briefing(datos: dict) -> str:
    bann   = datos.get("bannister", {})
    hoy    = datos.get("hoy", {})
    macros = datos.get("macros", {})
    snc    = bann.get("snc_pct", 85)
    grupo  = hoy.get("grupo","").upper()
    kcal   = macros.get("kcal", 0)
    prot   = macros.get("proteina_g", 0)
    rec    = bann.get("rec_volumen","normal")

    if rec == "deload":
        return (f"🔋 SNC: {snc}% · Semana de deload — volumen reducido, intensidad relativa mantenida\n"
                f"{'💪 ' + grupo if grupo else '🌿 Descanso activo'} · Pesos igual que semana pasada\n"
                f"🥗 {kcal} kcal · {prot}g proteína · 4 tomas")

    return (f"🔋 SNC: {snc}% · {'Listo para alta carga' if snc >= 85 else 'Recuperación moderada'}\n"
            f"{'💪 HOY: ' + grupo if grupo else '🌿 Descanso activo — movilidad 15 min'}\n"
            f"🥗 {kcal} kcal · {prot}g proteína · 4 tomas de {macros.get('toma_proteina',0)}g")


def _fallback_checkin(datos: dict) -> str:
    sesion = datos.get("sesion", {})
    pesos  = datos.get("pesos_usados", [])
    rutina = sesion.get("completada", False)
    progs  = [p for p in pesos if p.get("es_nuevo_peso")]

    if progs:
        nombres = ", ".join(p["ejercicio"][:20] for p in progs[:2])
        return f"✅ Progresión: {nombres} subieron de peso — doble progresión activada.\nDescansa bien esta noche para la síntesis proteica."

    if rutina:
        return "Sesión completada ✅\n40g proteína antes de dormir para maximizar recuperación."

    return "Mañana entrenas. Come proteína esta noche y duerme 7-8h."


def _fallback_notificacion(tipo: str, datos: dict) -> str:
    u      = datos.get("usuario", {})
    nombre = (u.get("nombre") or "").split()[0] or "tú"
    if tipo == "sin_entrenar":
        ej    = datos.get("ejercicio_proximo","tu próxima sesión")
        peso  = datos.get("peso_sugerido", 0)
        return f"{nombre}, {ej} te espera{f' con {peso} lbs' if peso else ''}. Tu ventana anabólica óptima es esta semana."
    elif tipo == "hrv_bajo":
        return f"HRV bajo detectado. Hoy: 20 min caminata + proteína alta. Mañana entrenas más fuerte."
    elif tipo == "racha":
        dias = datos.get("racha",0)
        return f"🔥 {dias} días de racha, {nombre}. Eso es consistencia real."
    return ""
