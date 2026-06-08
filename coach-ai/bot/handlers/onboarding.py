"""
bot/handlers/onboarding.py
Onboarding de 3 pasos. Cero texto escrito por el usuario excepto datos físicos.
"""
from __future__ import annotations
import logging, re
from telegram import Update
from telegram.ext import ContextTypes
from db.database import get_usuario, upsert_usuario, has_plan, insert_plan
from bot.keyboards import (kb_objetivos, kb_nivel, kb_ambiente, kb_dias,
                            kb_limitaciones, kb_horario, kb_dieta, kb_restricciones,
                            TECLADO_PRINCIPAL)

logger = logging.getLogger(__name__)

OBJETIVOS = {
    "bajar_grasa":   ("🔥 Bajar grasa / perder peso",   "peso"),
    "ganar_musculo": ("💪 Ganar músculo y fuerza",       "mamado"),
    "recomposicion": ("⚡ Bajar grasa Y ganar músculo",  "general"),
    "gluteo_pierna": ("🍑 Glúteo y pierna",              "gluteo"),
    "salud":         ("🏃 Salud y energía",              "general"),
    "competitivo":   ("🏆 Nivel competitivo",            "mamado"),
}

async def _edit(query, text, kb=None):
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML",
                                      disable_web_page_preview=True)
    except Exception as e:
        if "not modified" not in str(e).lower():
            raise


async def handle_ob(query, uid: int, context):
    """Paso 1 — Objetivo."""
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query,
            "Hola 👋 Empecemos — <b>¿cuál es tu objetivo?</b>", kb_objetivos())
        return
    desc, gym = OBJETIVOS.get(sub, ("","general"))
    upsert_usuario(uid, objetivo_vida=sub, objetivo_gym=gym)
    context.user_data["ob_step"] = "datos"
    await _edit(query,
        f"<b>Objetivo: {desc} ✅</b>\n\n"
        f"<b>Paso 1/3 — Tus datos físicos</b>\n\n"
        f"Escríbeme en un solo mensaje:\n"
        f"<code>edad, peso, altura, sexo</code>\n\n"
        f"Ejemplo: <code>29 años, 112 kg, 178 cm, hombre</code>")


async def handle_datos_texto(uid: int, texto: str, update: Update, context):
    """Parser de datos físicos desde texto libre."""
    texto_l = texto.lower()
    sexo = ("hombre" if any(x in texto_l for x in ["hombre","masculino","male"])
            else "mujer" if any(x in texto_l for x in ["mujer","femenino","female"])
            else None)
    nums = re.findall(r'(\d+(?:[.,]\d+)?)\s*(kg|kgs|lbs|lb|cm|años|año)?', texto_l)
    edad = peso = altura = None
    for val_s, unit in nums:
        val = float(val_s.replace(",","."))
        if unit in ("kg","kgs") or (not unit and 30 <= val <= 300 and not peso):
            if 30 <= val <= 300: peso = val
        elif unit in ("lbs","lb"):
            peso = round(val * 0.453592, 1)
        elif unit == "cm" or (not unit and 130 <= val <= 230 and not altura):
            if 130 <= val <= 230: altura = val
        elif unit in ("años","año") or (not unit and 10 <= val <= 100 and not edad):
            if 10 <= val <= 100: edad = int(val)

    kw = {}
    if edad:   kw["edad"] = edad
    if peso:   kw["peso_kg"] = peso
    if altura: kw["altura_cm"] = altura
    if sexo:   kw["sexo"] = sexo
    if kw: upsert_usuario(uid, **kw)

    p = get_usuario(uid) or {}
    falta = []
    if not p.get("edad"):       falta.append("edad (ej: 29)")
    if not p.get("peso_kg"):    falta.append("peso (ej: 112 kg)")
    if not p.get("altura_cm"): falta.append("altura (ej: 178 cm)")
    if not p.get("sexo"):       falta.append("sexo (hombre/mujer)")

    if falta:
        await update.message.reply_text(
            f"✅ Anotado. Falta: <b>{', '.join(falta)}</b>\n\nEscribe el resto:",
            parse_mode="HTML")
        return

    # Calcular BMR
    peso_v = float(p["peso_kg"]); altura_v = float(p["altura_cm"])
    edad_v = int(p["edad"]); sexo_v = p.get("sexo","hombre")
    if sexo_v == "hombre":
        bmr = round(10*peso_v + 6.25*altura_v - 5*edad_v + 5)
    else:
        bmr = round(10*peso_v + 6.25*altura_v - 5*edad_v - 161)
    upsert_usuario(uid, bmr=bmr)
    context.user_data["ob_step"] = None

    await update.message.reply_text(
        f"✅ Perfil registrado — BMR: <b>{bmr} kcal/día</b>\n\n"
        f"<b>Paso 2/3 — Tu entrenamiento</b>\n\n"
        f"¿Cuánto tiempo llevas entrenando?",
        parse_mode="HTML", reply_markup=kb_nivel())


