"""
bot/handlers/gym.py — Sesión de gym con tap-only para pesos.
"""
from __future__ import annotations
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from db.database import (get_ejercicios_dia, get_peso_sugerido, save_peso,
                          save_sesion, marcar_completado, avanzar_dia, set_estado)
from bot.keyboards import kb_ejercicio, kb_peso_inicial, kb_feedback_sesion, BTN_MENU
from engine.gym.catalog import BY_ID

logger = logging.getLogger(__name__)
COMPUESTOS = {"sentadilla","press_horizontal","press_inclinado","press_vertical",
              "bisagra_cadera","remo_horizontal","jalon_vertical","peso_muerto"}

def _inc(patron: str) -> float:
    return 5.0 if patron in COMPUESTOS else 2.5

def _render_ejercicio(uid: int, semana: int, dia: str, idx: int) -> tuple[str, object]:
    rows = [r for r in get_ejercicios_dia(uid, semana, dia) if not r.get("es_cardio")]
    if idx >= len(rows):
        return _fin_sesion(uid, semana, dia)

    ej = rows[idx]
    total = len(rows)
    inc = _inc(ej.get("patron",""))
    peso_sug = get_peso_sugerido(uid, ej["ejercicio_id"], ej.get("reps","8-10"), ej.get("patron",""))

    # Calentamiento con pesos reales
    cal_str = ""
    if idx == 0 and peso_sug:
        p = float(peso_sug)
        p40 = round(p*0.40/5)*5; p60 = round(p*0.60/5)*5; p80 = round(p*0.80/5)*5
        GRUPOS = {
            "pierna":  "5 min bici + sentadilla sin peso 2×15",
            "empuje":  "Fondos 2×10 + elevaciones vacías 2×15",
            "tiron":   "Jalón mínimo 2×10 + face pull ligero 2×15",
            "gluteo":  "Hip thrust sin peso 2×15 + clamshell 2×15",
        }
        base = GRUPOS.get(ej.get("grupo",""), "5 min movimiento ligero")
        cal_str = f"\n🔥 <b>Calentamiento:</b> {base}\n   Con barra: {p40}×10 → {p60}×5 → {p80}×3\n"

    # Cue en el primer set del primer ejercicio
    cue_str = ""
    if idx == 0 and ej.get("notas"):
        cue_str = f"\n💡 <i>{ej['notas'][:70]}</i>"

    # Ejercicios restantes
    resto = [rows[j]["ejercicio"][:25] for j in range(idx+1, min(idx+4, total))]
    resto_str = f"\n\n<b>Falta:</b>\n" + "\n".join(f"· {e}" for e in resto) if resto else ""

    texto = (
        f"<b>{idx+1}/{total} — {ej['ejercicio']}</b>\n"
        f"{ej['series']} series × {ej['reps']} reps · RIR {ej.get('rir_objetivo',2)}"
        f"{cue_str}"
        f"{cal_str}"
        f"{resto_str}"
    )

    if peso_sug:
        kb = kb_ejercicio(semana, dia, idx, peso_sug, ej["ejercicio_id"], inc)
    else:
        kb = kb_peso_inicial(semana, dia, idx)

    return texto, kb


def _fin_sesion(uid: int, semana: int, dia: str) -> tuple[str, object]:
    marcar_completado(uid, semana, dia)
    return (
        "🏁 <b>¡Sesión completada!</b>\n\n¿Cómo estuvo?",
        kb_feedback_sesion(semana, dia)
    )


