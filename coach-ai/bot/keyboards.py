"""
bot/keyboards.py — Todos los teclados del bot en un solo lugar.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

# ── TECLADO PERSISTENTE ───────────────────────────────────────────────────────
TECLADO_PRINCIPAL = ReplyKeyboardMarkup([
    ["💪 Rutina de hoy", "⚖️ Mi cuerpo"],
    ["🥗 Mi dieta",      "❓ Ayuda"],
], resize_keyboard=True, is_persistent=True)

# ── MENÚ INLINE ───────────────────────────────────────────────────────────────
MENU_INLINE = InlineKeyboardMarkup([
    [InlineKeyboardButton("💪 Rutina de hoy", callback_data="m:hoy"),
     InlineKeyboardButton("⚖️ Mi cuerpo",     callback_data="m:cuerpo")],
    [InlineKeyboardButton("🥗 Mi dieta",      callback_data="m:dieta"),
     InlineKeyboardButton("🔄 Nuevo plan",    callback_data="m:nuevo")],
])

BTN_MENU = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú", callback_data="m:main")]])

# ── ONBOARDING ────────────────────────────────────────────────────────────────
def kb_objetivos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Bajar grasa / perder peso",   callback_data="ob:bajar_grasa")],
        [InlineKeyboardButton("💪 Ganar músculo y fuerza",      callback_data="ob:ganar_musculo")],
        [InlineKeyboardButton("⚡ Bajar grasa Y ganar músculo", callback_data="ob:recomposicion")],
        [InlineKeyboardButton("🍑 Glúteo y pierna",            callback_data="ob:gluteo_pierna")],
        [InlineKeyboardButton("🏃 Salud y energía",            callback_data="ob:salud")],
        [InlineKeyboardButton("🏆 Nivel competitivo",          callback_data="ob:competitivo")],
    ])

def kb_nivel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌱 Menos de 1 año — soy nuevo",     callback_data="nv:principiante")],
        [InlineKeyboardButton("💪 1 a 3 años entrenando",         callback_data="nv:intermedio")],
        [InlineKeyboardButton("🔥 Más de 3 años — nivel avanzado",callback_data="nv:avanzado")],
        [InlineKeyboardButton("← Atrás",                           callback_data="ob:back")],
    ])

def kb_ambiente() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏋️ Gimnasio — máquinas y barras", callback_data="am:gym")],
        [InlineKeyboardButton("🏠 Casa — peso corporal",          callback_data="am:home")],
        [InlineKeyboardButton("🦺 Casa con banda elástica",       callback_data="am:band")],
        [InlineKeyboardButton("← Atrás",                          callback_data="nv:back")],
    ])

def kb_dias() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("3 días", callback_data="dy:3"),
         InlineKeyboardButton("4 días", callback_data="dy:4")],
        [InlineKeyboardButton("5 días", callback_data="dy:5"),
         InlineKeyboardButton("6 días", callback_data="dy:6")],
        [InlineKeyboardButton("← Atrás", callback_data="am:back")],
    ])

def kb_limitaciones() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ninguna",               callback_data="lm:ninguna")],
        [InlineKeyboardButton("🦵 Rodilla",              callback_data="lm:rodilla")],
        [InlineKeyboardButton("🔙 Espalda baja",         callback_data="lm:espalda")],
        [InlineKeyboardButton("💪 Hombro",               callback_data="lm:hombro")],
        [InlineKeyboardButton("← Atrás",                  callback_data="dy:back")],
    ])

def kb_horario(back: str = "lm:back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 6am", callback_data="hr:06:00"),
         InlineKeyboardButton("🌅 7am", callback_data="hr:07:00"),
         InlineKeyboardButton("🌅 8am", callback_data="hr:08:00")],
        [InlineKeyboardButton("☀️ 12pm", callback_data="hr:12:00"),
         InlineKeyboardButton("🌆 5pm",  callback_data="hr:17:00"),
         InlineKeyboardButton("🌆 6pm",  callback_data="hr:18:00")],
        [InlineKeyboardButton("🌙 7pm",  callback_data="hr:19:00"),
         InlineKeyboardButton("🌙 8pm",  callback_data="hr:20:00"),
         InlineKeyboardButton("🌙 9pm",  callback_data="hr:21:00")],
        [InlineKeyboardButton("❌ Sin recordatorio", callback_data="hr:none")],
        [InlineKeyboardButton("← Atrás", callback_data=back)],
    ])

def kb_dieta() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍗 Como de todo",        callback_data="dt:omnivoro")],
        [InlineKeyboardButton("🥗 Trato de comer sano", callback_data="dt:saludable")],
        [InlineKeyboardButton("🌱 Vegetariano/vegano",  callback_data="dt:vegano")],
        [InlineKeyboardButton("🍖 Alta en proteína",    callback_data="dt:proteina")],
        [InlineKeyboardButton("← Atrás",               callback_data="hr:back")],
    ])

def kb_restricciones(sel: set) -> InlineKeyboardMarkup:
    OPTS = [
        ("🥛","Sin lácteos","lacteos"), ("🌾","Sin gluten","gluten"),
        ("🥜","Sin maní","mani"),       ("🥚","Sin huevo","huevo"),
        ("🦐","Sin mariscos","mariscos"),("🐖","Sin cerdo","cerdo"),
        ("🌱","Vegano","vegano"),        ("🌽","Sin maíz","maiz"),
    ]
    rows = []
    for i in range(0, len(OPTS), 2):
        row = []
        for emoji, label, key in OPTS[i:i+2]:
            mark = "☑️" if key in sel else "⬜"
            row.append(InlineKeyboardButton(f"{mark} {emoji} {label}", callback_data=f"rt:{key}"))
        rows.append(row)
    n = len(sel)
    rows.append([InlineKeyboardButton("✏️ Otra restricción...", callback_data="rt:otra")])
    rows.append([InlineKeyboardButton(
        f"✅ Confirmar ({n})" if n else "✅ Ninguna — continuar",
        callback_data="rt:ok"
    )])
    rows.append([InlineKeyboardButton("← Atrás", callback_data="dt:back")])
    return InlineKeyboardMarkup(rows)

# ── EJERCICIOS — TAP ONLY ─────────────────────────────────────────────────────
def kb_ejercicio(semana: int, dia: str, idx: int,
                 peso: float, eid: str, inc: float = 5.0) -> InlineKeyboardMarkup:
    s, d, i = semana, dia, idx
    p_m = round(peso - inc, 1)
    p_p = round(peso + inc, 1)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"−{inc:.0f}", callback_data=f"pw:{s}:{d}:{i}:{p_m}"),
         InlineKeyboardButton(f"💪 {peso:.1f} lbs", callback_data=f"pw:{s}:{d}:{i}:{peso}"),
         InlineKeyboardButton(f"+{inc:.0f}", callback_data=f"pw:{s}:{d}:{i}:{p_p}")],
        [InlineKeyboardButton(f"✅ Hecho — {peso:.1f} lbs", callback_data=f"ej_ok:{s}:{d}:{i}:{peso}")],
        [InlineKeyboardButton("🔄 Cambiar",  callback_data=f"swp:{eid}:{s}:{d}"),
         InlineKeyboardButton("⏭ Saltar",   callback_data=f"ej_ok:{s}:{d}:{i}:0"),
         InlineKeyboardButton("🏠",          callback_data="m:main")],
    ])

def kb_peso_inicial(semana: int, dia: str, idx: int) -> InlineKeyboardMarkup:
    s, d, i = semana, dia, idx
    opciones = [("🟢 Barra vacía", 45), ("🟡 65 lbs", 65), ("🟠 95 lbs", 95),
                ("🔴 135 lbs", 135),    ("⚡ 185 lbs", 185), ("💀 225+ lbs", 225)]
    rows = []
    for j in range(0, len(opciones), 3):
        rows.append([
            InlineKeyboardButton(label, callback_data=f"ej_ok:{s}:{d}:{i}:{peso}")
            for label, peso in opciones[j:j+3]
        ])
    rows.append([InlineKeyboardButton("✏️ Otro peso", callback_data=f"ej_manual:{s}:{d}:{i}")])
    rows.append([InlineKeyboardButton("⏭ Saltar", callback_data=f"ej_ok:{s}:{d}:{i}:0")])
    return InlineKeyboardMarkup(rows)

def kb_feedback_sesion(semana: int, dia: str) -> InlineKeyboardMarkup:
    s, d = semana, dia
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Sin reserva",  callback_data=f"fb:{s}:{d}:0:5"),
         InlineKeyboardButton("💪 Bien",         callback_data=f"fb:{s}:{d}:2:3")],
        [InlineKeyboardButton("😌 Fácil",        callback_data=f"fb:{s}:{d}:3:2"),
         InlineKeyboardButton("😓 Muy cansado",  callback_data=f"fb:{s}:{d}:1:5")],
    ])
