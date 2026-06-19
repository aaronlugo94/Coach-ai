"""
bot/handlers/gym.py — Invisible Coach v4.1 (Fase 1 fix)

Fixes:
  - Stepper: 3 botones -20/-10/-5 / peso / +5/+10/+20 (2 filas)
  - Calentamiento siempre visible en ejercicio 1 (incluso tras ← Anterior)
  - Cardio visible en preview Y como paso final de la sesión
  - Peso guardado entre sesiones: muestra el último peso usado como base
  - RIR explicado en lenguaje simple ("te quedan ~N reps en el tanque")
  - handle_prev registrado y funcional
"""
from __future__ import annotations
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db.database import (get_ejercicios_dia, get_peso_sugerido, get_historial_peso,
                          save_peso, save_sesion, marcar_completado,
                          avanzar_dia, set_estado, sustituir_ejercicio, get_usuario)
from bot.keyboards import kb_feedback_sesion, BTN_MENU
from engine.gym.catalog import buscar_alternativas

logger = logging.getLogger(__name__)

CARDIO_ICON = "Cardio"
COMPUESTOS  = {"sentadilla","press_horizontal","press_inclinado","press_vertical",
               "bisagra_cadera","remo_horizontal","jalon_vertical","peso_muerto"}

RIR_TEXTO = {
    0: "al fallo — máxima intensidad",
    1: "te queda 1 rep en el tanque",
    2: "te quedan ~2 reps en el tanque",
    3: "te quedan ~3 reps en el tanque",
    4: "esfuerzo moderado-alto",
    5: "esfuerzo moderado — día de volumen",
}


def _inc(patron: str) -> float:
    return 5.0 if patron in COMPUESTOS else 2.5


def _default_peso(patron: str) -> float:
    return 45.0 if patron in COMPUESTOS else 10.0


def _split_rows(uid: int, semana: int, dia: str):
    todas  = get_ejercicios_dia(uid, semana, dia)
    fuerza = [r for r in todas if not r.get("es_cardio")]
    cardio = [r for r in todas if r.get("es_cardio")]
    return fuerza, cardio


def _get_peso_base(uid: int, ej: dict, context=None) -> tuple[float, bool]:
    """
    Retorna (peso_a_mostrar, es_inicial).
    Orden de prioridad:
    1. Ajuste hecho en ESTA sesión activa (context.user_data) — aunque
       no se haya confirmado con "Hecho" todavía, así no se pierde si
       navegas con Atrás/Adelante o sales al Menú y regresas.
    2. Historial real (última sesión pasada).
    3. Peso sugerido por doble progresión.
    4. Default sensato por patrón (primera vez).
    """
    if context is not None:
        pesos_sesion = context.user_data.get("pesos_sesion", {})
        if ej["ejercicio_id"] in pesos_sesion:
            return float(pesos_sesion[ej["ejercicio_id"]]), False

    hist = get_historial_peso(uid, ej["ejercicio_id"], 1)
    if hist and float(hist[0].get("peso_lbs", 0)) > 0:
        return float(hist[0]["peso_lbs"]), False

    sug = get_peso_sugerido(uid, ej["ejercicio_id"], ej.get("reps","8-10"), ej.get("patron",""))
    if sug and float(sug) > 0:
        return float(sug), False

    return _default_peso(ej.get("patron","")), True


def _calentamiento_texto(ej: dict, peso: float, es_inicial: bool) -> str:
    if ej.get("patron","") in COMPUESTOS:
        p60 = max(round(peso * 0.60 / 5) * 5, 0)
        nota = " (estimado)" if es_inicial else ""
        return f"\nCalentamiento: 1 serie con {p60} lbs x 8 reps, luego al peso de trabajo{nota}\n"
    return "\nCalentamiento: 1 serie ligera antes del peso de trabajo\n"


