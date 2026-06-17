"""
bot/widgets.py — Invisible Coach v4.0

Widgets reutilizables de UI para Telegram (sin escribir texto):
  - Calendario inline (año → mes → día) para fecha de nacimiento
  - Teclado numérico inline para peso/altura (primera vez)
  - Steppers +/- para ajustes posteriores
"""
from __future__ import annotations
import calendar as _cal
from datetime import date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


# ══════════════════════════════════════════════════════════════════════════════
# CALENDARIO — fecha de nacimiento
# callback_data: "cal:Y:<año>" | "cal:M:<año>:<mes>" | "cal:D:<año>:<mes>:<dia>"
#                "cal:ynav:<base_año>" | "cal:mnav:<año>"
# ══════════════════════════════════════════════════════════════════════════════

def kb_calendario_anio(base: int | None = None) -> InlineKeyboardMarkup:
    """Grid de 12 años. base = año más reciente mostrado (arriba-derecha)."""
    hoy = date.today().year
    if base is None:
        base = hoy - 18  # default: empezar mostrando ~18 años atrás
    años = list(range(base - 11, base + 1))
    rows = []
    for i in range(0, 12, 4):
        rows.append([InlineKeyboardButton(str(a), callback_data=f"cal:Y:{a}") for a in años[i:i+4]])
    rows.append([
        InlineKeyboardButton("◀ -12", callback_data=f"cal:ynav:{base-12}"),
        InlineKeyboardButton("+12 ▶", callback_data=f"cal:ynav:{min(base+12, hoy)}"),
    ])
    return InlineKeyboardMarkup(rows)


def kb_calendario_mes(año: int) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, 12, 4):
        rows.append([
            InlineKeyboardButton(MESES[m], callback_data=f"cal:M:{año}:{m+1}")
            for m in range(i, i+4)
        ])
    rows.append([InlineKeyboardButton("← Cambiar año", callback_data="cal:back_year")])
    return InlineKeyboardMarkup(rows)


def kb_calendario_dia(año: int, mes: int) -> InlineKeyboardMarkup:
    _, n_dias = _cal.monthrange(año, mes)
    rows = []
    dias = list(range(1, n_dias + 1))
    for i in range(0, len(dias), 7):
        rows.append([
            InlineKeyboardButton(str(d), callback_data=f"cal:D:{año}:{mes}:{d}")
            for d in dias[i:i+7]
        ])
    rows.append([InlineKeyboardButton("← Cambiar mes", callback_data=f"cal:back_month:{año}")])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════════════════════════════
# TECLADO NUMÉRICO — peso/altura primera vez
# callback_data: "num:<campo>:d:<digito>" | "num:<campo>:back" | "num:<campo>:ok"
# ══════════════════════════════════════════════════════════════════════════════

def kb_numerico(campo: str, valor_actual: str = "") -> InlineKeyboardMarkup:
    """Teclado tipo calculadora. campo = 'peso' | 'altura'.
    Layout SIEMPRE fijo (mismo número de filas) para que Telegram no
    tenga que redimensionar el mensaje en cada tap — eso es lo que
    causaba la sensación de lentitud."""
    rows = [
        [InlineKeyboardButton(str(n), callback_data=f"num:{campo}:d:{n}") for n in range(1,4)],
        [InlineKeyboardButton(str(n), callback_data=f"num:{campo}:d:{n}") for n in range(4,7)],
        [InlineKeyboardButton(str(n), callback_data=f"num:{campo}:d:{n}") for n in range(7,10)],
        [
            InlineKeyboardButton(".", callback_data=f"num:{campo}:d:."),
            InlineKeyboardButton("0", callback_data=f"num:{campo}:d:0"),
            InlineKeyboardButton("⌫", callback_data=f"num:{campo}:back"),
        ],
    ]
    tiene_valor = bool(valor_actual) and valor_actual != "0"
    label = "✅ Confirmar" if tiene_valor else "Escribe un número..."
    cb    = f"num:{campo}:ok" if tiene_valor else f"num:{campo}:noop"
    rows.append([InlineKeyboardButton(label, callback_data=cb)])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════════════════════════════
# STEPPERS — ajustes rápidos +/- (peso corporal, pesos de gym)
# callback_data: "step:<campo>:<delta>" | "step:<campo>:ok"
# ══════════════════════════════════════════════════════════════════════════════

def kb_stepper(campo: str, unidad: str = "kg", pasos: tuple = (-20,-10,-5,5,10,20)) -> InlineKeyboardMarkup:
    botones = []
    for p in pasos:
        signo = "+" if p > 0 else ""
        botones.append(InlineKeyboardButton(f"{signo}{p}", callback_data=f"step:{campo}:{p}"))
    rows = [botones[:3], botones[3:]]
    rows.append([InlineKeyboardButton("✅ Confirmar", callback_data=f"step:{campo}:ok")])
    return InlineKeyboardMarkup(rows)


def kb_stepper_lbs(campo: str, pasos: tuple = (-10,-5,-2.5,2.5,5,10)) -> InlineKeyboardMarkup:
    """Para pesos de gimnasio en lbs — incrementos más finos."""
    botones = []
    for p in pasos:
        signo = "+" if p > 0 else ""
        label = f"{signo}{p:g}"
        botones.append(InlineKeyboardButton(label, callback_data=f"step:{campo}:{p}"))
    rows = [botones[:3], botones[3:]]
    rows.append([InlineKeyboardButton("✅ Usar este peso", callback_data=f"step:{campo}:ok")])
    rows.append([InlineKeyboardButton("⏭️ Saltar", callback_data=f"step:{campo}:skip")])
    return InlineKeyboardMarkup(rows)
