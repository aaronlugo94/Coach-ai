"""
engine/growth/cards.py — Invisible Coach v4.0 (Sesión 14)

Genera imágenes PNG compartibles (formato Instagram Stories 4:5)
con la racha y progresión de fuerza del usuario.

Diseño: mismo sistema visual que la web app (negro, acentos
verde #1D9E75 / naranja #FF6B00, tipografía DejaVu Sans Bold).

No usa emoji — DejaVu no los renderiza (se ven como "tofu" / cuadros).
Toda la jerarquía visual se logra con tamaño, color y barras.
"""
from __future__ import annotations
import io
import os
from PIL import Image, ImageDraw, ImageFont

# ── Paleta (igual que la web) ──────────────────────────────────────────────────
BG      = (0, 0, 0)
WHITE   = (255, 255, 255)
GRAY    = (85, 85, 85)
GRAY_LT = (170, 170, 170)
GREEN   = (29, 158, 117)
ORANGE  = (255, 107, 0)
CARD    = (17, 17, 17)
BORDER  = (34, 34, 34)

W, H = 1080, 1350  # 4:5 — formato Instagram Stories/Post vertical
PAD  = 70

FONT_BOLD_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_REG_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def generar_card_progreso(datos: dict) -> bytes:
    """
    Genera la card de racha + progresión semanal.

    datos = {
        "nombre": str — nombre/usuario a mostrar
        "racha": int — días consecutivos
        "progresiones": [
            {"ejercicio": str, "peso_inicio": float, "peso_actual": float},
            ...  (máx 3, se usan las primeras)
        ]
    }

    Retorna bytes PNG listos para enviar con send_photo.
    """
    nombre       = datos.get("nombre", "")
    racha        = int(datos.get("racha", 0))
    progresiones = (datos.get("progresiones") or [])[:3]

    img = Image.new("RGB", (W, H), BG)
    d   = ImageDraw.Draw(img)

    f_label   = _font(FONT_BOLD_PATHS, 28)
    f_huge    = _font(FONT_BOLD_PATHS, 220)
    f_unit    = _font(FONT_BOLD_PATHS, 46)
    f_brand   = _font(FONT_BOLD_PATHS, 32)
    f_small   = _font(FONT_REG_PATHS, 30)
    f_ex_name = _font(FONT_BOLD_PATHS, 34)

    # ── Header ────────────────────────────────────────────────────────────────
    d.text((PAD, 70), "INVISIBLE COACH", font=f_brand, fill=GRAY_LT)
    if nombre:
        d.text((PAD, 130), nombre, font=f_small, fill=GRAY)

    # ── Racha — número gigante ───────────────────────────────────────────────
    d.text((PAD, 240), "RACHA ACTUAL", font=f_label, fill=ORANGE)

    racha_str = str(max(racha, 0))
    bbox_num  = d.textbbox((0, 0), racha_str, font=f_huge)
    num_h     = bbox_num[3] - bbox_num[1]
    d.text((PAD, 280), racha_str, font=f_huge, fill=WHITE)
    num_right = d.textbbox((PAD, 280), racha_str, font=f_huge)[2]

    label_y = 280 + num_h // 2 - 60
    dia_label = "DÍA" if racha == 1 else "DÍAS"
    d.text((num_right + 25, label_y),      dia_label,       font=f_unit, fill=GRAY_LT)
    d.text((num_right + 25, label_y + 60), "CONSECUTIVOS",  font=f_unit, fill=GRAY_LT)

    y = 620
    d.line([(PAD, y), (W - PAD, y)], fill=BORDER, width=2)

    # ── Progresión de fuerza ───────────────────────────────────────────────────
    y += 60
    d.text((PAD, y), "PROGRESIÓN ESTA SEMANA", font=f_label, fill=GREEN)
    y += 70

    bar_max_w = W - 2 * PAD
    bar_h     = 24
    scale     = 200  # lbs — referencia visual para el largo de la barra

    if progresiones:
        for p in progresiones:
            nombre_ej = str(p.get("ejercicio", ""))[:30]
            inicio    = float(p.get("peso_inicio", 0))
            actual    = float(p.get("peso_actual", 0))

            d.text((PAD, y), nombre_ej, font=f_ex_name, fill=WHITE)
            y += 50

            d.rounded_rectangle([PAD, y, PAD + bar_max_w, y + bar_h], radius=12, fill=CARD)
            fill_w = max(int(bar_max_w * min(actual / scale, 1)), bar_h) if actual > 0 else 0
            if fill_w:
                d.rounded_rectangle([PAD, y, PAD + fill_w, y + bar_h], radius=12, fill=GREEN)
            y += bar_h + 16

            cambio = actual - inicio
            signo  = "+" if cambio >= 0 else ""
            d.text((PAD, y), f"{inicio:g} \u2192 {actual:g} lbs   ({signo}{cambio:g})",
                   font=f_small, fill=GRAY_LT)
            y += 70
    else:
        d.text((PAD, y), "Sigue entrenando — tu progresión", font=f_small, fill=GRAY_LT)
        y += 40
        d.text((PAD, y), "de fuerza aparecerá aquí.", font=f_small, fill=GRAY_LT)
        y += 70

    # ── Footer ────────────────────────────────────────────────────────────────
    d.line([(PAD, H - 150), (W - PAD, H - 150)], fill=BORDER, width=2)
    d.text((PAD, H - 110), "Mide lo invisible.", font=f_ex_name, fill=WHITE)
    d.text((PAD, H - 60), "invisiblecoach.app", font=f_small, fill=GRAY)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
