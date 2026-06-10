"""
engine/gym/planner.py — Invisible Coach v3.0

Genera planes de 4 semanas con periodización científica:
  Semana 1: MEV  — Mínimo Volumen Efectivo (RIR 3)
  Semana 2: MAV  — Volumen de Adaptación Máxima (RIR 2)
  Semana 3: MRV  — Máximo Volumen Recuperable (RIR 1)
  Semana 4: Deload — Recuperación y supercompensación (RIR 4+)

Variables de adaptación:
  - Nivel del usuario (principiante/intermedio/avanzado)
  - Duración de sesión (45/60/90 min → número de ejercicios)
  - Estrés habitual (ajusta K_fatiga del modelo Bannister)
  - Limitaciones físicas (excluye patrones de movimiento)
  - Objetivo (prioriza grupos musculares)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .catalog import CATALOG, Ejercicio

DIAS_SEMANA = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]

# ── Configuración por semana ──────────────────────────────────────────────────

@dataclass
class SemanaConfig:
    label:        str
    series_p:     int    # series ejercicio principal
    series_a:     int    # series ejercicio accesorio
    reps_p:       str    # rango reps principal
    reps_a:       str    # rango reps accesorio
    rir:          int    # RIR objetivo
    deload:       bool = False

PERIODIZACION = {
    "principiante": {
        1: SemanaConfig("MEV",    3, 2, "12-15", "15",    rir=3),
        2: SemanaConfig("MAV",    3, 3, "10-12", "12-15", rir=2),
        3: SemanaConfig("MRV",    4, 3, "10-12", "12-15", rir=2),
        4: SemanaConfig("Deload", 2, 2, "15",    "15",    rir=4, deload=True),
    },
    "intermedio": {
        1: SemanaConfig("MEV",    4, 2, "10-12", "12-15", rir=3),
        2: SemanaConfig("MAV",    4, 3, "8-10",  "10-12", rir=2),
        3: SemanaConfig("MRV",    5, 3, "6-8",   "10-12", rir=1),
        4: SemanaConfig("Deload", 3, 2, "12-15", "15",    rir=4, deload=True),
    },
    "avanzado": {
        1: SemanaConfig("MEV",    4, 3, "8-10",  "10-12", rir=2),
        2: SemanaConfig("MAV",    5, 3, "6-8",   "8-10",  rir=1),
        3: SemanaConfig("MRV",    5, 4, "4-6",   "8-10",  rir=1),
        4: SemanaConfig("Deload", 3, 2, "10-12", "12-15", rir=4, deload=True),
    },
}

# ── Splits según días de entrenamiento ───────────────────────────────────────

SPLITS = {
    3: [
        ["empuje"],
        ["tiron"],
        ["pierna","gluteo"],
    ],
    4: [
        ["empuje"],
        ["tiron"],
        ["pierna"],
        ["gluteo","core"],
    ],
    5: [
        ["empuje"],
        ["tiron"],
        ["pierna"],
        ["gluteo"],
        ["empuje","tiron"],  # día extra — upper ligero
    ],
    6: [
        ["empuje"],
        ["tiron"],
        ["pierna"],
        ["gluteo"],
        ["empuje","core"],
        ["tiron"],
    ],
}

# Split ajustado por objetivo
SPLITS_OBJETIVO = {
    "gluteo": {
        4: [["gluteo"],["pierna","core"],["empuje"],["gluteo","tiron"]],
        5: [["gluteo"],["pierna"],["empuje"],["gluteo"],["tiron","core"]],
    },
    "mamado": {  # volumen — más días de empuje/tirón
        4: [["empuje"],["tiron"],["pierna"],["empuje","tiron"]],
    },
}

# ── Ejercicios máximos según duración de sesión ───────────────────────────────

EJERCICIOS_POR_DURACION = {
    45: {"principal": 2, "accesorio": 1},  # 45 min: denso, solo compuestos
    60: {"principal": 2, "accesorio": 2},  # 60 min: estándar
    90: {"principal": 2, "accesorio": 3},  # 90 min: completo
}

# ── Patrones excluidos por lesión ────────────────────────────────────────────

EXCLUSIONES_LESION = {
    "rodilla":  ["sentadilla","press_pierna"],
    "espalda":  ["peso_muerto","bisagra_cadera"],
    "hombro":   ["press_vertical","press_inclinado"],
    "ninguna":  [],
}

# ── Días de descanso entre sesiones ──────────────────────────────────────────

SALTOS_DESCANSO = {3: 2, 4: 2, 5: 1, 6: 1}


def _seleccionar(grupo: str, excl_patrones: list, ambiente: str,
                 rol: str = "principal", n: int = 3) -> list[Ejercicio]:
    """Selecciona ejercicios por grupo, rol y ambiente. Ordena por EMG score."""
    return sorted(
        [e for e in CATALOG
         if e.grupo == grupo
         and e.rol == rol
         and ambiente in e.ambiente
         and e.patron not in excl_patrones
         and not e.es_cardio],
        key=lambda e: -e.emg_score
    )[:n]


def _ejercicios_dia(grupos: list[str], cfg: SemanaConfig,
                    ambiente: str, excl: list,
                    max_princ: int, max_acc: int) -> list[dict]:
    """Genera la lista de ejercicios para un día según la configuración."""
    ejercicios = []
    orden = 0

    for grupo in grupos:
        # Principales
        princs = _seleccionar(grupo, excl, ambiente, "principal", max_princ + 1)
        for ej in princs[:max_princ]:
            ejercicios.append({
                "orden":        orden,
                "ejercicio_id": ej.id,
                "ejercicio":    ej.nombre,
                "grupo":        grupo,
                "patron":       ej.patron,
                "rol":          "principal",
                "series":       cfg.series_p,
                "reps":         cfg.reps_p,
                "rir_objetivo": cfg.rir,
                "notas":        ej.notas,
            })
            orden += 1

        # Accesorios
        accs = _seleccionar(grupo, excl, ambiente, "accesorio", max_acc + 1)
        for ej in accs[:max_acc]:
            ejercicios.append({
                "orden":        orden,
                "ejercicio_id": ej.id,
                "ejercicio":    ej.nombre,
                "grupo":        grupo,
                "patron":       ej.patron,
                "rol":          "accesorio",
                "series":       cfg.series_a,
                "reps":         cfg.reps_a,
                "rir_objetivo": cfg.rir + 1,
                "notas":        ej.notas,
            })
            orden += 1

    # Cardio al final en días de pierna/gluteo (zona 2 — 20 min)
    if any(g in grupos for g in ["pierna","gluteo"]):
        cardio = next(
            (e for e in CATALOG if e.es_cardio and ambiente in e.ambiente), None
        )
        if cardio:
            ejercicios.append({
                "orden":        orden,
                "ejercicio_id": cardio.id,
                "ejercicio":    cardio.nombre,
                "grupo":        "cardio",
                "patron":       "cardio",
                "rol":          "cardio",
                "series":       1,
                "reps":         "20 min",
                "rir_objetivo": 5,
                "notas":        cardio.notas,
                "es_cardio":    True,
            })

    return ejercicios


def generar_plan(nivel:       str = "intermedio",
                 objetivo:    str = "general",
                 dias:        int = 4,
                 ambiente:    str = "gym",
                 limitacion:  str = "ninguna",
                 duracion:    int = 60) -> list[dict]:
    """
    Genera el plan de 4 semanas completo.

    Args:
        nivel:      principiante | intermedio | avanzado
        objetivo:   general | peso | mamado | gluteo
        dias:       3-6 días de entrenamiento por semana
        ambiente:   gym | home | band
        limitacion: ninguna | rodilla | espalda | hombro
        duracion:   45 | 60 | 90 minutos por sesión

    Returns:
        Lista de 4 semanas con sus días y ejercicios.
    """
    nivel    = nivel    if nivel    in PERIODIZACION else "intermedio"
    dias     = max(3, min(6, dias))
    duracion = 45 if duracion <= 45 else 90 if duracion >= 90 else 60

    excl = EXCLUSIONES_LESION.get(limitacion, [])

    # Split según objetivo
    split = (SPLITS_OBJETIVO
             .get(objetivo, {})
             .get(dias, None)) or SPLITS.get(dias, SPLITS[4])

    # Límite de ejercicios por duración
    lim     = EJERCICIOS_POR_DURACION[duracion]
    max_p   = lim["principal"]
    max_a   = lim["accesorio"]

    # Salto de días entre sesiones
    salto = SALTOS_DESCANSO.get(dias, 2)

    semanas = []
    for num_sem in range(1, 5):
        cfg      = PERIODIZACION[nivel][num_sem]
        dias_sem = []
        dia_idx  = 0

        for grupos in split[:dias]:
            dia_nombre = DIAS_SEMANA[dia_idx % 7]
            ejs = _ejercicios_dia(grupos, cfg, ambiente, excl, max_p, max_a)
            dias_sem.append({
                "dia":        dia_nombre,
                "grupo":      grupos[0],
                "grupos":     grupos,
                "ejercicios": ejs,
            })
            dia_idx = (dia_idx + salto) % 7

        semanas.append({
            "semana": num_sem,
            "label":  cfg.label,
            "deload": cfg.deload,
            "dias":   dias_sem,
        })

    return semanas