def _kb_stepper(semana: int, dia: str, idx: int, peso: float, es_compuesto: bool,
                ejercicio_id: str = "") -> InlineKeyboardMarkup:
    """
    2 filas de steppers: -20/-10/-5 | peso | +5/+10/+20
    Fila 3: Hecho
    Fila 4: Cambiar ejercicio
    Fila 5: Anterior | Saltar | Menu
    """
    s, d, i = semana, dia, idx

    def btn_p(delta: float) -> InlineKeyboardButton:
        nuevo = round(max(peso + delta, 0), 1)
        signo = "+" if delta > 0 else ""
        label = f"{signo}{delta:g}"
        return InlineKeyboardButton(label, callback_data=f"pw:{s}:{d}:{i}:{nuevo}")

    rows = [
        # Fila 1: decrementos
        [btn_p(-20), btn_p(-10), btn_p(-5)],
        # Fila 2: peso actual (display) + incrementos
        [InlineKeyboardButton(f"{peso:g} lbs", callback_data=f"pw:{s}:{d}:{i}:{peso}"),
         btn_p(+5), btn_p(+10), btn_p(+20)],
        # Fila 3: confirmar
        [InlineKeyboardButton(f"Hecho — {peso:g} lbs", callback_data=f"ej_ok:{s}:{d}:{i}:{peso}")],
    ]

    if ejercicio_id:
        rows.append([InlineKeyboardButton("🔄 Cambiar ejercicio", callback_data=f"ej_swap:{s}:{d}:{i}")])

    nav = []
    if i > 0:
        nav.append(InlineKeyboardButton("Atras", callback_data=f"prev:{s}:{d}:{i}"))
    nav.append(InlineKeyboardButton("Saltar", callback_data=f"ej_ok:{s}:{d}:{i}:0"))
    nav.append(InlineKeyboardButton("Menu", callback_data="m:main"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)


def _kb_cardio(semana: int, dia: str, idx: int) -> InlineKeyboardMarkup:
    s, d, i = semana, dia, idx
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Hecho", callback_data=f"ej_ok:{s}:{d}:{i}:0")],
        [InlineKeyboardButton("Atras",  callback_data=f"prev:{s}:{d}:{i}"),
         InlineKeyboardButton("Saltar", callback_data=f"ej_ok:{s}:{d}:{i}:-1"),
         InlineKeyboardButton("Menu",   callback_data="m:main")],
    ])


def _render_ejercicio(uid: int, semana: int, dia: str, idx: int, context=None) -> tuple[str, object]:
    fuerza, cardio = _split_rows(uid, semana, dia)
    total = len(fuerza)

    # ── Paso de cardio ────────────────────────────────────────────────────────
    if idx == total and cardio:
        c = cardio[0]
        duracion = c.get("reps","20min")
        texto = (
            f"<b>{CARDIO_ICON} — {c['ejercicio']}</b>\n"
            f"Duracion: {duracion}\n"
            f"Zona 2 — mantente a un ritmo donde puedas hablar con esfuerzo"
        )
        if c.get("notas"):
            texto += f"\n\n{c['notas'][:100]}"
        return texto, _kb_cardio(semana, dia, idx)

    # ── Fin de sesion ─────────────────────────────────────────────────────────
    if idx >= total + (1 if cardio else 0):
        return _fin_sesion(uid, semana, dia)

    # ── Ejercicio de fuerza ───────────────────────────────────────────────────
    ej = fuerza[idx]
    peso, es_inicial = _get_peso_base(uid, ej, context)
    es_compuesto     = ej.get("patron","") in COMPUESTOS
    rir              = ej.get("rir_objetivo", 2)
    rir_txt          = RIR_TEXTO.get(rir, f"RIR {rir}")

    # Calentamiento solo en el primer ejercicio
    cal_str = _calentamiento_texto(ej, peso, es_inicial) if idx == 0 else ""

    # Cue tecnico en el primer ejercicio
    cue_str = ""
    if idx == 0 and ej.get("notas"):
        cue_str = f"\n<i>{ej['notas'][:80]}</i>"

    # Proximos ejercicios
    resto = [fuerza[j]["ejercicio"][:28] for j in range(idx+1, min(idx+4, total))]
    if cardio and idx + 1 >= total:
        resto.append(f"{CARDIO_ICON}: {cardio[0]['ejercicio'][:20]}")
    resto_str = ("\n\nSigue:\n" + "\n".join(f"  {e}" for e in resto)) if resto else ""

    inicial_str = "\n<i>Primera vez — ajusta a lo que se sienta bien (RIR honesto)</i>" if es_inicial else ""

    texto = (
        f"<b>{idx+1}/{total} — {ej['ejercicio']}</b>\n"
        f"{ej['series']} series x {ej['reps']} reps\n"
        f"Intensidad: {rir_txt}"
        f"{cue_str}"
        f"{cal_str}"
        f"{inicial_str}"
        f"{resto_str}"
    )

    kb = _kb_stepper(semana, dia, idx, peso, es_compuesto, ej["ejercicio_id"])
    return texto, kb


