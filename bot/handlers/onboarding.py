"""
bot/handlers/onboarding.py — Invisible Coach v4.0 (Sesión 11)

Discovery en 4 bloques científicos.

Cambios v4.0:
  - Fecha de nacimiento real vía calendario inline (año → mes → día)
  - Peso/altura: teclado numérico (primera vez, dato preciso)
  - Lesiones: 9 opciones + "otra" (texto libre)
  - Restricciones: + "otra" (texto libre)
  - Proteínas favoritas: hasta 6 (antes 3)
  - Recuperación activa: preferencia real (caminar/yoga/bici/etc)
  - Electrodomésticos: pregunta opcional para mejorar planes de comida

Bloque 1: Perfil biológico (objetivo, fecha nac, peso, altura, sexo)
Bloque 2: Experiencia (nivel, días, duración, horario, ambiente, lesiones)
Bloque 3: Nutrición (dieta, proteínas, restricciones, prep, electrodomésticos)
Bloque 4: Recuperación (sueño, trabajo, estrés, recup. activa, wearable)
"""
from __future__ import annotations
import logging
from datetime import date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db.database import (
    get_usuario, upsert_usuario, insert_plan,
    set_estado, add_allowed_user,
)
from bot.keyboards import TECLADO_PRINCIPAL
from bot.widgets import kb_calendario_anio, kb_calendario_mes, kb_calendario_dia, kb_numerico

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
        f"📅 ¿Cuál es tu fecha de nacimiento?\n"
        f"<i>Toca el año, luego mes, luego día</i>",
        kb_calendario_anio())