async def handle_rutina_preview(uid: int, semana: int, dia: str, query=None, msg=None):
    ejs = [r for r in get_ejercicios_dia(uid, semana, dia) if not r.get("es_cardio")]
    cardio = [r for r in get_ejercicios_dia(uid, semana, dia) if r.get("es_cardio")]

    if not ejs:
        import random
        RECOVERY = [
            "🧘 Movilidad 15 min — caderas, hombros, columna",
            "🚶 Caminata 20-30 min a ritmo cómodo (Zona 1)",
            "🚴 Bici suave 20-25 min — FC < 110 bpm",
            "🎯 Core: plancha 3×30s · dead bug 3×10 · bird dog 3×10",
            "🤸 Yoga restaurativo 15 min",
        ]
        texto = (
            f"🌿 <b>Hoy: Descanso activo</b>\n\n"
            f"{random.choice(RECOVERY)}\n\n"
            f"<i>El músculo crece hoy — proteína alta y 7-9h de sueño.</i>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú", callback_data="m:main")]])
    else:
        GRUPOS_ICON = {"empuje":"💪","tiron":"🏋️","pierna":"🦵","gluteo":"🍑","core":"🎯"}
        grupo = ejs[0].get("grupo","")
        icon  = GRUPOS_ICON.get(grupo,"💪")
        dur   = len(ejs) * 18 + (20 if cardio else 0)
        lineas = []
        for i, ej in enumerate(ejs):
            sug = get_peso_sugerido(uid, ej["ejercicio_id"], ej.get("reps","8-10"), ej.get("patron",""))
            sug_str = f" → <i>{sug} lbs</i>" if sug else ""
            lineas.append(f"{i+1}. {ej['ejercicio']}  {ej['series']}×{ej['reps']}{sug_str}")
        texto = (
            f"S{semana} · {dia.capitalize()} {icon} {grupo.upper()}  ~{dur} min\n\n"
            f"<b>Rutina de hoy:</b>\n" + "\n".join(lineas) + "\n\n"
            f"Revisa los pesos y toca <b>Empezar</b> cuando estés listo 👇"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Empezar sesión", callback_data=f"ej_start:{semana}:{dia}")],
            [InlineKeyboardButton("⏭ Saltar este día", callback_data=f"skip:{semana}:{dia}"),
             InlineKeyboardButton("🏠 Menú",           callback_data="m:main")],
        ])

    if query:
        try: await query.edit_message_text(texto, reply_markup=kb, parse_mode="HTML")
        except Exception: await query.message.reply_text(texto, reply_markup=kb, parse_mode="HTML")
    elif msg:
        await msg.reply_text(texto, reply_markup=kb, parse_mode="HTML")


async def handle_ej_start(query, uid: int, context):
    parts = query.data.split(":")
    sem, dia = int(parts[1]), parts[2]
    context.user_data["sesion"] = {"semana": sem, "dia": dia, "idx": 0}
    txt, kb = _render_ejercicio(uid, sem, dia, 0)
    try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
    except Exception: await query.message.reply_text(txt, reply_markup=kb, parse_mode="HTML")


async def handle_pw(query, uid: int, context):
    """Ajuste de peso con +/- — solo actualiza display."""
    parts = query.data.split(":")
    sem, dia, idx, peso = int(parts[1]), parts[2], int(parts[3]), float(parts[4])
    peso = max(0, peso)
    rows = [r for r in get_ejercicios_dia(uid, sem, dia) if not r.get("es_cardio")]
    if idx >= len(rows): return
    ej = rows[idx]
    inc = _inc(ej.get("patron",""))
    p_m = round(peso - inc, 1); p_p = round(peso + inc, 1)

    resto = [rows[j]["ejercicio"][:25] for j in range(idx+1, min(idx+4,len(rows)))]
    resto_str = ("\n\n<b>Falta:</b>\n" + "\n".join(f"· {e}" for e in resto)) if resto else ""
    cue = f"\n💡 <i>{ej['notas'][:70]}</i>" if idx==0 and ej.get("notas") else ""

    texto = (
        f"<b>{idx+1}/{len(rows)} — {ej['ejercicio']}</b>\n"
        f"{ej['series']} series × {ej['reps']} reps"
        f"{cue}{resto_str}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"−{inc:.0f}", callback_data=f"pw:{sem}:{dia}:{idx}:{p_m}"),
         InlineKeyboardButton(f"💪 {peso:.1f} lbs", callback_data=f"pw:{sem}:{dia}:{idx}:{peso}"),
         InlineKeyboardButton(f"+{inc:.0f}", callback_data=f"pw:{sem}:{dia}:{idx}:{p_p}")],
        [InlineKeyboardButton(f"✅ Hecho — {peso:.1f} lbs", callback_data=f"ej_ok:{sem}:{dia}:{idx}:{peso}")],
        [InlineKeyboardButton("🔄 Cambiar", callback_data=f"swp:{ej['ejercicio_id']}:{sem}:{dia}"),
         InlineKeyboardButton("⏭ Saltar",  callback_data=f"ej_ok:{sem}:{dia}:{idx}:0"),
         InlineKeyboardButton("🏠",         callback_data="m:main")],
    ])
    try: await query.edit_message_text(texto, reply_markup=kb, parse_mode="HTML")
    except Exception: pass


