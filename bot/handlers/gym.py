"""
bot/handlers/gym.py — Invisible Coach v4.0 (Sesión 12)

Sesión de gym con tap-only para pesos.

Cambios v4.0:
  - Botón "← Anterior" funcional en cada ejercicio (navegación real)
  - Calentamiento SIEMPRE visible en el primer ejercicio (antes solo si
    había historial de pesos — ahora usa un peso inicial sensato si es
    la primera vez)
  - Cardio visible: en el preview de la rutina y como paso final de la
    sesión (con su propia pantalla Hecho/Saltar)
  - Eliminados botones muertos "🔄 Cambiar" / "✏️ Otro peso" (ej_manual:
    y swp: nunca estaban ruteados)
  - Primera vez: peso inicial sensato (45 lbs barra vacía para
    compuestos, 10 lbs para accesorios) + stepper +/-, no más tabla
    fija de pesos de barra
"""
from __future__ import annotations
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from db.database import (get_ejercicios_dia, get_peso_sugerido, save_peso,
                          save_sesion, marcar_completado, avanzar_dia, set_estado)
from bot.keyboards import kb_feedback_sesion, BTN_MENU
from engine.gym.catalog import BY_ID

logger = logging.getLogger(__name__)
COMPUESTOS = {"sentadilla","press_horizontal","press_inclinado","press_vertical",
              "bisagra_cadera","remo_horizontal","jalon_vertical","peso_muerto"}

CARDIO_ICON = "🚴"


def _inc(patron: str) -> float:
    return 5.0 if patron in COMPUESTOS else 2.5


def _default_peso(patron: str) -> float:
    """Peso inicial sensato cuando no hay historial — primera sesión."""
    return 45.0 if patron in COMPUESTOS else 10.0


def _split_rows(uid: int, semana: int, dia: str):
    todas  = get_ejercicios_dia(uid, semana, dia)
    fuerza = [r for r in todas if not r.get("es_cardio")]
    cardio = [r for r in todas if r.get("es_cardio")]
    return fuerza, cardio


def _calentamiento_texto(ej: dict, peso_mostrar: float, es_inicial: bool) -> str:
    """Calentamiento — siempre visible en el primer ejercicio."""
    GRUPOS = {
        "pierna":  "5 min bici suave + sentadilla sin peso 2×15",
        "empuje":  "Fondos asistidos o flexiones 2×10 + elevaciones vacías 2×15",
        "tiron":   "Jalón con poco peso 2×10 + face pull ligero 2×15",
        "gluteo":  "Hip thrust sin peso 2×15 + clamshell 2×15",
        "core":    "Movilidad de cadera y columna 5 min",
    }
    base = GRUPOS.get(ej.get("grupo",""), "5 min movimiento ligero + articulaciones")

    if ej.get("patron","") in COMPUESTOS:
        p = peso_mostrar
        p40 = max(round(p*0.40/5)*5, 0)
        p60 = max(round(p*0.60/5)*5, 0)
        p80 = max(round(p*0.80/5)*5, 0)
        nota = " <i>(estimado — primera vez)</i>" if es_inicial else ""
        return (f"\n🔥 <b>Calentamiento:</b> {base}\n"
                f"   Con barra: {p40}×10 → {p60}×5 → {p80}×3{nota}\n")
    else:
        return (f"\n🔥 <b>Calentamiento:</b> {base}\n"
                f"   1-2 series ligeras (50-60% del peso) antes de ir a la carga de trabajo\n")