def _fin_sesion(uid: int, semana: int, dia: str) -> tuple[str, object]:
    marcar_completado(uid, semana, dia)
    return (
        "Sesion completada!\n\nComo estuvo?",
        kb_feedback_sesion(semana, dia)
    )


async def handle_rutina_preview(uid: int, semana: int, dia: str, query=None, msg=None):
    fuerza, cardio = _split_rows(uid, semana, dia)

    if not fuerza:
        import random
        RECOVERY = [
            "Movilidad 15 min — caderas, hombros, columna",
            "Caminata 20-30 min a ritmo comodo (Zona 1)",
            "Bici suave 20-25 min — FC menor a 110 bpm",
            "Core: plancha 3x30s + dead bug 3x10 + bird dog 3x10",
        ]
        u_recovery = random.choice(RECOVERY)
        from db.database import get_usuario
        u = get_usuario(uid) or {}
        ra = u.get("recuperacion_activa","caminar")
        texto = (
            f"Hoy: Descanso activo\n\n"
            f"Recomendado para ti ({ra.split(',')[0]}): {u_recovery}\n\n"
            f"El musculo crece hoy — proteina alta y 7-9h de sueno."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="m:main")]])
    else:
        GRUPOS_ICON = {"empuje":"Empuje","tiron":"Tiron","pierna":"Pierna",
                       "gluteo":"Gluteo","core":"Core"}
        grupo = fuerza[0].get("grupo","")
        label = GRUPOS_ICON.get(grupo, grupo.upper())
        dur_cardio = 0
        if cardio:
            try: dur_cardio = int(str(cardio[0].get("reps","20")).replace("min","").strip())
            except ValueError: dur_cardio = 20
        dur = len(fuerza) * 18 + dur_cardio

        lineas = []
        for i, ej in enumerate(fuerza):
            hist = get_historial_peso(uid, ej["ejercicio_id"], 1)
            if hist and float(hist[0].get("peso_lbs",0)) > 0:
                sug_str = f"  {float(hist[0]['peso_lbs']):g} lbs"
            else:
                sug = get_peso_sugerido(uid, ej["ejercicio_id"], ej.get("reps","8-10"), ej.get("patron",""))
                sug_str = f"  {sug} lbs" if sug else ""
            lineas.append(f"{i+1}. {ej['ejercicio']}  {ej['series']}x{ej['reps']}{sug_str}")

        if cardio:
            c = cardio[0]
            lineas.append(f"{len(fuerza)+1}. {CARDIO_ICON}: {c['ejercicio']}  {c.get('reps','20min')}")

        # Calentamiento — preview del que verás al iniciar
        primer_ej = fuerza[0]
        peso_warmup, _ = _get_peso_base(uid, primer_ej)
        cal_preview = _calentamiento_texto(primer_ej, peso_warmup, False).strip()

        texto = (
            f"S{semana} - {dia.capitalize()} - {label}  ~{dur} min\n\n"
            f"{cal_preview}\n\n"
            f"<b>Rutina de hoy:</b>\n" + "\n".join(lineas) + "\n\n"
            f"Revisa los pesos y toca Empezar cuando estes listo"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Empezar sesion", callback_data=f"ej_start:{semana}:{dia}")],
            [InlineKeyboardButton("Saltar este dia", callback_data=f"skip:{semana}:{dia}"),
             InlineKeyboardButton("Menu",            callback_data="m:main")],
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
    context.user_data["pesos_sesion"] = {}
    txt, kb = _render_ejercicio(uid, sem, dia, 0, context)
    try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
    except Exception: await query.message.reply_text(txt, reply_markup=kb, parse_mode="HTML")


async def handle_prev(query, uid: int, context):
    """Atras — vuelve al ejercicio anterior sin perder progreso."""
    parts = query.data.split(":")
    sem, dia, idx = int(parts[1]), parts[2], int(parts[3])
    anterior = max(idx - 1, 0)
    context.user_data["sesion"] = {"semana": sem, "dia": dia, "idx": anterior}
    txt, kb = _render_ejercicio(uid, sem, dia, anterior, context)
    try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
    except Exception: pass


async def handle_pw(query, uid: int, context):
    """Ajuste de peso — actualiza display Y lo recuerda en la sesión activa
    (aunque no se confirme con 'Hecho') para que no se pierda al navegar
    con Atrás/Adelante o al salir y volver desde el Menú."""
    parts = query.data.split(":")
    sem, dia, idx, peso = int(parts[1]), parts[2], int(parts[3]), float(parts[4])
    peso = max(0.0, peso)
    fuerza, cardio = _split_rows(uid, sem, dia)
    if idx >= len(fuerza):
        return

    ej_actual = fuerza[idx]
    pesos_sesion = context.user_data.setdefault("pesos_sesion", {})
    pesos_sesion[ej_actual["ejercicio_id"]] = peso

    ej = fuerza[idx]
    es_compuesto = ej.get("patron","") in COMPUESTOS
    rir  = ej.get("rir_objetivo", 2)

    # Calentamiento siempre en idx==0, recalculado con el nuevo peso
    cal_str = _calentamiento_texto(ej, peso, False) if idx == 0 else ""
    cue_str = f"\n<i>{ej['notas'][:80]}</i>" if idx == 0 and ej.get("notas") else ""

    resto = [fuerza[j]["ejercicio"][:28] for j in range(idx+1, min(idx+4, len(fuerza)))]
    if cardio and idx+1 >= len(fuerza):
        resto.append(f"{CARDIO_ICON}: {cardio[0]['ejercicio'][:20]}")
    resto_str = ("\n\nSigue:\n" + "\n".join(f"  {e}" for e in resto)) if resto else ""

    rir_txt = RIR_TEXTO.get(rir, f"RIR {rir}")
    texto = (
        f"<b>{idx+1}/{len(fuerza)} — {ej['ejercicio']}</b>\n"
        f"{ej['series']} series x {ej['reps']} reps\n"
        f"Intensidad: {rir_txt}"
        f"{cue_str}{cal_str}{resto_str}"
    )
    kb = _kb_stepper(sem, dia, idx, peso, es_compuesto, ej["ejercicio_id"])
    try: await query.edit_message_text(texto, reply_markup=kb, parse_mode="HTML")
    except Exception: pass


async def handle_ej_ok(query, uid: int, context):
    """Confirma peso y avanza al siguiente paso."""
    parts = query.data.split(":")
    sem, dia, idx, peso = int(parts[1]), parts[2], int(parts[3]), float(parts[4])
    fuerza, cardio = _split_rows(uid, sem, dia)

    # Guardar peso si es ejercicio de fuerza con peso valido
    if idx < len(fuerza) and peso > 0:
        ej = fuerza[idx]
        save_peso(uid, ej["ejercicio_id"], sem, dia, peso, ej.get("reps"), ej.get("series"))

    siguiente = idx + 1
    context.user_data["sesion"] = {"semana": sem, "dia": dia, "idx": siguiente}
    txt, kb = _render_ejercicio(uid, sem, dia, siguiente, context)
    try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
    except Exception: await query.message.reply_text(txt, reply_markup=kb, parse_mode="HTML")


async def handle_fb(query, uid: int):
    """Feedback de sesion — RIR y fatiga."""
    parts = query.data.split(":")
    sem, dia, rir, fatiga = int(parts[1]), parts[2], int(parts[3]), int(parts[4])
    save_sesion(uid, sem, dia, completada=1, fatiga_global=fatiga, rir_promedio=rir)
    nueva_sem, nuevo_dia = avanzar_dia(uid, sem, dia)
    set_estado(uid, nueva_sem, nuevo_dia)
    sueño_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("menos de 6h", callback_data=f"sue:{sem}:{dia}:5.5"),
         InlineKeyboardButton("6-7h",        callback_data=f"sue:{sem}:{dia}:6.5")],
        [InlineKeyboardButton("7-8h",        callback_data=f"sue:{sem}:{dia}:7.5"),
         InlineKeyboardButton("8h+",         callback_data=f"sue:{sem}:{dia}:8.5")],
        [InlineKeyboardButton("Saltar",      callback_data="m:hoy")],
    ])
    try:
        await query.edit_message_text(
            "Guardado\n\nCuantas horas dormiste anoche?\n"
            "El sueno es donde crece el musculo.",
            reply_markup=sueño_kb)
    except Exception: pass


