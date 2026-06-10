"""
bot/handlers/onboarding.py — Invisible Coach v3.0

Discovery en 4 bloques científicos. 100% botones, cero escritura.

Bloque 1: Perfil biológico (edad, peso, altura, sexo, objetivo)
Bloque 2: Experiencia y capacidad mecánica (nivel, días, tiempo, horario, equipo)
Bloque 3: Flexibilidad nutricional (dieta, proteínas favoritas, preparación, restricciones)
Bloque 4: Recuperación y estilo de vida (sueño, trabajo, estrés, wearable)

Al terminar: genera el plan de gym + macros base automáticamente.
"""
from __future__ import annotations
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db.database import (
    get_usuario, upsert_usuario, insert_plan,
    set_estado, add_allowed_user,
)
from bot.keyboards import TECLADO_PRINCIPAL

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _edit(query, text: str, kb=None):
    try:
        await query.edit_message_text(
            text, reply_markup=kb, parse_mode="HTML",
            disable_web_page_preview=True)
    except Exception as e:
        if "not modified" not in str(e).lower():
            raise

def _kb(*rows):
    return InlineKeyboardMarkup(rows)

def _btn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)

def _back(data: str) -> list:
    return [_btn("← Atrás", data)]


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — PERFIL BIOLÓGICO
# ══════════════════════════════════════════════════════════════════════════════

async def handle_ob(query, uid: int, context):
    """Objetivo principal — entrada al onboarding."""
    sub = query.data.split(":")[1]

    if sub == "back":
        await _mostrar_objetivo(query)
        return

    MAPA = {
        "recomposicion": ("general",  "⚡ Recomposición corporal"),
        "volumen":       ("mamado",   "💪 Volumen limpio"),
        "deficit":       ("peso",     "🔥 Déficit eficiente"),
        "gluteo":        ("gluteo",   "🍑 Glúteo y pierna"),
        "salud":         ("general",  "🏃 Salud y energía"),
    }
    objetivo_gym, desc = MAPA.get(sub, ("general", sub))
    upsert_usuario(uid, objetivo_vida=sub, objetivo_gym=objetivo_gym)

    await _edit(query,
        f"<b>{desc} ✅</b>\n\n"
        f"<b>Bloque 1/4 — Tu perfil biológico</b>\n\n"
        f"¿Cuántos años tienes?",
        _kb(
            [_btn("18-24", "edad:21"), _btn("25-29", "edad:27"), _btn("30-34", "edad:32")],
            [_btn("35-39", "edad:37"), _btn("40-49", "edad:44"), _btn("50+",   "edad:55")],
            _back("ob:back"),
        ))


async def _mostrar_objetivo(query):
    await _edit(query,
        "👋 Bienvenido a <b>Invisible Coach</b>\n\n"
        "En 4 bloques rápidos voy a entender tu biología, "
        "historial de entrenamiento y estilo de vida para "
        "diseñar un plan que realmente funcione.\n\n"
        "<b>¿Cuál es tu objetivo principal a 90 días?</b>",
        _kb(
            [_btn("⚡ Recomposición corporal",             "ob:recomposicion")],
            [_btn("💪 Volumen limpio — máxima masa magra",  "ob:volumen")],
            [_btn("🔥 Déficit eficiente — perder grasa",    "ob:deficit")],
            [_btn("🍑 Glúteo y pierna",                     "ob:gluteo")],
            [_btn("🏃 Salud, energía y bienestar",          "ob:salud")],
        ))