def _kb_ejercicio_v2(semana: int, dia: str, idx: int, peso: float,
                      eid: str, inc: float) -> InlineKeyboardMarkup:
    s, d, i = semana, dia, idx
    p_m = round(max(peso - inc, 0), 1)
    p_p = round(peso + inc, 1)
    rows = [
        [InlineKeyboardButton(f"−{inc:.0f}", callback_data=f"pw:{s}:{d}:{i}:{p_m}"),
         InlineKeyboardButton(f"💪 {peso:.1f} lbs", callback_data=f"pw:{s}:{d}:{i}:{peso}"),
         InlineKeyboardButton(f"+{inc:.0f}", callback_data=f"pw:{s}:{d}:{i}:{p_p}")],
        [InlineKeyboardButton(f"✅ Hecho — {peso:.1f} lbs", callback_data=f"ej_ok:{s}:{d}:{i}:{peso}")],
    ]
    nav = []
    if i > 0:
        nav.append(InlineKeyboardButton("← Anterior", callback_data=f"prev:{s}:{d}:{i}"))
    nav.append(InlineKeyboardButton("⏭ Saltar", callback_data=f"ej_ok:{s}:{d}:{i}:0"))
    nav.append(InlineKeyboardButton("🏠", callback_data="m:main"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)


def _kb_cardio(semana: int, dia: str, idx_cardio: int) -> InlineKeyboardMarkup:
    s, d, i = semana, dia, idx_cardio
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Hecho", callback_data=f"ej_ok:{s}:{d}:{i}:0")],
        [InlineKeyboardButton("← Anterior", callback_data=f"prev:{s}:{d}:{i}"),
         InlineKeyboardButton("⏭ Saltar",   callback_data=f"ej_ok:{s}:{d}:{i}:-1"),
         InlineKeyboardButton("🏠",          callback_data="m:main")],
    ])


def _render_ejercicio(uid: int, semana: int, dia: str, idx: int) -> tuple[str, object]:
    fuerza, cardio = _split_rows(uid, semana, dia)
    total = len(fuerza)

    # ── Paso de cardio (después del último ejercicio de fuerza) ──────────────
    if idx == total and cardio:
        c = cardio[0]
        texto = (
            f"<b>{CARDIO_ICON} Cardio — {c['ejercicio']}</b>\n"
            f"Duración: {c.get('reps','20min')}\n"
        )
        if c.get("notas"):
            texto += f"\n💡 <i>{c['notas'][:100]}</i>"
        return texto, _kb_cardio(semana, dia, idx)

    # ── Fin de sesión (no más ejercicios ni cardio) ──────────────────────────
    if idx >= total + (1 if cardio else 0):
        return _fin_sesion(uid, semana, dia)

    # ── Ejercicio de fuerza ────────────────────────────────────────────────
    ej = fuerza[idx]
    inc = _inc(ej.get("patron",""))
    peso_real = get_peso_sugerido(uid, ej["ejercicio_id"], ej.get("reps","8-10"), ej.get("patron",""))
    es_inicial = not bool(peso_real)
    peso_mostrar = float(peso_real) if peso_real else _default_peso(ej.get("patron",""))

    cal_str = _calentamiento_texto(ej, peso_mostrar, es_inicial) if idx == 0 else ""

    cue_str = ""
    if idx == 0 and ej.get("notas"):
        cue_str = f"\n💡 <i>{ej['notas'][:70]}</i>"

    resto = [fuerza[j]["ejercicio"][:25] for j in range(idx+1, min(idx+4, total))]
    if cardio and idx+1 >= total:
        resto.append(f"{CARDIO_ICON} {cardio[0]['ejercicio'][:25]}")
    resto_str = f"\n\n<b>Falta:</b>\n" + "\n".join(f"· {e}" for e in resto) if resto else ""

    inicial_str = "\n<i>Primera vez — ajusta el peso a lo que se sienta correcto</i>" if es_inicial else ""

    texto = (
        f"<b>{idx+1}/{total} — {ej['ejercicio']}</b>\n"
        f"{ej['series']} series × {ej['reps']} reps · RIR {ej.get('rir_objetivo',2)}"
        f"{cue_str}"
        f"{cal_str}"
        f"{inicial_str}"
        f"{resto_str}"
    )

    kb = _kb_ejercicio_v2(semana, dia, idx, peso_mostrar, ej["ejercicio_id"], inc)
    return texto, kb


def _fin_sesion(uid: int, semana: int, dia: str) -> tuple[str, object]:
    marcar_completado(uid, semana, dia)
    return (
        "🏁 <b>¡Sesión completada!</b>\n\n¿Cómo estuvo?",
        kb_feedback_sesion(semana, dia)
    )


