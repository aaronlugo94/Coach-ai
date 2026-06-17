"""
bot/handlers/onboarding.py — Invisible Coach v5.0 (Fase 2)

Flujo nuevo:
  1. Bienvenida — 1 mensaje + botón Empezar
  2. Wearable primero — si conecta Google Fit y tiene datos, salta
     peso/altura/sueño automáticamente
  3. Bloque 1 — Objetivo (con descripción), fecha nacimiento, sexo,
     peso/altura (solo si no vino de Fit)
  4. Bloque 2 — Experiencia: nivel, días, duración, horario, ambiente, lesiones
  5. Bloque 3 — Alimentación: tipo dieta (con explicación), cocinas favoritas,
     número de comidas, tiempo por comida (desayuno/comida/cena), proteínas
     sin límite, restricciones, suplementos, alcohol, electrodomésticos (todos
     marcados por default, desmarcar lo que no tienen)
  6. Bloque 4 — Recuperación: estrés, trabajo, recuperación activa
  7. Final — "¿Qué quieres? 💪 Rutina / 🥗 Dieta / 🔄 Los dos"
     → genera plan inmediatamente
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
            logger.warning("_edit error: %s", e)

def _btn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)

def _kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(list(rows))

def _back(data: str) -> list:
    return [_btn("← Atrás", data)]


# ══════════════════════════════════════════════════════════════════════════════
# INICIO — Bienvenida + Wearable primero
# ══════════════════════════════════════════════════════════════════════════════

async def handle_bienvenida(query, uid: int, context):
    """Botón 'Empezar →' del mensaje de bienvenida → pregunta wearable."""
    sub = query.data.split(":")[1] if ":" in query.data else query.data

    if sub != "start":
        return

    await _edit(query,
        "<b>Primero — conecta tu reloj o app de salud</b>\n\n"
        "Si tienes datos de peso, altura y sueño en una app, "
        "puedo importarlos automáticamente y saltar esas preguntas.\n\n"
        "¿Qué dispositivo usas?",
        _kb(
            [_btn("⌚ Google Fit / WearOS", "wear_init:google_fit")],
            [_btn("🍎 Apple Health",        "wear_init:apple")],
            [_btn("📱 Samsung Health",      "wear_init:samsung")],
            [_btn("📊 Sin reloj — continuar", "wear_init:ninguno")],
        ))


async def handle_wear_init(query, uid: int, context):
    """
    wear_init:<tipo>
    Si es google_fit → manda link de OAuth para conectar.
    El callback de OAuth guardará el token y llamará _continuar_tras_wearable.
    Si es otro → guarda preferencia y continúa manual.
    """
    sub = query.data.split(":")[1]
    upsert_usuario(uid, wearable=sub)

    if sub == "google_fit":
        from engine.body.healthconnect import get_auth_url, esta_conectado
        if esta_conectado(uid):
            # Ya conectado — intentar pre-llenar
            await _edit(query, "⏳ Google Fit ya conectado — importando tus datos...")
            await _prefill_desde_fit(query, uid, context)
            return

        url = get_auth_url(uid)
        await _edit(query,
            "⌚ <b>Conecta Google Fit</b>\n\n"
            "Toca el botón para autorizar. Cuando termines, "
            "regresa aquí y toca <b>Ya conecté</b>.",
            _kb(
                [_btn("🔗 Conectar Google Fit", url)],
                [_btn("✅ Ya conecté — continuar", "wear_check:google_fit")],
                [_btn("⏭ Saltar por ahora", "wear_init:ninguno")],
            ))
        return

    if sub == "apple":
        await _edit(query,
            "🍎 <b>Apple Health</b>\n\n"
            "Por el momento no podemos leer datos de Apple Health "
            "directamente. Ingresarás peso, altura y sueño manualmente — "
            "son solo 3 preguntas rápidas.\n\n"
            "Puedes conectar una báscula Renpho después con /conectar_renpho "
            "para que el bot actualice tu peso automáticamente.",
            _kb([_btn("Continuar →", "wear_init:ninguno")]))
        return

    # samsung o ninguno → continuar manual
    await _mostrar_objetivo(query, uid, context)


async def handle_wear_check(query, uid: int, context):
    """El usuario dice 'Ya conecté' — verificar si el token llegó."""
    sub = query.data.split(":")[1]
    from engine.body.healthconnect import esta_conectado
    if esta_conectado(uid):
        await _edit(query, "⏳ Importando tus datos de Google Fit...")
        await _prefill_desde_fit(query, uid, context)
    else:
        await _edit(query,
            "⚠️ No detecté la conexión todavía.\n\n"
            "Si ya autorizaste, espera unos segundos y toca de nuevo.",
            _kb(
                [_btn("🔄 Verificar de nuevo", f"wear_check:{sub}")],
                [_btn("⏭ Continuar sin wearable", "wear_init:ninguno")],
            ))


async def _prefill_desde_fit(query, uid: int, context):
    """
    Tras conectar Google Fit: trae los últimos 7 días de datos,
    pre-llena peso/altura/sueño y muestra resumen para confirmar.
    """
    from engine.body.healthconnect import sync_usuario
    from datetime import timedelta

    datos = {}
    for i in range(7):
        try:
            d = await sync_usuario(uid, date.today() - timedelta(days=i))
            if d:
                datos.update({k: v for k, v in d.items() if v})
        except Exception:
            pass

    u = get_usuario(uid) or {}
    peso   = float(u.get("peso_kg") or 0)
    sueño  = float(u.get("sueño_horas") or 0)
    # altura no viene de Fit — siempre se pregunta

    if peso > 0:
        context.user_data["fit_peso"]  = peso
        context.user_data["fit_sueño"] = sueño

    lineas = []
    if peso > 0:
        lineas.append(f"⚖️ Peso detectado: <b>{peso:.1f} kg</b>")
    if sueño > 0:
        lineas.append(f"😴 Sueño promedio: <b>{sueño:.1f}h/noche</b>")
    if datos.get("hrv_promedio"):
        lineas.append(f"💚 HRV: <b>{datos['hrv_promedio']} ms</b>")
    if datos.get("fc_reposo"):
        lineas.append(f"❤️ FC reposo: <b>{datos['fc_reposo']} bpm</b>")

    if lineas:
        resumen = "\n".join(lineas)
        await _edit(query,
            f"✅ <b>Google Fit conectado</b>\n\n"
            f"Datos importados:\n{resumen}\n\n"
            f"<i>Nota: la altura necesito que me la digas tú.</i>",
            _kb([_btn("✅ Confirmar y continuar →", "prefill:ok")]))
    else:
        await _edit(query,
            "✅ Google Fit conectado.\n\n"
            "No encontré datos suficientes todavía — "
            "ingresaremos peso y altura manualmente.",
            _kb([_btn("Continuar →", "prefill:ok")]))


async def handle_prefill(query, uid: int, context):
    """Confirmación de datos de Fit — continuar al objetivo."""
    await _mostrar_objetivo(query, uid, context)


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — OBJETIVO + DATOS BIOLÓGICOS
# ══════════════════════════════════════════════════════════════════════════════

async def _mostrar_objetivo(query, uid, context):
    await _edit(query,
        "<b>Bloque 1/4 — Tu objetivo y perfil biológico</b>\n\n"
        "¿Qué quieres lograr en los próximos 90 días?",
        _kb(
            [_btn("⚡ Recomposición — perder grasa Y ganar músculo a la vez",  "ob:recomposicion")],
            [_btn("🔥 Bajar grasa — perder peso reteniendo el músculo",         "ob:deficit")],
            [_btn("💪 Volumen limpio — ganar músculo sin engordar mucho",       "ob:volumen")],
            [_btn("🍑 Glúteo y pierna — enfoque en tren inferior",             "ob:gluteo")],
            [_btn("🏃 Salud y energía — estar activo y sentirme mejor",        "ob:salud")],
        ))


async def handle_ob(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _mostrar_objetivo(query, uid, context)
        return

    MAPA = {
        "recomposicion": ("general", "⚡ Recomposición"),
        "deficit":       ("peso",    "🔥 Bajar grasa"),
        "volumen":       ("mamado",  "💪 Volumen limpio"),
        "gluteo":        ("gluteo",  "🍑 Glúteo y pierna"),
        "salud":         ("general", "🏃 Salud y energía"),
    }
    objetivo_gym, desc = MAPA.get(sub, ("general", sub))
    upsert_usuario(uid, objetivo_vida=sub, objetivo_gym=objetivo_gym)

    await _edit(query,
        f"<b>{desc} ✅</b>\n\n"
        f"📅 ¿Cuándo naciste?\n"
        f"<i>Toca tu año de nacimiento</i>",
        kb_calendario_anio())


# ── Calendario ────────────────────────────────────────────────────────────────

async def handle_cal(query, uid: int, context):
    parts = query.data.split(":")
    sub   = parts[1]

    if sub == "ynav":
        base = int(parts[2])
        await _edit(query,
            "📅 ¿Cuándo naciste?\n<i>Toca tu año</i>",
            kb_calendario_anio(base))
        return

    if sub == "back_year":
        await _edit(query,
            "📅 ¿Cuándo naciste?\n<i>Toca tu año</i>",
            kb_calendario_anio())
        return

    if sub == "back_month":
        año = int(parts[2])
        await _edit(query,
            f"<b>Año: {año} ✅</b>\n\n📅 ¿En qué mes?",
            kb_calendario_mes(año))
        return

    if sub == "Y":
        año = int(parts[2])
        context.user_data["cal_año"] = año
        await _edit(query,
            f"<b>Año: {año} ✅</b>\n\n📅 ¿En qué mes?",
            kb_calendario_mes(año))
        return

    if sub == "M":
        año, mes = int(parts[2]), int(parts[3])
        context.user_data["cal_año"] = año
        context.user_data["cal_mes"] = mes
        await _edit(query,
            f"<b>{año} ✅</b>\n\n📅 ¿Qué día?",
            kb_calendario_dia(año, mes))
        return

    if sub == "D":
        año, mes, dia = int(parts[2]), int(parts[3]), int(parts[4])
        fecha_nac = f"{año:04d}-{mes:02d}-{dia:02d}"
        hoy  = date.today()
        edad = hoy.year - año - ((hoy.month, hoy.day) < (mes, dia))
        upsert_usuario(uid, fecha_nac=fecha_nac, edad=edad)

        context.user_data.pop("cal_año", None)
        context.user_data.pop("cal_mes", None)

        await _edit(query,
            f"<b>{dia:02d}/{mes:02d}/{año} — {edad} años ✅</b>\n\n"
            f"¿Cuál es tu sexo biológico?\n"
            f"<i>Necesario para calcular tu metabolismo basal (Mifflin-St Jeor)</i>",
            _kb(
                [_btn("Hombre", "sexo:hombre"),
                 _btn("Mujer",  "sexo:mujer")],
            ))
        return


# ── Sexo ──────────────────────────────────────────────────────────────────────

async def handle_sexo(query, uid: int, context):
    sub = query.data.split(":")[1]
    upsert_usuario(uid, sexo=sub)

    # Si Google Fit ya trajo el peso, saltar la pregunta
    fit_peso = context.user_data.get("fit_peso", 0)
    if fit_peso > 0:
        # Ya tenemos peso — solo pedir altura
        context.user_data["num_buffer"] = ""
        await _edit(query,
            f"<b>Sexo: {sub} ✅</b>\n\n"
            f"⚖️ Google Fit detectó tu peso: <b>{fit_peso:.1f} kg</b> ✅\n\n"
            f"📏 ¿Cuánto mides?\n"
            f"<i>Escribe tu altura en cm</i>\n\n"
            f"Altura: <b>_</b> cm",
            kb_numerico("altura", ""))
        return

    # Sin Fit — pedir peso
    context.user_data["num_buffer"] = ""
    await _edit(query,
        f"<b>Sexo: {sub} ✅</b>\n\n"
        f"⚖️ ¿Cuánto pesas?\n"
        f"<i>Escribe tu peso en kg</i>\n\n"
        f"Peso: <b>_</b> kg",
        kb_numerico("peso", ""))


# ── Teclado numérico ───────────────────────────────────────────────────────────

async def handle_num(query, uid: int, context):
    parts  = query.data.split(":")
    campo  = parts[1]
    accion = parts[2]
    buf    = context.user_data.get("num_buffer", "")

    if accion == "d":
        digito = parts[3]
        if digito == "." and "." in buf: pass
        elif len(buf) >= 6: pass
        else: buf += digito
        context.user_data["num_buffer"] = buf

    elif accion == "back":
        buf = buf[:-1]
        context.user_data["num_buffer"] = buf

    elif accion == "ok":
        try: valor = float(buf)
        except ValueError: valor = 0
        if valor <= 0: return

        if campo == "peso":
            upsert_usuario(uid, peso_kg=valor)
            context.user_data["num_buffer"] = ""
            await _edit(query,
                f"<b>Peso: {valor:g} kg ✅</b>\n\n"
                f"📏 ¿Cuánto mides?\n"
                f"<i>Escribe tu altura en cm</i>\n\n"
                f"Altura: <b>_</b> cm",
                kb_numerico("altura", ""))
            return

        if campo == "altura":
            upsert_usuario(uid, altura_cm=valor)
            context.user_data["num_buffer"] = ""

            # Calcular BMR/TDEE con lo que tenemos
            u    = get_usuario(uid) or {}
            peso = float(u.get("peso_kg") or 80)
            edad = int(u.get("edad") or 30)
            sexo = u.get("sexo","hombre")
            bmr  = round(10*peso + 6.25*valor - 5*edad + (5 if sexo=="hombre" else -161))
            tdee = round(bmr * 1.375)
            upsert_usuario(uid, bmr=bmr, tdee=tdee)

            await _edit(query,
                f"<b>Altura: {valor:g} cm ✅</b>\n\n"
                f"📊 Tu metabolismo estimado: <b>{tdee} kcal/día</b>\n"
                f"<i>Se recalcula con tus datos reales de actividad</i>\n\n"
                f"<b>Bloque 2/4 — Tu experiencia</b>\n\n"
                f"¿Cuánto tiempo llevas entrenando fuerza de forma seria?",
                _kb(
                    [_btn("🌱 Menos de 6 meses — soy nuevo",    "nv:principiante")],
                    [_btn("💪 6 meses a 2 años — tengo base",   "nv:intermedio")],
                    [_btn("🔥 Más de 2 años — soy avanzado",    "nv:avanzado")],
                ))
            return
        return

    # Re-renderizar
    if campo == "peso":
        titulo, unidad = "⚖️ ¿Cuánto pesas?", "kg"
    else:
        titulo, unidad = "📏 ¿Cuánto mides?", "cm"

    val_show = buf if buf else "_"
    await _edit(query,
        f"{titulo}\n<i>Usa el teclado para escribir el número</i>\n\n"
        f"{'Peso' if campo=='peso' else 'Altura'}: <b>{val_show}</b> {unidad}",
        kb_numerico(campo, buf))


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — EXPERIENCIA
# ══════════════════════════════════════════════════════════════════════════════

async def handle_nv(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _edit(query,
            "¿Cuánto tiempo llevas entrenando fuerza?",
            _kb(
                [_btn("🌱 Menos de 6 meses",  "nv:principiante")],
                [_btn("💪 6 meses a 2 años",  "nv:intermedio")],
                [_btn("🔥 Más de 2 años",     "nv:avanzado")],
            ))
        return

    DESC = {
        "principiante": "Tu cuerpo responde muy bien al entrenamiento ahora — ganancias rápidas",
        "intermedio":   "Necesitas progresión sistemática y volumen moderado para seguir creciendo",
        "avanzado":     "Requieres alta intensidad y técnicas avanzadas para progresar",
    }
    upsert_usuario(uid, nivel=sub)
    await _edit(query,
        f"<b>{sub.capitalize()} ✅</b>\n"
        f"<i>{DESC.get(sub,'')}</i>\n\n"
        f"¿Cuántos días REALES puedes entrenar a la semana?",
        _kb(
            [_btn("3 días — Fullbody (ideal para empezar)",    "dy:3"),
             _btn("4 días — Upper/Lower (más popular)",         "dy:4")],
            [_btn("5 días — Push/Pull/Legs",                   "dy:5"),
             _btn("6 días — PPL × 2 (avanzado)",               "dy:6")],
            _back("nv:back"),
        ))


async def handle_dy(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await handle_nv(query, uid, context)
        return
    upsert_usuario(uid, dias_semana=int(sub))
    await _edit(query,
        f"<b>{sub} días ✅</b>\n\n"
        f"¿Cuánto tiempo tienes por sesión de entrenamiento?\n"
        f"<i>Esto determina cuántos ejercicios incluye cada rutina</i>",
        _kb(
            [_btn("⚡ 45 min — sesión densa y rápida", "dur:45")],
            [_btn("💪 60 min — balance ideal",          "dur:60")],
            [_btn("🏆 90 min — sesión completa",        "dur:90")],
            _back("dy:back"),
        ))


async def handle_dur(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await handle_dy(query, uid, context)
        return
    upsert_usuario(uid, duracion_sesion=int(sub))
    await _edit(query,
        f"<b>{sub} min ✅</b>\n\n"
        f"¿A qué hora entrenas normalmente?\n"
        f"<i>El briefing diario y el check-in se adaptan a tu horario</i>",
        _kb(
            [_btn("🌅 Mañana (6-9am)",    "gym_hora:07:00"),
             _btn("☀️ Mediodía (12-2pm)", "gym_hora:12:00")],
            [_btn("🌆 Tarde (4-6pm)",     "gym_hora:17:00"),
             _btn("🌙 Noche (7-9pm)",     "gym_hora:20:00")],
            _back("dur:back"),
        ))


async def handle_gym_hora(query, uid: int, context):
    parts = query.data.split(":")
    sub   = parts[1]
    if sub == "back":
        await handle_dur(query, uid, context)
        return

    hora_gym = f"{sub}:{parts[2]}" if len(parts) > 2 else sub
    h = int(hora_gym.split(":")[0])
    hora_reminder = f"{((h-2)%24):02d}:00"
    hora_checkin  = f"{((h+2)%24):02d}:00"
    upsert_usuario(uid, hora_gym=hora_gym,
                   hora_reminder=hora_reminder, hora_checkin=hora_checkin)

    await _edit(query,
        f"<b>Gym a las {hora_gym} ✅</b>\n"
        f"<i>Briefing: {hora_reminder} · Check-in: {hora_checkin}</i>\n\n"
        f"¿Dónde entrenas?",
        _kb(
            [_btn("🏋️ Gimnasio completo",   "am:gym")],
            [_btn("🏠 Casa — peso corporal", "am:home")],
            [_btn("🦺 Casa con bandas",      "am:band")],
            _back("gym_hora:back"),
        ))


async def handle_am(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await handle_gym_hora(query, uid, context)
        return
    upsert_usuario(uid, ambiente=sub)
    await _edit(query,
        f"<b>{sub} ✅</b>\n\n"
        f"¿Tienes alguna lesión o limitación física?\n"
        f"<i>Selecciona todo lo que aplique — el planeador ajusta la rutina</i>",
        _kb_lesiones(set()))


# ── Lesiones ──────────────────────────────────────────────────────────────────

LESION_OPTS = [
    ("🦵","Rodilla","rodilla"),       ("🔙","Espalda baja","espalda"),
    ("💪","Hombro","hombro"),          ("✋","Muñeca","muneca"),
    ("🦶","Tobillo","tobillo"),        ("🦒","Cuello","cuello"),
    ("🦴","Cadera","cadera"),          ("💪","Codo","codo"),
    ("🏃","Rodilla de corredor","it_band"), ("🔙","Lumbar crónico","lumbar"),
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
        await handle_am(query, uid, context)
        return

    if sub == "ninguna":
        upsert_usuario(uid, limitaciones="ninguna")
        context.user_data.pop("lesion_sel", None)
        if context.user_data.get("modo_ciclo"):
            await _generar_ciclo(query, uid, context)
        else:
            await _mostrar_dieta(query)
        return

    if sub == "otra":
        context.user_data["esperando_texto"] = "lesion_otra"
        await _edit(query,
            "✏️ <b>Escribe tu lesión o limitación</b>\n\n"
            "<i>Ejemplo: \"tendinitis en el codo derecho\"</i>\n\n"
            "Escribe tu respuesta a continuación 👇")
        return

    if sub == "ok":
        upsert_usuario(uid, limitaciones=",".join(sorted(sel)) if sel else "ninguna")
        context.user_data.pop("lesion_sel", None)
        if context.user_data.get("modo_ciclo"):
            await _generar_ciclo(query, uid, context)
        else:
            await _mostrar_dieta(query)
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["lesion_sel"] = sel
    await _edit(query,
        "<b>¿Tienes alguna lesión o limitación?</b>\n<i>Selecciona todo lo que aplique</i>",
        _kb_lesiones(sel))


async def _mostrar_dieta(query):
    await _edit(query,
        "<b>Bloque 3/4 — Alimentación</b>\n\n"
        "¿Cómo describes tu forma de comer?\n\n"
        "<i>Omnívoro = comes de todo\n"
        "Saludable = priorizas comida real, evitas ultra-procesados\n"
        "Proteína = priorizas proteína sobre todo\n"
        "Vegano = sin productos de origen animal\n"
        "Keto = muy pocos carbohidratos, muchas grasas</i>",
        _kb(
            [_btn("🍗 Omnívoro — como de todo",            "dt:omnivoro")],
            [_btn("🥗 Saludable — comida real y natural",  "dt:saludable")],
            [_btn("🍖 Alta proteína — es mi prioridad",    "dt:proteina")],
            [_btn("🌱 Vegano / Vegetariano",               "dt:vegano")],
            [_btn("🥑 Keto / Bajo en carbos",              "dt:keto")],
        ))


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 — ALIMENTACIÓN
# ══════════════════════════════════════════════════════════════════════════════

async def handle_dt(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "back":
        await _mostrar_dieta(query)
        return

    DIETAS = {"omnivoro":"🍗 Omnívoro","saludable":"🥗 Saludable",
              "proteina":"🍖 Alta proteína","vegano":"🌱 Vegano","keto":"🥑 Keto"}
    upsert_usuario(uid, tipo_dieta=sub)
    await _edit(query,
        f"<b>Dieta: {DIETAS.get(sub,sub)} ✅</b>\n\n"
        f"¿Cuáles son tus cocinas favoritas?\n"
        f"<i>La IA arma el plan con comidas que te gusten — elige hasta 4</i>",
        _kb_cocinas(set()))


# ── Cocinas favoritas ─────────────────────────────────────────────────────────

COCINA_OPTS = [
    ("🌮","Mexicana / Latina","mexicana"),     ("🍔","Americana / BBQ","americana"),
    ("🍝","Italiana / Mediterránea","italiana"),("🍱","Asiática","asiatica"),
    ("🫔","Árabe / Medio Oriente","arabe"),     ("🍛","India","india"),
    ("🥘","Española","española"),               ("🫕","Francesa","francesa"),
    ("🌍","Sin preferencia — como de todo","variada"),
]

def _kb_cocinas(sel: set) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(COCINA_OPTS)-1, 2):
        row = []
        for emoji, label, key in COCINA_OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"cocina:{key}"))
        rows.append(row)
    # Última opción sola (variada)
    e, l, k = COCINA_OPTS[-1]
    mark = "☑️" if k in sel else "⬜"
    rows.append([_btn(f"{mark} {e} {l}", f"cocina:{k}")])
    n = len(sel)
    rows.append([_btn(f"✅ Continuar ({n})" if n else "✅ Sin preferencia — continuar", "cocina:ok")])
    return InlineKeyboardMarkup(rows)


async def handle_cocina(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("cocina_sel", set())

    if sub == "ok":
        upsert_usuario(uid, cocina=",".join(sorted(sel)) if sel else "variada")
        context.user_data.pop("cocina_sel", None)
        await _mostrar_comidas_dia(query)
        return

    if sub in sel: sel.discard(sub)
    else:
        if len(sel) < 4: sel.add(sub)
    context.user_data["cocina_sel"] = sel
    await _edit(query,
        f"<b>¿Cuáles son tus cocinas favoritas?</b> ({len(sel)}/4)\n"
        f"<i>La IA arma el plan con comidas que te gusten</i>",
        _kb_cocinas(sel))


# ── Número de comidas y tiempo por comida ─────────────────────────────────────

async def _mostrar_comidas_dia(query):
    await _edit(query,
        "<b>¿Cuántas comidas principales haces al día?</b>\n\n"
        "<i>Esto determina cómo distribuimos tus macros durante el día</i>",
        _kb(
            [_btn("2 comidas — ayuno intermitente",         "n_comidas:2")],
            [_btn("3 comidas — desayuno, comida y cena",    "n_comidas:3")],
            [_btn("4+ comidas — incluyo snacks/merienda",   "n_comidas:4")],
        ))


async def handle_n_comidas(query, uid: int, context):
    sub = query.data.split(":")[1]
    n   = int(sub)
    upsert_usuario(uid, n_comidas=n)
    context.user_data["comidas_restantes"] = (
        ["desayuno","comida","cena"][:n] if n <= 3
        else ["desayuno","comida","cena","snack"]
    )
    await _siguiente_comida_tiempo(query, uid, context)


async def _siguiente_comida_tiempo(query, uid, context):
    restantes = context.user_data.get("comidas_restantes", [])
    if not restantes:
        # Terminamos con tiempos — ir a proteínas
        await _mostrar_proteinas(query, context)
        return

    comida = restantes[0]
    EMOJI  = {"desayuno":"🌅","comida":"☀️","cena":"🌙","snack":"🍎"}
    NOMBRE = {"desayuno":"Desayuno","comida":"Comida","cena":"Cena","snack":"Snack"}

    await _edit(query,
        f"{EMOJI.get(comida,'🍽️')} <b>{NOMBRE.get(comida,comida).capitalize()}</b>\n\n"
        f"¿Cuánto tiempo tienes para preparar y comer?",
        _kb(
            [_btn("⚡ Menos de 10 min — muy rápido", f"t_comida:{comida}:10")],
            [_btn("🕐 10-20 min — algo rápido",       f"t_comida:{comida}:20")],
            [_btn("🍳 20-40 min — tengo tiempo",      f"t_comida:{comida}:40")],
            [_btn("👨‍🍳 Más de 40 min — me gusta cocinar", f"t_comida:{comida}:60")],
        ))


async def handle_t_comida(query, uid: int, context):
    parts   = query.data.split(":")
    comida  = parts[1]
    minutos = int(parts[2])

    tiempos = context.user_data.get("tiempos_comida", {})
    tiempos[comida] = minutos
    context.user_data["tiempos_comida"] = tiempos

    restantes = context.user_data.get("comidas_restantes", [])
    if restantes and restantes[0] == comida:
        restantes.pop(0)
    context.user_data["comidas_restantes"] = restantes

    # Guardar todos los tiempos cuando terminan
    if not restantes:
        import json as _json
        upsert_usuario(uid, tiempos_comida=_json.dumps(tiempos))

    await _siguiente_comida_tiempo(query, uid, context)


async def _mostrar_proteinas(query, context):
    context.user_data.pop("tiempos_comida", None)
    context.user_data.pop("comidas_restantes", None)
    await _edit(query,
        "<b>¿Cuáles son tus fuentes de proteína favoritas?</b>\n\n"
        "<i>Sin límite — la IA arma el plan con lo que te gusta.\n"
        "Si no marcas nada, usamos las más comunes.</i>",
        _kb_proteinas(set()))


# ── Proteínas favoritas — sin límite ──────────────────────────────────────────

PROT_OPTS = [
    ("🍗","Pollo","pollo"),       ("🥩","Res/Bistec","res"),
    ("🐟","Atún","atun"),          ("🍳","Huevo","huevo"),
    ("🐷","Cerdo","cerdo"),        ("🐟","Salmón","salmon"),
    ("🍤","Camarones","camarones"),("🦃","Pavo","pavo"),
    ("🫘","Legumbres","legumbres"),("🥛","Dairy/Caseína","dairy"),
    ("🧀","Requesón/Cottage","requesón"),("🌱","Tofu/Tempeh","tofu"),
]

def _kb_proteinas(sel: set) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(PROT_OPTS), 2):
        row = []
        for emoji, label, key in PROT_OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(_btn(f"{mark} {emoji} {label}", f"prot:{key}"))
        rows.append(row)
    n = len(sel)
    rows.append([_btn(f"✅ Confirmar ({n})" if n else "✅ Sin preferencia — continuar", "prot:ok")])
    return InlineKeyboardMarkup(rows)


async def handle_prot(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("prot_sel", set())

    if sub == "ok":
        prots = list(sel) if sel else ["pollo","huevo","atun"]
        upsert_usuario(uid, proteinas_favoritas=",".join(prots))
        context.user_data.pop("prot_sel", None)
        await _edit(query,
            f"<b>Proteínas favoritas: {', '.join(prots[:4])}{'...' if len(prots)>4 else ''} ✅</b>\n\n"
            f"¿Tienes alguna restricción alimentaria?\n"
            f"<i>Selecciona todo lo que aplique</i>",
            _kb_restricciones(set()))
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["prot_sel"] = sel

    await _edit(query,
        f"<b>¿Cuáles son tus proteínas favoritas?</b> ({len(sel)} seleccionadas)\n"
        f"<i>Sin límite — más opciones = mejores recetas</i>",
        _kb_proteinas(sel))


# ── Restricciones ─────────────────────────────────────────────────────────────

REST_OPTS = [
    ("🥛","Sin lácteos","lacteos"),  ("🌾","Sin gluten","gluten"),
    ("🥜","Sin maní","mani"),         ("🥚","Sin huevo","huevo"),
    ("🦐","Sin mariscos","mariscos"), ("🐖","Sin cerdo","cerdo"),
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
    rows.append([_btn("✏️ Otra restricción (escribir)", "rt:otra")])
    n = len(sel)
    rows.append([_btn(f"✅ Confirmar ({n})" if n else "✅ Ninguna — continuar", "rt:ok")])
    return InlineKeyboardMarkup(rows)


async def handle_rt(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("rest_sel", set())

    if sub == "otra":
        context.user_data["esperando_texto"] = "restriccion_otra"
        await _edit(query,
            "✏️ <b>Escribe tu restricción alimentaria</b>\n\n"
            "<i>Ejemplo: \"sin cilantro\" o \"intolerante a la lactosa\"</i>\n\n"
            "Escribe a continuación 👇")
        return

    if sub == "ok":
        upsert_usuario(uid, alergias=",".join(sorted(sel)) if sel else "ninguna")
        context.user_data.pop("rest_sel", None)
        await _mostrar_suplementos(query)
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["rest_sel"] = sel
    await _edit(query,
        "<b>¿Tienes alguna restricción alimentaria?</b>",
        _kb_restricciones(sel))


# ── Suplementos ───────────────────────────────────────────────────────────────

async def _mostrar_suplementos(query):
    await _edit(query,
        "<b>¿Qué suplementos tomas actualmente?</b>\n\n"
        "<i>Esto ayuda a la IA a no duplicar nutrientes en tu plan</i>",
        _kb(
            [_btn("❌ Ninguno",                    "suple:ninguno")],
            [_btn("🥛 Proteína whey",              "suple:whey")],
            [_btn("💊 Creatina",                   "suple:creatina")],
            [_btn("🥛💊 Whey + Creatina",          "suple:whey_creatina")],
            [_btn("🌿 Multivitamínico",             "suple:multi")],
            [_btn("🔀 Varios (whey+crea+multi)",    "suple:varios")],
        ))


async def handle_suple(query, uid: int, context):
    sub = query.data.split(":")[1]
    upsert_usuario(uid, suplementos=sub)
    await _edit(query,
        f"<b>Suplementos: {sub} ✅</b>\n\n"
        f"🍺 ¿Consumes alcohol?\n"
        f"<i>El alcohol tiene calorías ocultas que afectan el déficit</i>",
        _kb(
            [_btn("❌ No consumo",              "alcohol:no")],
            [_btn("🍷 Ocasional (1-2x/mes)",   "alcohol:ocasional")],
            [_btn("🍺 Moderado (1-2x/semana)", "alcohol:moderado")],
            [_btn("🍻 Frecuente (3+ x/semana)","alcohol:frecuente")],
        ))


async def handle_alcohol(query, uid: int, context):
    sub = query.data.split(":")[1]
    upsert_usuario(uid, alcohol=sub)
    await _edit(query,
        f"<b>Alcohol: {sub} ✅</b>\n\n"
        f"🔌 ¿Con qué electrodomésticos cocinas?\n"
        f"<i>Todos marcados por default — quita lo que NO tienes</i>",
        _kb_electrodomesticos(set(["air_fryer","microondas","horno","licuadora"])))


# ── Electrodomésticos — todos marcados por default ────────────────────────────

ELEC_OPTS = [
    ("🍳","Air fryer","air_fryer"),      ("🍲","Slow cooker","slow_cooker"),
    ("📡","Microondas","microondas"),     ("🔥","Horno","horno"),
    ("🥤","Licuadora","licuadora"),       ("⚡","Pressure cooker","pressure_cooker"),
    ("🍚","Arrocera","arrocera"),         ("🥪","Sandwichera","sandwichera"),
    ("🍳","Sartén/estufa","estufa"),
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
    rows.append([_btn(f"✅ Tengo estos ({n})", "elec:ok")])
    return InlineKeyboardMarkup(rows)


async def handle_elec(query, uid: int, context):
    sub = query.data.split(":")[1]
    # Default: todos marcados al abrir
    sel = context.user_data.get("elec_sel", set(["air_fryer","microondas","horno","licuadora"]))

    if sub == "ok":
        upsert_usuario(uid, electrodomesticos=",".join(sorted(sel)) if sel else "ninguno")
        context.user_data.pop("elec_sel", None)
        await _edit(query,
            f"<b>Bloque 3 completo ✅</b>\n\n"
            f"<b>Bloque 4/4 — Recuperación y estilo de vida</b>\n\n"
            f"😴 ¿Cuántas horas duermes por noche?",
            _kb_sueño(context))
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["elec_sel"] = sel

    await _edit(query,
        "<b>¿Con qué electrodomésticos cocinas?</b>\n"
        "<i>Quita lo que NO tienes — el resto ya está marcado</i>",
        _kb_electrodomesticos(sel))


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 4 — RECUPERACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def _kb_sueño(context) -> InlineKeyboardMarkup:
    fit_sueño = context.user_data.get("fit_sueño", 0) if context else 0
    nota = f"\n<i>Google Fit detectó {fit_sueño:.1f}h promedio — confirma o ajusta</i>" if fit_sueño else ""
    return _kb(
        [_btn("😫 Menos de 6h", "sueño_hab:5.5"),
         _btn("😐 6-7h",        "sueño_hab:6.5")],
        [_btn("✅ 7-8h",        "sueño_hab:7.5"),
         _btn("🌟 Más de 8h",   "sueño_hab:8.5")],
    )


async def handle_sueño_hab(query, uid: int, context):
    sub = query.data.split(":")[1]
    horas = float(sub)
    upsert_usuario(uid, sueño_horas=horas)

    nota = ""
    if horas < 6:
        nota = "\n⚠️ <i>Menos de 6h reduce la síntesis proteica hasta 30%. El plan lo considera.</i>"
    elif horas >= 8:
        nota = "\n✅ <i>Recuperación óptima.</i>"

    await _edit(query,
        f"<b>Sueño: ~{horas}h ✅</b>{nota}\n\n"
        f"¿Cómo es tu actividad durante el día?\n"
        f"<i>Afecta tu gasto calórico real (TDEE)</i>",
        _kb(
            [_btn("💺 Sedentario — oficina/casa todo el día",      "trabajo:sedentario")],
            [_btn("🚶 Moderado — me muevo algo",                    "trabajo:moderado")],
            [_btn("🏗️ Activo — de pie o en movimiento constante", "trabajo:activo")],
            [_btn("🏃 Muy activo — trabajo físico intenso",        "trabajo:muy_activo")],
        ))


async def handle_trabajo(query, uid: int, context):
    sub = query.data.split(":")[1]
    FACTOR = {"sedentario":1.2,"moderado":1.375,"activo":1.55,"muy_activo":1.725}
    factor = FACTOR.get(sub, 1.375)
    upsert_usuario(uid, actividad_nivel=sub)

    u    = get_usuario(uid) or {}
    bmr  = int(u.get("bmr") or 2000)
    tdee = round(bmr * factor)
    upsert_usuario(uid, tdee=tdee)

    await _edit(query,
        f"<b>Actividad: {sub} ✅</b>\n"
        f"<i>TDEE ajustado: {tdee} kcal/día</i>\n\n"
        f"¿Cómo describes tu nivel de estrés habitual?\n"
        f"<i>El estrés crónico eleva el cortisol y afecta la recuperación muscular</i>",
        _kb(
            [_btn("😌 Bajo — vida tranquila",        "estres:bajo")],
            [_btn("😐 Moderado — algo de presión",   "estres:moderado")],
            [_btn("😤 Alto — trabajo/vida intensa",  "estres:alto")],
            [_btn("🤯 Muy alto — siempre ocupado",   "estres:muy_alto")],
        ))


async def handle_estres(query, uid: int, context):
    sub = query.data.split(":")[1]
    FACTOR = {"bajo":1.0,"moderado":1.1,"alto":1.25,"muy_alto":1.4}
    upsert_usuario(uid, nivel_estres=sub, factor_estres=FACTOR.get(sub,1.0))

    await _edit(query,
        f"<b>Estrés: {sub} ✅</b>\n\n"
        f"🌿 En días de descanso, ¿qué te gusta hacer para recuperarte?\n"
        f"<i>Selecciona una o más — el bot las usa en tus recomendaciones</i>",
        _kb_recuperacion(set()))


# ── Recuperación activa ───────────────────────────────────────────────────────

RA_OPTS = [
    ("🚶","Caminar","caminar"),    ("🧘","Yoga / Estiramiento","yoga"),
    ("🚴","Bicicleta","bici"),     ("🏊","Natación","natacion"),
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
    rows.append([_btn(f"✅ Confirmar ({n})" if n else "⏭ Sin preferencia — continuar", "ra:ok")])
    return InlineKeyboardMarkup(rows)


async def handle_ra(query, uid: int, context):
    sub = query.data.split(":")[1]
    sel = context.user_data.get("ra_sel", set())

    if sub == "otra":
        context.user_data["esperando_texto"] = "recuperacion_otra"
        await _edit(query,
            "✏️ <b>Escribe tu actividad favorita de recuperación</b>\n\n"
            "<i>Ejemplo: \"pádel\" o \"escalada ligera\"</i>\n\n"
            "Escribe a continuación 👇")
        return

    if sub == "ok":
        upsert_usuario(uid, recuperacion_activa=",".join(sorted(sel)) if sel else "caminar")
        context.user_data.pop("ra_sel", None)
        await _mostrar_final(query)
        return

    if sub in sel: sel.discard(sub)
    else: sel.add(sub)
    context.user_data["ra_sel"] = sel
    await _edit(query,
        "<b>¿Qué te gusta hacer en días de descanso?</b>",
        _kb_recuperacion(sel))


# ══════════════════════════════════════════════════════════════════════════════
# FINAL — ¿Qué quieres generar?
# ══════════════════════════════════════════════════════════════════════════════

async def _mostrar_final(query):
    await _edit(query,
        "<b>¡Perfil completo! 🎉</b>\n\n"
        "Ahora dime qué quieres que genere primero:",
        _kb(
            [_btn("💪 Rutina de gym",          "generar:gym")],
            [_btn("🥗 Plan de dieta semanal",  "generar:dieta")],
            [_btn("🔄 Los dos (recomendado)",  "generar:todo")],
        ))


async def handle_generar_final(query, uid: int, context):
    sub = query.data.split(":")[1]

    try:
        await query.edit_message_text(
            "⚙️ <b>Creando tu plan personalizado...</b>\n\n"
            "Analizando perfil y generando rutina...",
            parse_mode="HTML")
    except Exception: pass

    try:
        u = get_usuario(uid)
        from engine.gym.planner import generar_plan

        resumen = ""

        if sub in ("gym","todo"):
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

            peso   = float(u.get("peso_kg") or 80)
            tdee   = int(u.get("tdee") or 2200)
            obj    = u.get("objetivo_gym","general")
            DEFICIT = {"peso":0.82,"mamado":1.10,"gluteo":0.90,"general":0.90}
            kcal    = round(tdee * DEFICIT.get(obj, 0.90))
            prot_g  = round(peso * 2.2)

            resumen = (
                f"✅ <b>Rutina creada — {n} ejercicios · 4 semanas</b>\n"
                f"  {u.get('nivel','').capitalize()} · {u.get('dias_semana')} días · "
                f"{u.get('duracion_sesion',60)} min\n\n"
                f"🔥 <b>Macros base:</b> {kcal} kcal · {prot_g}g proteína\n"
                f"<i>El plan se ajusta automáticamente cada semana</i>"
            )

        if sub in ("dieta","todo"):
            try:
                await query.edit_message_text(
                    resumen + "\n\n🥗 Generando plan de nutrición con IA... <i>(30s)</i>",
                    parse_mode="HTML")
            except Exception: pass

            plan_nutri = await regenerar_dieta(uid)
            if plan_nutri:
                resumen += "\n✅ Plan de nutrición listo"
            else:
                resumen += "\n⚠️ Plan de nutrición: toca 'Regenerar' en la sección Nutrición"

        if sub == "dieta" and not ("gym" in sub or "todo" in sub):
            add_allowed_user(uid)
            upsert_usuario(uid, onboarding_done=1)

        await query.edit_message_text(
            resumen,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💪 Ver mi rutina de hoy", callback_data="m:hoy")
            ]]))

        from bot.keyboards import TECLADO_PRINCIPAL
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Usa los botones de abajo 👇",
            reply_markup=TECLADO_PRINCIPAL)

    except Exception as e:
        logger.error("Error handle_generar_final uid=%s: %s", uid, e, exc_info=True)
        await query.edit_message_text(
            f"❌ Error: {str(e)[:150]}\n\nEscribe /start para reintentar.",
            parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# TEXTO LIBRE — "Otra..." durante onboarding
# ══════════════════════════════════════════════════════════════════════════════

async def handle_texto_otra(update, context, tipo: str, texto: str):
    uid   = update.effective_user.id
    texto = texto.strip()[:100]
    context.user_data.pop("esperando_texto", None)

    if tipo == "lesion_otra":
        u = get_usuario(uid) or {}
        actuales = [a for a in (u.get("limitaciones") or "").split(",") if a and a != "ninguna"]
        actuales.append(f"otra:{texto}")
        upsert_usuario(uid, limitaciones=",".join(actuales))
        if context.user_data.get("modo_ciclo"):
            await update.message.reply_text(f"Anotado: {texto} ✅\n\nGenerando tu nuevo ciclo...")
            await _generar_ciclo_desde_mensaje(update, uid, context)
            return
        await update.message.reply_text(
            f"Anotado: {texto} ✅\n\n<b>Bloque 3/4 — Alimentación</b>\n\n"
            f"¿Cómo describes tu forma de comer?",
            parse_mode="HTML",
            reply_markup=_kb(
                [_btn("🍗 Omnívoro — como de todo",           "dt:omnivoro")],
                [_btn("🥗 Saludable — comida real y natural", "dt:saludable")],
                [_btn("🍖 Alta proteína — es mi prioridad",   "dt:proteina")],
                [_btn("🌱 Vegano / Vegetariano",              "dt:vegano")],
                [_btn("🥑 Keto / Bajo en carbos",             "dt:keto")],
            ))
        return

    if tipo == "restriccion_otra":
        u = get_usuario(uid) or {}
        actuales = [a for a in (u.get("alergias") or "").split(",") if a and a != "ninguna"]
        actuales.append(f"otra:{texto}")
        upsert_usuario(uid, alergias=",".join(actuales))
        await update.message.reply_text(
            f"Anotado: {texto} ✅",
            parse_mode="HTML",
            reply_markup=_kb([_btn("Continuar →", "rt:ok")]))
        return

    if tipo == "recuperacion_otra":
        u = get_usuario(uid) or {}
        actuales = [a for a in (u.get("recuperacion_activa") or "").split(",") if a]
        actuales.append(f"otra:{texto}")
        upsert_usuario(uid, recuperacion_activa=",".join(actuales))
        await update.message.reply_text(
            f"Anotado: {texto} ✅",
            parse_mode="HTML",
            reply_markup=_kb([_btn("Continuar →", "ra:ok")]))
        return


# ══════════════════════════════════════════════════════════════════════════════
# REGENERAR CICLO (desde /reset_plan) — sin re-onboarding completo
# ══════════════════════════════════════════════════════════════════════════════

async def iniciar_ciclo(query, uid: int, context, incluir_dieta: bool = False):
    context.user_data["modo_ciclo"] = True
    context.user_data["modo_dieta_tambien"] = incluir_dieta
    await _edit(query,
        "<b>🔄 Nuevo ciclo de entrenamiento</b>\n\n"
        "Solo confirmo lo que puede haber cambiado — "
        "tu dieta y preferencias se mantienen igual.\n\n"
        "¿Cuánto tiempo llevas entrenando actualmente?",
        _kb(
            [_btn("🌱 Menos de 6 meses",  "nv:principiante")],
            [_btn("💪 6 meses a 2 años",  "nv:intermedio")],
            [_btn("🔥 Más de 2 años",     "nv:avanzado")],
        ))


async def regenerar_dieta(uid: int) -> dict | None:
    from db.database import fetchall, get_ciclo, save_plan_nutricion, get_estado
    from engine.nutrition.macros import calcular_macros_dia
    from ai.coach import generar_plan_nutricion

    usuario = get_usuario(uid)
    if not usuario: return None

    semana, _ = get_estado(uid)
    dias_r = fetchall(
        "SELECT DISTINCT dia FROM rutinas WHERE user_id=? AND ciclo=? AND semana=?",
        (uid, get_ciclo(uid), semana)
    )
    dias_gym = [r["dia"] for r in dias_r] or ["lunes","miercoles","viernes","domingo"]
    macros   = calcular_macros_dia(uid, es_gym=True)
    datos    = {"usuario": usuario, "macros": macros, "dias_gym": dias_gym}

    plan_json = await generar_plan_nutricion(datos)
    if plan_json:
        save_plan_nutricion(uid, plan_json, macros)
    return plan_json


async def _generar_ciclo_core(uid: int, context, notificar) -> None:
    incluir_dieta = context.user_data.get("modo_dieta_tambien", False)
    context.user_data.pop("modo_ciclo", None)
    context.user_data.pop("modo_dieta_tambien", None)

    await notificar("⚙️ <b>Generando tu nuevo ciclo...</b>\n\nReusando tu perfil guardado.")

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

        resumen = (
            f"✅ <b>Nuevo ciclo — {n} ejercicios · 4 semanas</b>\n\n"
            f"  {u.get('nivel','').capitalize()} · {u.get('dias_semana')} días · "
            f"{u.get('duracion_sesion',60)} min\n"
            f"  {u.get('ambiente','gym')} · {u.get('limitaciones','ninguna')}"
        )

        if incluir_dieta:
            await notificar(resumen + "\n\n🥗 Generando plan de nutrición... <i>(30s)</i>")
            plan_nutri = await regenerar_dieta(uid)
            resumen += "\n✅ Nutrición actualizada" if plan_nutri else "\n⚠️ Nutrición: regenera desde la web"

        await notificar(resumen, final=True)

    except Exception as e:
        logger.error("_generar_ciclo uid=%s: %s", uid, e, exc_info=True)
        await notificar(f"❌ Error: {str(e)[:150]}\n\nEscribe /reset_plan para reintentar.", final=True)


async def _generar_ciclo(query, uid: int, context):
    async def notificar(texto, final=False):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💪 Ver mi rutina de hoy", callback_data="m:hoy")
        ]]) if final and texto.startswith("✅") else None
        try: await query.edit_message_text(texto, parse_mode="HTML", reply_markup=kb)
        except Exception: pass
    await _generar_ciclo_core(uid, context, notificar)


async def _generar_ciclo_desde_mensaje(update, uid: int, context):
    async def notificar(texto, final=False):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💪 Ver mi rutina de hoy", callback_data="m:hoy")
        ]]) if final and texto.startswith("✅") else None
        await update.message.reply_text(texto, parse_mode="HTML", reply_markup=kb)
    await _generar_ciclo_core(uid, context, notificar)