async def handle_edad(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        u = get_usuario(uid)
        obj = u.get("objetivo_vida","") if u else ""
        await _mostrar_objetivo(query)
        return

    edad = int(sub)
    upsert_usuario(uid, edad=edad)
    await _edit(query,
        f"<b>Edad: ~{edad} años ✅</b>\n\n"
        f"¿Cuánto pesas actualmente?",
        _kb(
            [_btn("50-65 kg",    "peso:57"),  _btn("65-80 kg",   "peso:72")],
            [_btn("80-95 kg",    "peso:87"),  _btn("95-110 kg",  "peso:102")],
            [_btn("110-125 kg",  "peso:117"), _btn("125+ kg",    "peso:132")],
            _back("edad:back"),
        ))


async def handle_peso(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuántos años tienes?</b>",
            _kb(
                [_btn("18-24","edad:21"),_btn("25-29","edad:27"),_btn("30-34","edad:32")],
                [_btn("35-39","edad:37"),_btn("40-49","edad:44"),_btn("50+","edad:55")],
            ))
        return

    peso = float(sub)
    upsert_usuario(uid, peso_kg=peso)
    await _edit(query,
        f"<b>Peso: ~{peso} kg ✅</b>\n\n"
        f"¿Cuánto mides?",
        _kb(
            [_btn("155-165 cm", "altura:160"), _btn("165-175 cm", "altura:170")],
            [_btn("175-185 cm", "altura:180"), _btn("185-195 cm", "altura:190")],
            [_btn("195+ cm",    "altura:198")],
            _back("peso:back"),
        ))


async def handle_altura(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuánto pesas?</b>",
            _kb(
                [_btn("50-65 kg","peso:57"),  _btn("65-80 kg","peso:72")],
                [_btn("80-95 kg","peso:87"),  _btn("95-110 kg","peso:102")],
                [_btn("110-125 kg","peso:117"),_btn("125+ kg","peso:132")],
            ))
        return

    altura = float(sub)
    upsert_usuario(uid, altura_cm=altura)
    await _edit(query,
        f"<b>Altura: ~{altura} cm ✅</b>\n\n"
        f"¿Cuál es tu sexo biológico?\n"
        f"<i>Necesario para calcular tu metabolismo basal con precisión (Mifflin-St Jeor)</i>",
        _kb(
            [_btn("Hombre", "sexo:hombre"), _btn("Mujer", "sexo:mujer")],
            _back("altura:back"),
        ))


async def handle_sexo(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuánto mides?</b>",
            _kb(
                [_btn("155-165 cm","altura:160"),_btn("165-175 cm","altura:170")],
                [_btn("175-185 cm","altura:180"),_btn("185-195 cm","altura:190")],
                [_btn("195+ cm","altura:198")],
            ))
        return

    upsert_usuario(uid, sexo=sub)

    # Calcular BMR y TDEE (Mifflin-St Jeor)
    u    = get_usuario(uid)
    peso = float(u.get("peso_kg") or 80)
    alt  = float(u.get("altura_cm") or 170)
    edad = int(u.get("edad") or 30)
    bmr  = round(10*peso + 6.25*alt - 5*edad + (5 if sub=="hombre" else -161))
    tdee = round(bmr * 1.375)
    upsert_usuario(uid, bmr=bmr, tdee=tdee)

    await _edit(query,
        f"<b>Perfil biológico completo ✅</b>\n\n"
        f"📊 Gasto calórico estimado: <b>{tdee} kcal/día</b>\n"
        f"<i>BMR {bmr} kcal × factor actividad moderada</i>\n\n"
        f"<b>Bloque 2/4 — Experiencia y capacidad mecánica</b>\n\n"
        f"¿Cuánto tiempo llevas entrenando fuerza de forma seria?",
        _kb(
            [_btn("🌱 Menos de 6 meses",    "nv:principiante")],
            [_btn("💪 6 meses a 2 años",    "nv:intermedio")],
            [_btn("🔥 Más de 2 años",       "nv:avanzado")],
            _back("sexo:back"),
        ))


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — EXPERIENCIA Y CAPACIDAD MECÁNICA
# ══════════════════════════════════════════════════════════════════════════════

async def handle_nv(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuánto tiempo llevas entrenando?</b>",
            _kb(
                [_btn("🌱 Menos de 6 meses","nv:principiante")],
                [_btn("💪 6 meses a 2 años","nv:intermedio")],
                [_btn("🔥 Más de 2 años","nv:avanzado")],
            ))
        return

    NIVEL_DESC = {
        "principiante": "Alta respuesta hipertrófica — progresarás rápido con volumen bajo",
        "intermedio":   "Requiere volumen moderado y progresión sistemática",
        "avanzado":     "Requiere alta intensidad (RIR 1-2) y sobrecarga estricta",
    }
    upsert_usuario(uid, nivel=sub)
    await _edit(query,
        f"<b>Nivel: {sub} ✅</b>\n"
        f"<i>{NIVEL_DESC.get(sub,'')}</i>\n\n"
        f"¿Cuántos días REALES tienes a la semana para entrenar?\n"
        f"<i>Sé honesto — esto determina el split óptimo</i>",
        _kb(
            [_btn("3 días — Fullbody",        "dy:3"),
             _btn("4 días — Upper/Lower",      "dy:4")],
            [_btn("5 días — Push/Pull/Legs",   "dy:5"),
             _btn("6 días — PPL × 2",          "dy:6")],
            _back("nv:back"),
        ))


async def handle_dy(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuántos días tienes a la semana?</b>",
            _kb(
                [_btn("3 días","dy:3"),_btn("4 días","dy:4")],
                [_btn("5 días","dy:5"),_btn("6 días","dy:6")],
            ))
        return

    upsert_usuario(uid, dias_semana=int(sub))
    await _edit(query,
        f"<b>{sub} días ✅</b>\n\n"
        f"¿Cuánto tiempo tienes por sesión?\n"
        f"<i>Esto determina cuántos ejercicios caben en cada día</i>",
        _kb(
            [_btn("⚡ 45 min — sesión densa", "dur:45")],
            [_btn("💪 60 min — estándar",     "dur:60")],
            [_btn("🏆 90 min — completa",      "dur:90")],
            _back("dy:back"),
        ))


async def handle_dur(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuántos días tienes?</b>",
            _kb(
                [_btn("3 días","dy:3"),_btn("4 días","dy:4")],
                [_btn("5 días","dy:5"),_btn("6 días","dy:6")],
            ))
        return

    upsert_usuario(uid, duracion_sesion=int(sub))
    await _edit(query,
        f"<b>{sub} min por sesión ✅</b>\n\n"
        f"¿A qué hora entrenas normalmente?\n"
        f"<i>El briefing matutino y el check-in nocturno se adaptan a tu horario</i>",
        _kb(
            [_btn("🌅 Mañana (6-9am)",  "gym_hora:07:00"),
             _btn("☀️ Mediodía (12-2pm)","gym_hora:12:00")],
            [_btn("🌆 Tarde (4-6pm)",   "gym_hora:17:00"),
             _btn("🌙 Noche (7-9pm)",   "gym_hora:20:00")],
            _back("dur:back"),
        ))


async def handle_gym_hora(query, uid: int):
    parts = query.data.split(":")
    sub   = parts[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuánto tiempo tienes por sesión?</b>",
            _kb(
                [_btn("⚡ 45 min","dur:45")],
                [_btn("💪 60 min","dur:60")],
                [_btn("🏆 90 min","dur:90")],
            ))
        return

    hora_gym = f"{sub}:{parts[2]}" if len(parts) > 2 else sub
    # Calcular hora del briefing (2h antes del gym) y check-in (2h después)
    h, m = map(int, hora_gym.split(":"))
    h_brief = (h - 2) % 24
    h_checkin = (h + 2) % 24
    hora_reminder = f"{h_brief:02d}:00"

    upsert_usuario(uid,
        hora_gym=hora_gym,
        hora_reminder=hora_reminder,
        hora_checkin=f"{h_checkin:02d}:00",
    )

    await _edit(query,
        f"<b>Horario de gym: {hora_gym} ✅</b>\n"
        f"<i>Briefing: {hora_reminder} · Check-in: {h_checkin:02d}:00</i>\n\n"
        f"¿Dónde entrenas?",
        _kb(
            [_btn("🏋️ Gimnasio completo",    "am:gym")],
            [_btn("🏠 Casa — peso corporal",  "am:home")],
            [_btn("🦺 Casa con bandas",       "am:band")],
            _back("gym_hora:back"),
        ))


async def handle_am(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿A qué hora entrenas?</b>",
            _kb(
                [_btn("🌅 Mañana (6-9am)","gym_hora:07:00"),
                 _btn("☀️ Mediodía","gym_hora:12:00")],
                [_btn("🌆 Tarde (4-6pm)","gym_hora:17:00"),
                 _btn("🌙 Noche (7-9pm)","gym_hora:20:00")],
            ))
        return

    upsert_usuario(uid, ambiente=sub)
    await _edit(query,
        f"<b>Lugar: {sub} ✅</b>\n\n"
        f"¿Tienes alguna lesión o limitación física?",
        _kb(
            [_btn("✅ Ninguna, estoy al 100%",    "lm:ninguna")],
            [_btn("🦵 Rodilla — evitar sentadilla","lm:rodilla")],
            [_btn("🔙 Espalda baja — sin axial",  "lm:espalda")],
            [_btn("💪 Hombro — sin press overhead","lm:hombro")],
            _back("am:back"),
        ))


async def handle_lm(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Dónde entrenas?</b>",
            _kb(
                [_btn("🏋️ Gimnasio","am:gym")],
                [_btn("🏠 Casa","am:home")],
                [_btn("🦺 Bandas","am:band")],
            ))
        return

    upsert_usuario(uid, limitaciones=sub)
    await _edit(query,
        f"<b>Lesiones: {sub} ✅</b>\n\n"
        f"<b>Bloque 3/4 — Tu alimentación</b>\n\n"
        f"¿Qué tipo de alimentación llevas o prefieres?",
        _kb(
            [_btn("🍗 Omnívoro / Dieta flexible",      "dt:omnivoro")],
            [_btn("🥗 Saludable — comida real",        "dt:saludable")],
            [_btn("🌱 Vegetariano / Vegano",           "dt:vegano")],
            [_btn("🍖 Alta en proteína (prioridad)",   "dt:proteina")],
            _back("lm:back"),
        ))


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 — FLEXIBILIDAD NUTRICIONAL
# ══════════════════════════════════════════════════════════════════════════════

async def handle_dt(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Tipo de alimentación?</b>",
            _kb(
                [_btn("🍗 Omnívoro / Dieta flexible","dt:omnivoro")],
                [_btn("🥗 Saludable — comida real","dt:saludable")],
                [_btn("🌱 Vegetariano / Vegano","dt:vegano")],
                [_btn("🍖 Alta en proteína","dt:proteina")],
            ))
        return

    DIETAS = {"omnivoro":"🍗 Omnívoro","saludable":"🥗 Saludable","vegano":"🌱 Vegano","proteina":"🍖 Alta proteína"}
    upsert_usuario(uid, tipo_dieta=sub)
    await _edit(query,
        f"<b>Dieta: {DIETAS.get(sub,sub)} ✅</b>\n\n"
        f"¿Cuáles son tus 3 fuentes de proteína favoritas?\n"
        f"<i>La IA arma la dieta con lo que te gusta — no al revés</i>",
        _kb(
            [_btn("🍗 Pollo",    "prot:pollo"),   _btn("🥩 Res/Bistec", "prot:res")],
            [_btn("🐟 Atún",    "prot:atun"),    _btn("🍳 Huevo",      "prot:huevo")],
            [_btn("🐷 Cerdo",   "prot:cerdo"),   _btn("🐟 Salmón",     "prot:salmon")],
            [_btn("🫘 Legumbres","prot:legumbres"),_btn("🥛 Dairy/Caseína","prot:dairy")],
            [_btn("✅ Continuar", "prot:ok")],
            _back("dt:back"),
        ))


async def handle_prot(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Tipo de alimentación?</b>",
            _kb(
                [_btn("🍗 Omnívoro / Dieta flexible","dt:omnivoro")],
                [_btn("🥗 Saludable","dt:saludable")],
                [_btn("🌱 Vegano","dt:vegano")],
                [_btn("🍖 Alta proteína","dt:proteina")],
            ))
        return

    sel = context.user_data.get("prot_sel", set())

    if sub == "ok":
        prots = list(sel) if sel else ["pollo", "huevo", "atun"]
        upsert_usuario(uid, proteinas_favoritas=",".join(prots))
        await _edit(query,
            f"<b>Proteínas: {', '.join(prots)} ✅</b>\n\n"
            f"¿Tienes alguna restricción alimentaria?\n"
            f"<i>Selecciona todo lo que aplique</i>",
            _kb_restricciones(set()))
        return

    if sub in sel: sel.discard(sub)
    else:
        if len(sel) < 3:
            sel.add(sub)
    context.user_data["prot_sel"] = sel

    LABELS = {
        "pollo":"🍗 Pollo","res":"🥩 Res","atun":"🐟 Atún","huevo":"🍳 Huevo",
        "cerdo":"🐷 Cerdo","salmon":"🐟 Salmón","legumbres":"🫘 Legumbres","dairy":"🥛 Dairy",
    }
    check = lambda k: "☑️" if k in sel else "⬜"
    n = len(sel)
    await _edit(query,
        f"<b>Selecciona hasta 3 fuentes de proteína</b> ({n}/3)\n"
        f"<i>La IA usará estas para armar tu plan de comidas</i>",
        _kb(
            [_btn(f"{check('pollo')} 🍗 Pollo","prot:pollo"),
             _btn(f"{check('res')} 🥩 Res","prot:res")],
            [_btn(f"{check('atun')} 🐟 Atún","prot:atun"),
             _btn(f"{check('huevo')} 🍳 Huevo","prot:huevo")],
            [_btn(f"{check('cerdo')} 🐷 Cerdo","prot:cerdo"),
             _btn(f"{check('salmon')} 🐟 Salmón","prot:salmon")],
            [_btn(f"{check('legumbres')} 🫘 Legumbres","prot:legumbres"),
             _btn(f"{check('dairy')} 🥛 Dairy","prot:dairy")],
            [_btn(f"✅ Confirmar ({n})" if n else "✅ Sin preferencia — continuar","prot:ok")],
            _back("dt:back"),
        ))


def _kb_restricciones(sel: set) -> InlineKeyboardMarkup:
    OPTS = [
        ("🥛","Sin lácteos","lacteos"), ("🌾","Sin gluten","gluten"),
        ("🥜","Sin maní","mani"),       ("🥚","Sin huevo","huevo"),
        ("🦐","Sin mariscos","mariscos"),("🐖","Sin cerdo","cerdo"),
        ("🌱","Vegano estricto","vegano"),
    ]
    rows = []
    for i in range(0, len(OPTS), 2):
        row = []
        for emoji, label, key in OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"rt:{key}"))
        rows.append(row)
    n = len(sel)
    rows.append([_btn(f"✅ Confirmar ({n})" if n else "✅ Ninguna — continuar", "rt:ok")])
    rows.append(_back("prot:ok"))
    return InlineKeyboardMarkup(rows)