async def handle_nv(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuánto tiempo llevas entrenando?</b>", kb_nivel())
        return
    upsert_usuario(uid, nivel=sub)
    await _edit(query, f"<b>Nivel: {sub} ✅</b>\n\n<b>¿Dónde entrenas?</b>", kb_ambiente())


async def handle_am(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Dónde entrenas?</b>", kb_ambiente())
        return
    upsert_usuario(uid, ambiente=sub)
    await _edit(query, "<b>¿Cuántos días a la semana?</b>\n\n<i>4 días es el punto óptimo.</i>", kb_dias())


async def handle_dy(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuántos días a la semana?</b>", kb_dias())
        return
    upsert_usuario(uid, dias_semana=int(sub))
    await _edit(query, f"<b>{sub} días ✅</b>\n\n<b>¿Tienes alguna lesión?</b>", kb_limitaciones())


async def handle_lm(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Tienes alguna lesión?</b>", kb_limitaciones())
        return
    upsert_usuario(uid, limitaciones=sub)
    await _edit(query, "<b>Paso 2/3 completo ✅</b>\n\n<b>⏰ ¿A qué hora quieres tu recordatorio diario?</b>",
                kb_horario("lm:back"))


async def handle_hr(query, uid: int, context):
    parts = query.data.split(":")
    if parts[1] == "back":
        await _edit(query, "<b>⏰ ¿A qué hora quieres tu recordatorio?</b>", kb_horario("lm:back"))
        return
    hora = None if parts[1] == "none" else f"{parts[1]}:{parts[2]}" if len(parts) > 2 else parts[1]
    upsert_usuario(uid, hora_reminder=hora)
    if context.user_data.get("solo_gym"):
        context.user_data["solo_gym"] = False
        await _generar(query, uid, context)
        return
    await _edit(query,
        "<b>Paso 3/3 — Tu alimentación</b>\n\n<b>¿Cómo describes tu dieta?</b>",
        kb_dieta())


async def handle_dt(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cómo describes tu dieta?</b>", kb_dieta())
        return
    upsert_usuario(uid, tipo_dieta=sub)
    context.user_data["rest_sel"] = set()
    await _edit(query,
        "<b>¿Hay algo que no puedas comer?</b>\n<i>Selecciona todo lo que aplique:</i>",
        kb_restricciones(set()))


async def handle_rt(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("rest_sel", set())
    if sub == "ok":
        extra = context.user_data.get("rest_extra","")
        todas = list(sel) + ([extra] if extra else [])
        upsert_usuario(uid, alergias=",".join(sorted(todas)) if todas else "ninguna")
        await _generar(query, uid, context)
        return
    if sub == "otra":
        context.user_data["ob_step"] = "restriccion_otra"
        await _edit(query, "✏️ <b>Escribe tu restricción</b>\n\nEj: sin azúcar, sin soya")
        return
    if sub == "back":
        await _edit(query, "<b>¿Hay algo que no puedas comer?</b>", kb_restricciones(sel))
        return
    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["rest_sel"] = sel
    await _edit(query, "<b>¿Hay algo que no puedas comer?</b>\n<i>Selecciona todo lo que aplique:</i>",
                kb_restricciones(sel))


async def _generar(query, uid: int, context):
    await query.edit_message_text("⚙️ <b>Creando tu plan...</b>", parse_mode="HTML")
    try:
        u = get_usuario(uid)
        from engine.gym.planner import generar_plan
        plan = generar_plan(
            nivel=u.get("nivel","intermedio"),
            objetivo=u.get("objetivo_gym","general"),
            dias=int(u.get("dias_semana") or 4),
            ambiente=u.get("ambiente","gym"),
            limitacion=u.get("limitaciones","ninguna"),
        )
        n = insert_plan(uid, plan)
        from db.database import set_estado
        set_estado(uid, plan[0]["semana"], plan[0]["dias"][0]["dia"])
        upsert_usuario(uid, onboarding_done=1)
        peso = float(u.get("peso_kg") or 80)
        tdee = int(u.get("tdee") or u.get("bmr",2000)*1.2)
        prot = round(peso * 2.2)
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        await query.edit_message_text(
            f"✅ <b>Plan creado — {n} ejercicios · 4 semanas</b>\n\n"
            f"💡 Proteína objetivo: <b>{prot}g/día</b> (4 tomas de {round(prot/4)}g)\n"
            f"<i>El plan de nutrición detallado llega el domingo.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💪 Ver mi rutina de hoy", callback_data="m:hoy")
            ]])
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="Usa los botones 👇",
            reply_markup=TECLADO_PRINCIPAL)
    except Exception as e:
        logger.error("Error generando plan uid=%s: %s", uid, e, exc_info=True)
        await query.edit_message_text(f"❌ Error: {str(e)[:150]}\n\nEscribe /start")