async def handle_rutina_preview(uid: int, semana: int, dia: str, query=None, msg=None):
    fuerza, cardio = _split_rows(uid, semana, dia)

    if not fuerza:
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
        grupo = fuerza[0].get("grupo","")
        icon  = GRUPOS_ICON.get(grupo,"💪")
        dur_cardio = 0
        if cardio:
            try: dur_cardio = int(str(cardio[0].get("reps","20")).replace("min",""))
            except ValueError: dur_cardio = 20
        dur = len(fuerza) * 18 + dur_cardio

        lineas = []
        for i, ej in enumerate(fuerza):
            sug = get_peso_sugerido(uid, ej["ejercicio_id"], ej.get("reps","8-10"), ej.get("patron",""))
            sug_str = f" → <i>{sug} lbs</i>" if sug else ""
            lineas.append(f"{i+1}. {ej['ejercicio']}  {ej['series']}×{ej['reps']}{sug_str}")

        if cardio:
            c = cardio[0]
            lineas.append(f"{len(fuerza)+1}. {CARDIO_ICON} {c['ejercicio']}  {c.get('reps','20min')}")

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


async def handle_prev(query, uid: int, context):
    """← Anterior — vuelve al ejercicio/cardio anterior sin perder progreso."""
    parts = query.data.split(":")
    sem, dia, idx = int(parts[1]), parts[2], int(parts[3])
    anterior = max(idx - 1, 0)
    context.user_data["sesion"] = {"semana": sem, "dia": dia, "idx": anterior}
    txt, kb = _render_ejercicio(uid, sem, dia, anterior)
    try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
    except Exception: pass


async def handle_pw(query, uid: int, context):
    """Ajuste de peso con +/- — solo actualiza display."""
    parts = query.data.split(":")
    sem, dia, idx, peso = int(parts[1]), parts[2], int(parts[3]), float(parts[4])
    peso = max(0, peso)
    fuerza, cardio = _split_rows(uid, sem, dia)
    if idx >= len(fuerza): return
    ej = fuerza[idx]
    inc = _inc(ej.get("patron",""))

    cal_str = ""
    cue_str = ""
    if idx == 0:
        cal_str = _calentamiento_texto(ej, peso, False)
        if ej.get("notas"):
            cue_str = f"\n💡 <i>{ej['notas'][:70]}</i>"

    resto = [fuerza[j]["ejercicio"][:25] for j in range(idx+1, min(idx+4,len(fuerza)))]
    if cardio and idx+1 >= len(fuerza):
        resto.append(f"{CARDIO_ICON} {cardio[0]['ejercicio'][:25]}")
    resto_str = ("\n\n<b>Falta:</b>\n" + "\n".join(f"· {e}" for e in resto)) if resto else ""

    texto = (
        f"<b>{idx+1}/{len(fuerza)} — {ej['ejercicio']}</b>\n"
        f"{ej['series']} series × {ej['reps']} reps · RIR {ej.get('rir_objetivo',2)}"
        f"{cue_str}{cal_str}{resto_str}"
    )
    kb = _kb_ejercicio_v2(sem, dia, idx, peso, ej["ejercicio_id"], inc)
    try: await query.edit_message_text(texto, reply_markup=kb, parse_mode="HTML")
    except Exception: pass


async def handle_ej_ok(query, uid: int, context):
    """Confirma peso/cardio y avanza al siguiente paso."""
    parts = query.data.split(":")
    sem, dia, idx, peso = int(parts[1]), parts[2], int(parts[3]), float(parts[4])
    fuerza, cardio = _split_rows(uid, sem, dia)

    # idx < len(fuerza): ejercicio de fuerza — guardar peso si es válido (peso>0)
    if idx < len(fuerza) and peso > 0:
        ej = fuerza[idx]
        save_peso(uid, ej["ejercicio_id"], sem, dia, peso, ej.get("reps"), ej.get("series"))

    # idx == len(fuerza): paso de cardio — peso=0 (Hecho) o -1 (Saltar), no se guarda nada

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