async def handle_ej_ok(query, uid: int, context):
    """Confirma peso y avanza al siguiente ejercicio."""
    parts = query.data.split(":")
    sem, dia, idx, peso = int(parts[1]), parts[2], int(parts[3]), float(parts[4])
    rows = [r for r in get_ejercicios_dia(uid, sem, dia) if not r.get("es_cardio")]
    if idx < len(rows) and peso > 0:
        ej = rows[idx]
        save_peso(uid, ej["ejercicio_id"], sem, dia, peso, ej.get("reps"), ej.get("series"))
    siguiente = idx + 1
    context.user_data["sesion"] = {"semana": sem, "dia": dia, "idx": siguiente}
    txt, kb = _render_ejercicio(uid, sem, dia, siguiente)
    try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
    except Exception: await query.message.reply_text(txt, reply_markup=kb, parse_mode="HTML")


async def handle_fb(query, uid: int):
    """Feedback de sesión — RIR y fatiga."""
    parts = query.data.split(":")
    sem, dia, rir, fatiga = int(parts[1]), parts[2], int(parts[3]), int(parts[4])
    save_sesion(uid, sem, dia, completada=1, fatiga_global=fatiga, rir_promedio=rir)
    nueva_sem, nuevo_dia = avanzar_dia(uid, sem, dia)
    set_estado(uid, nueva_sem, nuevo_dia)
    sueño_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("😫 <6h",  callback_data=f"sue:{sem}:{dia}:5.5"),
         InlineKeyboardButton("😊 6-7h", callback_data=f"sue:{sem}:{dia}:6.5")],
        [InlineKeyboardButton("✅ 7-8h", callback_data=f"sue:{sem}:{dia}:7.5"),
         InlineKeyboardButton("🌟 8h+",  callback_data=f"sue:{sem}:{dia}:8.5")],
        [InlineKeyboardButton("Saltar →", callback_data="m:hoy")],
    ])
    try:
        await query.edit_message_text(
            "💾 Guardado ✅\n\n😴 <b>¿Cuántas horas dormiste anoche?</b>\n"
            "<i>El sueño es donde crece el músculo. Gemini lo usa en el análisis.</i>",
            reply_markup=sueño_kb, parse_mode="HTML")
    except Exception: pass


async def handle_sue(query, uid: int):
    parts = query.data.split(":")
    horas = float(parts[3])
    from db.database import upsert_usuario
    upsert_usuario(uid, sueño_horas=horas)
    aviso = ""
    if horas < 6: aviso = "\n⚠️ Menos de 6h afecta la síntesis proteica y la recuperación muscular."
    try:
        await query.edit_message_text(
            f"✅ {horas}h registradas.{aviso}\n\nEl análisis llega esta noche 🧠",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💪 Ver siguiente sesión", callback_data="m:hoy")
            ]]),
            parse_mode="HTML")
    except Exception: pass


async def handle_skip(query, uid: int):
    parts = query.data.split(":")
    sem, dia = int(parts[1]), parts[2]
    nueva_sem, nuevo_dia = avanzar_dia(uid, sem, dia)
    set_estado(uid, nueva_sem, nuevo_dia)
    await query.edit_message_text("Día saltado 👍\n\nToca 💪 Rutina de hoy cuando estés listo.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú", callback_data="m:main")]]))