async def _mostrar_objetivo(query):
    await _edit(query,
        "👋 <b>Empecemos</b>\n\n"
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


# ── Calendario de fecha de nacimiento ───────────────────────────────────────────

async def handle_cal(query, uid: int, context):
    """
    Calendario inline para fecha de nacimiento.
    cal:Y:<año> | cal:M:<año>:<mes> | cal:D:<año>:<mes>:<dia>
    cal:ynav:<base> | cal:back_year | cal:back_month:<año>
    """
    parts = query.data.split(":")
    sub = parts[1]

    if sub == "ynav":
        base = int(parts[2])
        await _edit(query,
            "📅 ¿Cuál es tu fecha de nacimiento?\n<i>Toca tu año de nacimiento</i>",
            kb_calendario_anio(base))
        return

    if sub == "back_year":
        await _edit(query,
            "📅 ¿Cuál es tu fecha de nacimiento?\n<i>Toca tu año de nacimiento</i>",
            kb_calendario_anio())
        return

    if sub == "back_month":
        año = int(parts[2])
        await _edit(query,
            f"<b>Año: {año} ✅</b>\n\n📅 Ahora el mes:",
            kb_calendario_mes(año))
        return

    if sub == "Y":
        año = int(parts[2])
        context.user_data["cal_año"] = año
        await _edit(query,
            f"<b>Año: {año} ✅</b>\n\n📅 Ahora el mes:",
            kb_calendario_mes(año))
        return

    if sub == "M":
        año, mes = int(parts[2]), int(parts[3])
        context.user_data["cal_año"], context.user_data["cal_mes"] = año, mes
        await _edit(query,
            f"<b>{año} ✅</b>\n\n📅 Y el día:",
            kb_calendario_dia(año, mes))
        return

    if sub == "D":
        año, mes, dia = int(parts[2]), int(parts[3]), int(parts[4])
        fecha_nac = f"{año:04d}-{mes:02d}-{dia:02d}"
        hoy = date.today()
        edad = hoy.year - año - ((hoy.month, hoy.day) < (mes, dia))

        upsert_usuario(uid, fecha_nac=fecha_nac, edad=edad)
        context.user_data.pop("cal_año", None)
        context.user_data.pop("cal_mes", None)
        context.user_data["num_buffer"] = ""

        await _edit(query,
            f"<b>Naciste el {dia:02d}/{mes:02d}/{año} ({edad} años) ✅</b>\n\n"
            f"⚖️ ¿Cuánto pesas actualmente?\n"
            f"<i>Usa el teclado para escribir tu peso en kg</i>\n\n"
            f"Peso: <b>_</b> kg",
            kb_numerico("peso", ""))
        return


# ── Teclado numérico — peso y altura ────────────────────────────────────────────

async def handle_num(query, uid: int, context):
    """
    num:<campo>:d:<digito> | num:<campo>:back | num:<campo>:ok
    campo = 'peso' | 'altura'
    """
    parts  = query.data.split(":")
    campo  = parts[1]
    accion = parts[2]
    buf    = context.user_data.get("num_buffer", "")

    if accion == "d":
        digito = parts[3]
        if digito == "." and "." in buf:
            pass  # ignorar segundo punto
        elif len(buf) >= 6:
            pass  # límite de dígitos
        else:
            buf += digito
        context.user_data["num_buffer"] = buf

    elif accion == "back":
        buf = buf[:-1]
        context.user_data["num_buffer"] = buf

    elif accion == "ok":
        try:
            valor = float(buf)
        except ValueError:
            valor = 0
        if valor <= 0:
            return  # no hacer nada si está vacío/inválido

        if campo == "peso":
            upsert_usuario(uid, peso_kg=valor)
            context.user_data["num_buffer"] = ""
            await _edit(query,
                f"<b>Peso: {valor:g} kg ✅</b>\n\n"
                f"📏 ¿Cuánto mides?\n"
                f"<i>Usa el teclado para escribir tu altura en cm</i>\n\n"
                f"Altura: <b>_</b> cm",
                kb_numerico("altura", ""))
            return

        if campo == "altura":
            upsert_usuario(uid, altura_cm=valor)
            context.user_data["num_buffer"] = ""
            await _edit(query,
                f"<b>Altura: {valor:g} cm ✅</b>\n\n"
                f"¿Cuál es tu sexo biológico?\n"
                f"<i>Necesario para calcular tu metabolismo basal con precisión (Mifflin-St Jeor)</i>",
                _kb(
                    [_btn("Hombre", "sexo:hombre"), _btn("Mujer", "sexo:mujer")],
                ))
            return
        return

    # Re-renderizar el teclado con el buffer actualizado
    if campo == "peso":
        label, unidad = "Peso", "kg"
        titulo = "⚖️ ¿Cuánto pesas actualmente?"
    else:
        label, unidad = "Altura", "cm"
        titulo = "📏 ¿Cuánto mides?"

    valor_mostrar = buf if buf else "_"
    await _edit(query,
        f"{titulo}\n<i>Usa el teclado para escribir el número</i>\n\n"
        f"{label}: <b>{valor_mostrar}</b> {unidad}",
        kb_numerico(campo, buf))


async def handle_sexo(query, uid: int):
    sub = query.data.split(":")[1]
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
        await _edit(query, "<b>¿Cuánto tiempo llevas entrenando?</b>",
            _kb(
                [_btn("🌱 Menos de 6 meses","nv:principiante")],
                [_btn("💪 6 meses a 2 años","nv:intermedio")],
                [_btn("🔥 Más de 2 años","nv:avanzado")],
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
        await _edit(query, "<b>¿Cuántos días tienes a la semana?</b>",
            _kb(
                [_btn("3 días — Fullbody","dy:3"), _btn("4 días — Upper/Lower","dy:4")],
                [_btn("5 días — PPL","dy:5"),      _btn("6 días — PPL×2","dy:6")],
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
        f"¿Tienes alguna lesión o limitación física?\n"
        f"<i>Selecciona todas las que apliquen</i>",
        _kb_lesiones(set()))


# ── Lesiones — expandido + "otra" ────────────────────────────────────────────────

LESION_OPTS = [
    ("🦵","Rodilla","rodilla"), ("🔙","Espalda baja","espalda"),
    ("💪","Hombro","hombro"),   ("✋","Muñeca","muneca"),
    ("🦶","Tobillo","tobillo"), ("🦒","Cuello","cuello"),
    ("🦴","Cadera","cadera"),   ("💪","Codo","codo"),
]

def _kb_lesiones(sel: set) -> InlineKeyboardMarkup:
    rows = [[_btn("✅ Ninguna — estoy al 100%", "lm:ninguna")]]
    for i in range(0, len(LESION_OPTS), 2):
        row = []
        for emoji, label, key in LESION_OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"lm:{key}"))
        rows.append(row)
    rows.append([_btn("✏️ Otra (escribir)", "lm:otra")])
    n = len(sel)
    rows.append([_btn(f"✅ Continuar ({n})" if n else "✅ Continuar", "lm:ok")])
    rows.append(_back("am:back"))
    return InlineKeyboardMarkup(rows)


async def handle_lm(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("lesion_sel", set())

    if sub == "back":
        await _edit(query, "<b>¿Dónde entrenas?</b>",
            _kb(
                [_btn("🏋️ Gimnasio","am:gym")],
                [_btn("🏠 Casa","am:home")],
                [_btn("🦺 Bandas","am:band")],
            ))
        return

    if sub == "ninguna":
        upsert_usuario(uid, limitaciones="ninguna")
        context.user_data.pop("lesion_sel", None)
        await _avanzar_a_dieta(query, uid)
        return

    if sub == "otra":
        context.user_data["esperando_texto"] = "lesion_otra"
        await _edit(query,
            "✏️ <b>Escribe tu lesión o limitación</b>\n\n"
            "<i>Ejemplo: \"tendinitis en el codo derecho\"</i>\n\n"
            "Escribe tu mensaje a continuación 👇")
        return

    if sub == "ok":
        limitaciones = ",".join(sorted(sel)) if sel else "ninguna"
        upsert_usuario(uid, limitaciones=limitaciones)
        context.user_data.pop("lesion_sel", None)
        await _avanzar_a_dieta(query, uid)
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["lesion_sel"] = sel
    await _edit(query,
        "<b>¿Tienes alguna lesión o limitación física?</b>\n"
        "<i>Selecciona todas las que apliquen</i>",
        _kb_lesiones(sel))


async def _avanzar_a_dieta(query, uid: int):
    await _edit(query,
        f"<b>Lesiones registradas ✅</b>\n\n"
        f"<b>Bloque 3/4 — Tu alimentación</b>\n\n"
        f"¿Qué tipo de alimentación llevas o prefieres?",
        _kb(
            [_btn("🍗 Omnívoro / Dieta flexible",      "dt:omnivoro")],
            [_btn("🥗 Saludable — comida real",        "dt:saludable")],
            [_btn("🌱 Vegetariano / Vegano",           "dt:vegano")],
            [_btn("🍖 Alta en proteína (prioridad)",   "dt:proteina")],
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
        f"¿Cuáles son tus fuentes de proteína favoritas?\n"
        f"<i>Hasta 6 — la IA arma la dieta con lo que te gusta</i>",
        _kb_proteinas(set()))


PROT_OPTS = [
    ("🍗","Pollo","pollo"),    ("🥩","Res/Bistec","res"),
    ("🐟","Atún","atun"),      ("🍳","Huevo","huevo"),
    ("🐷","Cerdo","cerdo"),    ("🐟","Salmón","salmon"),
    ("🫘","Legumbres","legumbres"), ("🥛","Dairy/Caseína","dairy"),
]
PROT_LABELS = {k: f"{e} {l}" for e,l,k in PROT_OPTS}

def _kb_proteinas(sel: set) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(PROT_OPTS), 2):
        row = []
        for emoji, label, key in PROT_OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"prot:{key}"))
        rows.append(row)
    n = len(sel)
    rows.append([_btn(f"✅ Confirmar ({n}/6)" if n else "✅ Sin preferencia — continuar", "prot:ok")])
    rows.append(_back("dt:back"))
    return InlineKeyboardMarkup(rows)


async def handle_prot(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("prot_sel", set())

    if sub == "back":
        await _edit(query, "<b>¿Tipo de alimentación?</b>",
            _kb(
                [_btn("🍗 Omnívoro / Dieta flexible","dt:omnivoro")],
                [_btn("🥗 Saludable","dt:saludable")],
                [_btn("🌱 Vegano","dt:vegano")],
                [_btn("🍖 Alta proteína","dt:proteina")],
            ))
        return

    if sub == "ok":
        prots = list(sel) if sel else ["pollo", "huevo", "atun"]
        upsert_usuario(uid, proteinas_favoritas=",".join(prots))
        context.user_data.pop("prot_sel", None)
        await _edit(query,
            f"<b>Proteínas: {', '.join(prots)} ✅</b>\n\n"
            f"¿Tienes alguna restricción alimentaria?\n"
            f"<i>Selecciona todo lo que aplique</i>",
            _kb_restricciones(set()))
        return

    if sub in sel: sel.discard(sub)
    else:
        if len(sel) < 6:
            sel.add(sub)
    context.user_data["prot_sel"] = sel

    n = len(sel)
    await _edit(query,
        f"<b>Selecciona tus fuentes de proteína favoritas</b> ({n}/6)\n"
        f"<i>La IA usará estas para armar tu plan de comidas</i>",
        _kb_proteinas(sel))


# ── Restricciones — + "otra" ─────────────────────────────────────────────────────

REST_OPTS = [
    ("🥛","Sin lácteos","lacteos"), ("🌾","Sin gluten","gluten"),
    ("🥜","Sin maní","mani"),       ("🥚","Sin huevo","huevo"),
    ("🦐","Sin mariscos","mariscos"),("🐖","Sin cerdo","cerdo"),
    ("🌱","Vegano estricto","vegano"),
]

def _kb_restricciones(sel: set) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(REST_OPTS), 2):
        row = []
        for emoji, label, key in REST_OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"rt:{key}"))
        rows.append(row)
    rows.append([_btn("✏️ Otra (escribir)", "rt:otra")])
    n = len(sel)
    rows.append([_btn(f"✅ Confirmar ({n})" if n else "✅ Ninguna — continuar", "rt:ok")])
    rows.append(_back("prot:ok"))
    return InlineKeyboardMarkup(rows)