async def handle_sue(query, uid: int):
    parts = query.data.split(":")
    horas = float(parts[3])
    from db.database import upsert_usuario
    upsert_usuario(uid, sueño_horas=horas)
    aviso = "\nMenos de 6h reduce la sintesis proteica un 30%." if horas < 6 else ""
    try:
        await query.edit_message_text(
            f"{horas}h registradas.{aviso}\n\nEl analisis llega esta noche.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Ver siguiente sesion", callback_data="m:hoy")
            ]]))
    except Exception: pass


async def handle_ej_swap(query, uid: int, context):
    """Muestra hasta 4 alternativas para el ejercicio actual."""
    parts = query.data.split(":")
    sem, dia, idx = int(parts[1]), parts[2], int(parts[3])
    fuerza, _ = _split_rows(uid, sem, dia)
    if idx >= len(fuerza):
        return
    ej = fuerza[idx]

    u = get_usuario(uid) or {}
    ambiente = u.get("ambiente", "gym")
    limitacion = u.get("limitaciones", "ninguna")
    from engine.gym.planner import LIMITA_EJERCICIOS
    excl_patron = LIMITA_EJERCICIOS.get(limitacion.split(",")[0] if limitacion else "ninguna", [])

    alternativas = buscar_alternativas(ej["ejercicio_id"], ambiente=ambiente,
                                       excluir_patron=excl_patron, n=4)

    if not alternativas:
        try:
            await query.answer("No hay alternativas disponibles para este ejercicio en tu ambiente.", show_alert=True)
        except Exception: pass
        return

    rows = []
    for alt in alternativas:
        rows.append([InlineKeyboardButton(
            alt.nombre, callback_data=f"ej_swp2:{sem}:{dia}:{idx}:{alt.id}"
        )])
    rows.append([InlineKeyboardButton("Cancelar — mantener actual", callback_data=f"ej_swp2:{sem}:{dia}:{idx}:cancel")])

    try:
        await query.edit_message_text(
            f"<b>Cambiar: {ej['ejercicio']}</b>\n\n"
            f"Elige una alternativa para el mismo grupo muscular:",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
    except Exception: pass


async def handle_ej_swap_pick(query, uid: int, context):
    """Aplica la sustitución elegida — afecta todas las semanas del ciclo actual."""
    parts = query.data.split(":")
    sem, dia, idx, nuevo_id = int(parts[1]), parts[2], int(parts[3]), parts[4]

    if nuevo_id == "cancel":
        txt, kb = _render_ejercicio(uid, sem, dia, idx, context)
        try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
        except Exception: pass
        return

    fuerza, _ = _split_rows(uid, sem, dia)
    if idx >= len(fuerza):
        return
    ej_viejo = fuerza[idx]

    from engine.gym.catalog import BY_ID
    nuevo = BY_ID.get(nuevo_id)
    if not nuevo:
        return

    sustituir_ejercicio(uid, dia, ej_viejo["ejercicio_id"],
                        {"id": nuevo.id, "nombre": nuevo.nombre, "patron": nuevo.patron},
                        todas_las_semanas=True)

    # Limpiar cualquier ajuste de peso en sesión del ejercicio viejo
    pesos_sesion = context.user_data.get("pesos_sesion", {})
    pesos_sesion.pop(ej_viejo["ejercicio_id"], None)

    txt, kb = _render_ejercicio(uid, sem, dia, idx, context)
    try:
        await query.edit_message_text(
            f"Cambiado a <b>{nuevo.nombre}</b> ✅ <i>(aplica a todas las semanas de este ciclo)</i>\n\n" + txt,
            reply_markup=kb, parse_mode="HTML")
    except Exception:
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")


async def handle_skip(query, uid: int):
    parts = query.data.split(":")
    sem, dia = int(parts[1]), parts[2]
    nueva_sem, nuevo_dia = avanzar_dia(uid, sem, dia)
    set_estado(uid, nueva_sem, nuevo_dia)
    await query.edit_message_text(
        "Dia saltado.\n\nToca Rutina de hoy cuando estes listo.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Menu", callback_data="m:main")
        ]]))
