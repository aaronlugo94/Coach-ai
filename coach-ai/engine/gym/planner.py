"""
engine/gym/planner.py
Genera planes de 4 semanas con periodización MEV→MAV→MRV→Deload.
"""
from __future__ import annotations
from dataclasses import dataclass
from .catalog import CATALOG, Ejercicio

DIAS_SEMANA = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]

@dataclass
class SemanaConfig:
    series_princ: int
    series_acc:   int
    reps_princ:   str
    reps_acc:     str
    rir:          int
    deload:       bool = False

# MEV → MAV → MRV → Deload por nivel
PERIODIZACION = {
    "principiante": {
        1: SemanaConfig(3, 2, "12-15", "15",    rir=3),
        2: SemanaConfig(3, 3, "10-12", "12-15", rir=2),
        3: SemanaConfig(4, 3, "10-12", "12-15", rir=2),
        4: SemanaConfig(2, 2, "12-15", "15",    rir=4, deload=True),
    },
    "intermedio": {
        1: SemanaConfig(4, 2, "10-12", "12-15", rir=2),
        2: SemanaConfig(4, 3, "8-10",  "10-12", rir=2),
        3: SemanaConfig(5, 3, "6-8",   "10-12", rir=1),
        4: SemanaConfig(3, 2, "10-12", "15",    rir=4, deload=True),
    },
    "avanzado": {
        1: SemanaConfig(4, 3, "8-10",  "10-12", rir=2),
        2: SemanaConfig(5, 3, "6-8",   "8-10",  rir=1),
        3: SemanaConfig(5, 4, "5-6",   "8-10",  rir=1),
        4: SemanaConfig(3, 2, "10-12", "12-15", rir=4, deload=True),
    },
}

# Splits por días de entrenamiento
SPLITS = {
    3: [["empuje"],["tiron","core"],["pierna","gluteo"]],
    4: [["empuje"],["tiron"],["pierna","gluteo"],["empuje","core"]],
    5: [["empuje"],["tiron"],["pierna"],["gluteo","core"],["empuje","tiron"]],
    6: [["empuje"],["tiron"],["pierna"],["gluteo"],["empuje","core"],["tiron"]],
}

LIMITA_EJERCICIOS = {
    "rodilla":  ["sentadilla","peso_muerto"],
    "espalda":  ["peso_muerto","bisagra_cadera"],
    "hombro":   ["press_vertical"],
    "ninguna":  [],
}


def _seleccionar(grupo: str, patron_excl: list, ambiente: str,
                 rol: str = "principal", n: int = 1) -> list[Ejercicio]:
    candidatos = [
        e for e in CATALOG
        if e.grupo == grupo
        and e.rol == rol
        and ambiente in e.ambiente
        and e.patron not in patron_excl
        and not e.es_cardio
    ]
    candidatos.sort(key=lambda e: -e.emg_score)
    return candidatos[:n]


def _ejercicios_dia(grupos: list[str], cfg: SemanaConfig,
                    ambiente: str, excl_patrones: list) -> list[dict]:
    ejercicios = []
    orden = 0

    for grupo in grupos:
        # Principal
        princs = _seleccionar(grupo, excl_patrones, ambiente, "principal", 2)
        for ej in princs[:1]:
            ejercicios.append({
                "orden":        orden,
                "ejercicio_id": ej.id,
                "ejercicio":    ej.nombre,
                "grupo":        grupo,
                "patron":       ej.patron,
                "rol":          "principal",
                "series":       cfg.series_princ,
                "reps":         cfg.reps_princ,
                "rir_objetivo": cfg.rir,
                "notas":        ej.notas,
            })
            orden += 1

        # Accesorio
        accs = _seleccionar(grupo, excl_patrones, ambiente, "accesorio", 2)
        for ej in accs[:1]:
            ejercicios.append({
                "orden":        orden,
                "ejercicio_id": ej.id,
                "ejercicio":    ej.nombre,
                "grupo":        grupo,
                "patron":       ej.patron,
                "rol":          "accesorio",
                "series":       cfg.series_acc,
                "reps":         cfg.reps_acc,
                "rir_objetivo": cfg.rir + 1,
                "notas":        ej.notas,
            })
            orden += 1

    # Cardio al final si hay pierna o gluteo
    if any(g in grupos for g in ["pierna","gluteo"]):
        cardio = next((e for e in CATALOG if e.es_cardio and ambiente in e.ambiente), None)
        if cardio:
            ejercicios.append({
                "orden":        orden,
                "ejercicio_id": cardio.id,
                "ejercicio":    cardio.nombre,
                "grupo":        "cardio",
                "patron":       "cardio",
                "rol":          "cardio",
                "series":       1,
                "reps":         "20min",
                "rir_objetivo": 5,
                "notas":        cardio.notas,
                "es_cardio":    True,
            })

    return ejercicios


def generar_plan(nivel: str = "intermedio", objetivo: str = "general",
                 dias: int = 4, ambiente: str = "gym",
                 limitacion: str = "ninguna") -> list[dict]:
    """
    Genera plan de 4 semanas.
    Retorna lista de semanas con días y ejercicios.
    """
    nivel = nivel if nivel in PERIODIZACION else "intermedio"
    dias  = max(3, min(6, dias))
    split = SPLITS.get(dias, SPLITS[4])
    excl  = LIMITA_EJERCICIOS.get(limitacion, [])

    # Ajustar split según objetivo
    if objetivo == "gluteo":
        split = [["gluteo"],["pierna","core"],["empuje"],["gluteo","tiron"]][:dias]
    elif objetivo == "peso" and dias >= 4:
        # Más pierna — más masa muscular = más gasto calórico
        split[1 % len(split)] = ["pierna"]

    semanas = []
    for num_sem in range(1, 5):
        cfg       = PERIODIZACION[nivel][num_sem]
        dias_sem  = []
        dia_idx   = 0
        dias_activos = split[:dias]

        for grupos in dias_activos:
            dia_nombre = DIAS_SEMANA[dia_idx]
            ejs = _ejercicios_dia(grupos, cfg, ambiente, excl)
            dias_sem.append({
                "dia":        dia_nombre,
                "grupo":      grupos[0],
                "ejercicios": ejs,
            })
            # Saltar día de descanso entre sesiones para splits de 3-4 días
            if dias <= 4:
                dia_idx = (dia_idx + 2) % 7
            else:
                dia_idx = (dia_idx + 1) % 7

        semanas.append({"semana": num_sem, "dias": dias_sem, "deload": cfg.deload})

    return semanas