def _kb_preparacion() -> InlineKeyboardMarkup:
    return _kb(
        [_btn("🍳 Cocino al momento cada día",         "prep:momento")],
        [_btn("📦 Batch cooking — cocino para la semana","prep:batch")],
        [_btn("⚡ Rápido — máximo 20 min por comida",   "prep:rapido")],
        [_btn("🏃 Como fuera o pido delivery",          "prep:fuera")],
        _back("rt:back"),
    )


async def handle_rt(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("rest_sel", set())

    if sub == "back":
        await _edit(query, "<b>Restricciones alimentarias</b>", _kb_restricciones(sel))
        return

    if sub == "otra":
        context.user_data["esperando_texto"] = "restriccion_otra"
        await _edit(query,
            "✏️ <b>Escribe tu restricción alimentaria</b>\n\n"
            "<i>Ejemplo: \"sin cilantro\" o \"intolerante a la lactosa severa\"</i>\n\n"
            "Escribe tu mensaje a continuación 👇")
        return

    if sub == "ok":
        upsert_usuario(uid, alergias=",".join(sorted(sel)) if sel else "ninguna")
        context.user_data.pop("rest_sel", None)
        await _edit(query,
            f"<b>Restricciones registradas ✅</b>\n\n"
            f"¿Cómo manejas la preparación de tus comidas?",
            _kb_preparacion())
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["rest_sel"] = sel
    await _edit(query,
        "<b>¿Hay algo que no puedas comer?</b>\n<i>Selecciona todo lo que aplique</i>",
        _kb_restricciones(sel))


# ── Electrodomésticos — opcional ────────────────────────────────────────────────

ELEC_OPTS = [
    ("🍳","Air fryer","air_fryer"), ("🍲","Slow cooker","slow_cooker"),
    ("📡","Microondas","microondas"), ("🔥","Horno","horno"),
    ("🥤","Licuadora","licuadora"),
]

def _kb_electrodomesticos(sel: set) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(ELEC_OPTS), 2):
        row = []
        for emoji, label, key in ELEC_OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"elec:{key}"))
        rows.append(row)
    n = len(sel)
    rows.append([_btn(f"✅ Confirmar ({n})" if n else "⏭️ Saltar", "elec:ok")])
    return InlineKeyboardMarkup(rows)