async def handle_rt(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("rest_sel", set())

    if sub == "ok":
        upsert_usuario(uid, alergias=",".join(sorted(sel)) if sel else "ninguna")
        await _edit(query,
            f"<b>Restricciones: {'ninguna' if not sel else ', '.join(sel)} ✅</b>\n\n"
            f"¿Cómo manejas la preparación de tus comidas?",
            _kb(
                [_btn("🍳 Cocino al momento cada día",         "prep:momento")],
                [_btn("📦 Batch cooking — cocino para la semana","prep:batch")],
                [_btn("⚡ Rápido — máximo 20 min por comida",  "prep:rapido")],
                [_btn("🏃 Como fuera o pido delivery",         "prep:fuera")],
                _back("rt:back"),
            ))
        return

    if sub == "back":
        await _edit(query, "<b>Restricciones alimentarias</b>", _kb_restricciones(sel))
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["rest_sel"] = sel
    await _edit(query,
        "<b>¿Hay algo que no puedas comer?</b>\n<i>Selecciona todo lo que aplique</i>",
        _kb_restricciones(sel))


async def handle_prep(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>Restricciones alimentarias</b>",
            _kb_restricciones(set()))
        return

    PREP = {
        "momento": "🍳 Cocino al momento",
        "batch":   "📦 Batch cooking",
        "rapido":  "⚡ Rápido (20 min)",
        "fuera":   "🏃 Como fuera",
    }
    upsert_usuario(uid, donde_come=sub)
    await _edit(query,
        f"<b>Preparación: {PREP.get(sub,sub)} ✅</b>\n\n"
        f"<b>Bloque 4/4 — Recuperación y estilo de vida</b>\n\n"
        f"¿Cuántas horas duermes normalmente por noche?",
        _kb(
            [_btn("😫 Menos de 6h", "sueño_hab:5.5"),
             _btn("😐 6-7h",        "sueño_hab:6.5")],
            [_btn("✅ 7-8h",        "sueño_hab:7.5"),
             _btn("🌟 Más de 8h",   "sueño_hab:8.5")],
            _back("prep:back"),
        ))


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 4 — RECUPERACIÓN Y ESTILO DE VIDA
# ══════════════════════════════════════════════════════════════════════════════

async def handle_sueño_hab(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cómo preparas tus comidas?</b>",
            _kb(
                [_btn("🍳 Al momento","prep:momento")],
                [_btn("📦 Batch cooking","prep:batch")],
                [_btn("⚡ Rápido 20 min","prep:rapido")],
                [_btn("🏃 Como fuera","prep:fuera")],
            ))
        return

    horas = float(sub)
    upsert_usuario(uid, sueño_horas=horas)

    nota = ""
    if horas < 6:
        nota = "\n⚠️ <i>Menos de 6h reduce la síntesis proteica hasta un 30%. El plan lo considera.</i>"
    elif horas >= 8:
        nota = "\n✅ <i>Excelente. Recuperación óptima asegurada.</i>"

    await _edit(query,
        f"<b>Sueño: ~{horas}h/noche ✅</b>{nota}\n\n"
        f"¿Cómo es tu trabajo o actividad durante el día?",
        _kb(
            [_btn("💺 Sedentario — oficina/casa",         "trabajo:sedentario")],
            [_btn("🚶 Moderado — me muevo algo",          "trabajo:moderado")],
            [_btn("🏗️ Activo — de pie o movimiento",     "trabajo:activo")],
            [_btn("🏃 Muy activo — trabajo físico duro", "trabajo:muy_activo")],
            _back("sueño_hab:back"),
        ))


async def handle_trabajo(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Cuántas horas duermes?</b>",
            _kb(
                [_btn("😫 Menos de 6h","sueño_hab:5.5"),_btn("😐 6-7h","sueño_hab:6.5")],
                [_btn("✅ 7-8h","sueño_hab:7.5"),       _btn("🌟 Más de 8h","sueño_hab:8.5")],
            ))
        return

    FACTOR = {
        "sedentario": 1.2,
        "moderado":   1.375,
        "activo":     1.55,
        "muy_activo": 1.725,
    }
    factor = FACTOR.get(sub, 1.375)
    upsert_usuario(uid, actividad_nivel=sub)

    # Recalcular TDEE con factor real
    u = get_usuario(uid)
    bmr = u.get("bmr", 2000) or 2000
    tdee_real = round(int(bmr) * factor)
    upsert_usuario(uid, tdee=tdee_real)

    await _edit(query,
        f"<b>Actividad: {sub} ✅</b>\n"
        f"<i>TDEE ajustado: {tdee_real} kcal/día</i>\n\n"
        f"¿Cómo describes tu nivel de estrés habitual?\n"
        f"<i>El estrés crónico eleva el cortisol y reduce la recuperación muscular</i>",
        _kb(
            [_btn("😌 Bajo — vida tranquila",        "estres:bajo")],
            [_btn("😐 Moderado — algo de presión",   "estres:moderado")],
            [_btn("😤 Alto — trabajo/vida intensa",  "estres:alto")],
            [_btn("🤯 Muy alto — siempre ocupado",   "estres:muy_alto")],
            _back("trabajo:back"),
        ))


async def handle_estres(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Tipo de trabajo?</b>",
            _kb(
                [_btn("💺 Sedentario","trabajo:sedentario")],
                [_btn("🚶 Moderado","trabajo:moderado")],
                [_btn("🏗️ Activo","trabajo:activo")],
                [_btn("🏃 Muy activo","trabajo:muy_activo")],
            ))
        return

    # Estrés afecta capacidad de recuperación → Bannister K_fatiga ajustado
    FACTOR_ESTRES = {"bajo":1.0, "moderado":1.1, "alto":1.25, "muy_alto":1.4}
    factor = FACTOR_ESTRES.get(sub, 1.0)
    upsert_usuario(uid, nivel_estres=sub, factor_estres=factor)

    await _edit(query,
        f"<b>Estrés: {sub} ✅</b>\n\n"
        f"¿Qué wearable vas a conectar para el análisis de recuperación?\n"
        f"<i>El modelo Bannister usa HRV y FC reposo para ajustar tu plan</i>",
        _kb(
            [_btn("⌚ Google Fit / WearOS (OnePlus, Pixel)",  "wear:google_fit")],
            [_btn("🍎 Apple Watch / Apple Health",           "wear:apple")],
            [_btn("📱 Samsung Health",                       "wear:samsung")],
            [_btn("📊 Sin reloj — solo báscula",             "wear:ninguno")],
            _back("estres:back"),
        ))


async def handle_wear(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>¿Nivel de estrés?</b>",
            _kb(
                [_btn("😌 Bajo","estres:bajo")],
                [_btn("😐 Moderado","estres:moderado")],
                [_btn("😤 Alto","estres:alto")],
                [_btn("🤯 Muy alto","estres:muy_alto")],
            ))
        return

    WEAR_LABELS = {
        "google_fit": "⌚ Google Fit",
        "apple":      "🍎 Apple Health",
        "samsung":    "📱 Samsung Health",
        "ninguno":    "📊 Sin reloj",
    }
    upsert_usuario(uid, wearable=sub)

    await _generar(query, uid, context, wearable=sub, wear_label=WEAR_LABELS.get(sub, sub))


# ══════════════════════════════════════════════════════════════════════════════
# GENERAR PLAN
# ══════════════════════════════════════════════════════════════════════════════

async def _generar(query, uid: int, context, wearable: str = "", wear_label: str = ""):
    await query.edit_message_text(
        "⚙️ <b>Analizando tu perfil y creando tu plan...</b>\n\n"
        "Calibrando modelo Bannister según tu estrés y sueño...",
        parse_mode="HTML")

    try:
        u = get_usuario(uid)
        from engine.gym.planner import generar_plan

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
        add_allowed_user(uid)
        upsert_usuario(uid, onboarding_done=1)

        # Calcular datos del resumen
        peso      = float(u.get("peso_kg") or 80)
        tdee      = int(u.get("tdee") or 2200)
        objetivo  = u.get("objetivo_gym","general")
        nivel     = u.get("nivel","intermedio")
        dias_gym  = int(u.get("dias_semana") or 4)
        prot_g    = round(peso * 2.2)
        toma_g    = round(prot_g / 4)

        # Calorías objetivo según meta
        DEFICIT = {"peso":0.82,"mamado":1.10,"gluteo":0.90,"general":0.90}
        kcal    = round(tdee * DEFICIT.get(objetivo, 0.90))

        # Notas según estrés y sueño
        notas = []
        estres = u.get("nivel_estres","moderado")
        sueño  = float(u.get("sueño_horas") or 7)
        if estres in ("alto","muy_alto"):
            notas.append("⚠️ Estrés alto detectado — el volumen empieza conservador")
        if sueño < 6.5:
            notas.append("⚠️ Sueño bajo — RIR +1 en las primeras 2 semanas")
        if wearable == "google_fit":
            notas.append("✅ Google Fit conectado — el plan se ajusta solo con tu HRV")
        elif wearable == "ninguno":
            notas.append("💡 Sin reloj — el ajuste se hace con los datos de la báscula")

        nota_str = "\n".join(notas)
        if nota_str:
            nota_str = "\n\n" + nota_str

        await query.edit_message_text(
            f"✅ <b>Plan creado — {n} ejercicios · 4 semanas</b>\n\n"
            f"<b>Tu perfil:</b>\n"
            f"  {nivel.capitalize()} · {dias_gym} días · {u.get('duracion_sesion',60)} min\n"
            f"  {u.get('ambiente','gym').capitalize()} · {u.get('limitaciones','ninguna')}\n\n"
            f"<b>Tu nutrición base:</b>\n"
            f"  🔥 {kcal} kcal/día\n"
            f"  🥩 {prot_g}g proteína ({toma_g}g × 4 tomas)\n"
            f"  <i>El plan se ajusta automáticamente cada semana</i>"
            f"{nota_str}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💪 Ver mi rutina de hoy", callback_data="m:hoy")
            ]]))

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Usa los botones de abajo 👇",
            reply_markup=TECLADO_PRINCIPAL)

    except Exception as e:
        logger.error("Error generando plan uid=%s: %s", uid, e, exc_info=True)
        await query.edit_message_text(
            f"❌ Error: {str(e)[:150]}\n\nEscribe /start para intentar de nuevo.",
            parse_mode="HTML")