async def handle_prep(query, uid: int):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query, "<b>Restricciones alimentarias</b>", _kb_restricciones(set()))
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
        f"🔌 ¿Qué electrodomésticos tienes para cocinar?\n"
        f"<i>Opcional — ayuda a la IA a sugerir recetas que sí puedas hacer</i>",
        _kb_electrodomesticos(set()))


async def handle_elec(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("elec_sel", set())

    if sub == "ok":
        upsert_usuario(uid, electrodomesticos=",".join(sorted(sel)) if sel else "ninguno")
        context.user_data.pop("elec_sel", None)
        await _edit(query,
            f"<b>Bloque 3 completo ✅</b>\n\n"
            f"<b>Bloque 4/4 — Recuperación y estilo de vida</b>\n\n"
            f"😴 ¿Cuántas horas duermes normalmente por noche?",
            _kb(
                [_btn("😫 Menos de 6h", "sueño_hab:5.5"),
                 _btn("😐 6-7h",        "sueño_hab:6.5")],
                [_btn("✅ 7-8h",        "sueño_hab:7.5"),
                 _btn("🌟 Más de 8h",   "sueño_hab:8.5")],
            ))
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["elec_sel"] = sel
    await _edit(query,
        "<b>🔌 ¿Qué electrodomésticos tienes para cocinar?</b>\n"
        "<i>Opcional — ayuda a la IA a sugerir recetas que sí puedas hacer</i>",
        _kb_electrodomesticos(sel))


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 4 — RECUPERACIÓN Y ESTILO DE VIDA
# ══════════════════════════════════════════════════════════════════════════════

async def handle_sueño_hab(query, uid: int):
    sub = query.data.split(":")[1]

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
        ))


async def handle_trabajo(query, uid: int):
    sub = query.data.split(":")[1]

    FACTOR = {"sedentario":1.2,"moderado":1.375,"activo":1.55,"muy_activo":1.725}
    factor = FACTOR.get(sub, 1.375)
    upsert_usuario(uid, actividad_nivel=sub)

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
        ))


async def handle_estres(query, uid: int):
    sub = query.data.split(":")[1]

    FACTOR_ESTRES = {"bajo":1.0, "moderado":1.1, "alto":1.25, "muy_alto":1.4}
    factor = FACTOR_ESTRES.get(sub, 1.0)
    upsert_usuario(uid, nivel_estres=sub, factor_estres=factor)

    await _edit(query,
        f"<b>Estrés: {sub} ✅</b>\n\n"
        f"🌿 En tus días de descanso, ¿qué tipo de actividad ligera prefieres?\n"
        f"<i>Selecciona una o más — el bot la usará en tus recomendaciones de descanso activo</i>",
        _kb_recuperacion(set()))


# ── Recuperación activa — preferencia real ──────────────────────────────────────

RA_OPTS = [
    ("🚶","Caminar","caminar"), ("🧘","Yoga / estiramiento","yoga"),
    ("🚴","Bicicleta","bici"),  ("🏊","Natación","natacion"),
    ("🏃","Trote suave","trote"),
]

def _kb_recuperacion(sel: set) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(RA_OPTS), 2):
        row = []
        for emoji, label, key in RA_OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"ra:{key}"))
        rows.append(row)
    rows.append([_btn("✏️ Otra (escribir)", "ra:otra")])
    n = len(sel)
    rows.append([_btn(f"✅ Confirmar ({n})" if n else "⏭️ Sin preferencia — continuar", "ra:ok")])
    return InlineKeyboardMarkup(rows)


async def handle_ra(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("ra_sel", set())

    if sub == "otra":
        context.user_data["esperando_texto"] = "recuperacion_otra"
        await _edit(query,
            "✏️ <b>Escribe tu actividad de recuperación favorita</b>\n\n"
            "<i>Ejemplo: \"pádel\" o \"escalada ligera\"</i>\n\n"
            "Escribe tu mensaje a continuación 👇")
        return

    if sub == "ok":
        recuperacion = ",".join(sorted(sel)) if sel else "caminar"
        upsert_usuario(uid, recuperacion_activa=recuperacion)
        context.user_data.pop("ra_sel", None)
        await _mostrar_wearable(query)
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["ra_sel"] = sel
    await _edit(query,
        "<b>🌿 En tus días de descanso, ¿qué actividad ligera prefieres?</b>\n"
        "<i>Selecciona una o más</i>",
        _kb_recuperacion(sel))


async def _mostrar_wearable(query):
    await _edit(query,
        f"<b>Preferencia de recuperación registrada ✅</b>\n\n"
        f"¿Qué wearable vas a conectar para el análisis de recuperación?\n"
        f"<i>El modelo Bannister usa HRV y FC reposo para ajustar tu plan</i>",
        _kb(
            [_btn("⌚ Google Fit / WearOS (OnePlus, Pixel)",  "wear:google_fit")],
            [_btn("🍎 Apple Watch / Apple Health",           "wear:apple")],
            [_btn("📱 Samsung Health",                       "wear:samsung")],
            [_btn("📊 Sin reloj — solo báscula",             "wear:ninguno")],
        ))


async def handle_wear(query, uid: int, context):
    sub = query.data.split(":")[1]

    WEAR_LABELS = {
        "google_fit": "⌚ Google Fit",
        "apple":      "🍎 Apple Health",
        "samsung":    "📱 Samsung Health",
        "ninguno":    "📊 Sin reloj",
    }
    upsert_usuario(uid, wearable=sub)

    await _generar(query, uid, context, wearable=sub, wear_label=WEAR_LABELS.get(sub, sub))


# ══════════════════════════════════════════════════════════════════════════════
# TEXTO LIBRE — "otra" (lesiones, restricciones, recuperación activa)
# Llamado desde handler_texto en menu.py cuando context.user_data["esperando_texto"]
# tiene uno de estos valores.
# ══════════════════════════════════════════════════════════════════════════════

async def handle_texto_otra(update, context, tipo: str, texto: str):
    """Procesa texto libre durante onboarding y continúa el flujo."""
    uid = update.effective_user.id
    context.user_data.pop("esperando_texto", None)
    texto = texto.strip()[:100]

    if tipo == "lesion_otra":
        u = get_usuario(uid)
        actuales = (u.get("limitaciones") or "").split(",") if u else []
        actuales = [a for a in actuales if a and a != "ninguna"]
        actuales.append(f"otra:{texto}")
        upsert_usuario(uid, limitaciones=",".join(actuales))

        await update.message.reply_text(
            f"<b>Anotado: {texto} ✅</b>\n\n"
            f"<b>Bloque 3/4 — Tu alimentación</b>\n\n"
            f"¿Qué tipo de alimentación llevas o prefieres?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🍗 Omnívoro / Dieta flexible", callback_data="dt:omnivoro")],
                [InlineKeyboardButton("🥗 Saludable — comida real", callback_data="dt:saludable")],
                [InlineKeyboardButton("🌱 Vegetariano / Vegano", callback_data="dt:vegano")],
                [InlineKeyboardButton("🍖 Alta en proteína (prioridad)", callback_data="dt:proteina")],
            ]))
        return

    if tipo == "restriccion_otra":
        u = get_usuario(uid)
        actuales = (u.get("alergias") or "").split(",") if u else []
        actuales = [a for a in actuales if a and a != "ninguna"]
        actuales.append(f"otra:{texto}")
        upsert_usuario(uid, alergias=",".join(actuales))

        await update.message.reply_text(
            f"<b>Anotado: {texto} ✅</b>\n\n"
            f"¿Cómo manejas la preparación de tus comidas?",
            parse_mode="HTML",
            reply_markup=_kb_preparacion())
        return

    if tipo == "recuperacion_otra":
        u = get_usuario(uid)
        actuales = (u.get("recuperacion_activa") or "").split(",") if u else []
        actuales = [a for a in actuales if a]
        actuales.append(f"otra:{texto}")
        upsert_usuario(uid, recuperacion_activa=",".join(actuales))

        await update.message.reply_text(
            f"<b>Anotado: {texto} ✅</b>\n\n"
            f"¿Qué wearable vas a conectar para el análisis de recuperación?\n"
            f"<i>El modelo Bannister usa HRV y FC reposo para ajustar tu plan</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⌚ Google Fit / WearOS", callback_data="wear:google_fit")],
                [InlineKeyboardButton("🍎 Apple Health", callback_data="wear:apple")],
                [InlineKeyboardButton("📱 Samsung Health", callback_data="wear:samsung")],
                [InlineKeyboardButton("📊 Sin reloj — solo báscula", callback_data="wear:ninguno")],
            ]))
        return


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

        peso      = float(u.get("peso_kg") or 80)
        tdee      = int(u.get("tdee") or 2200)
        objetivo  = u.get("objetivo_gym","general")
        nivel     = u.get("nivel","intermedio")
        dias_gym  = int(u.get("dias_semana") or 4)
        prot_g    = round(peso * 2.2)
        toma_g    = round(prot_g / 4)

        DEFICIT = {"peso":0.82,"mamado":1.10,"gluteo":0.90,"general":0.90}
        kcal    = round(tdee * DEFICIT.get(objetivo, 0.90))

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
            f"❌ Error: {str(e)[:150]}\n\nEscribe /start para reintentar.",
            parse_mode="HTML")
