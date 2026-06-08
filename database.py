"""
db/database.py — Capa de acceso a datos.

Una sola fuente de verdad para todas las queries.
Sin lógica de negocio aquí — solo SQL.
"""
from __future__ import annotations
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/app/data/coach.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Inicializa la DB con el schema completo."""
    schema_path = Path(__file__).parent / "schema.sql"
    with get_db() as conn:
        conn.executescript(schema_path.read_text())
    logger.info("DB inicializada: %s", DB_PATH)


def execute(sql: str, params: tuple = ()) -> None:
    with get_db() as conn:
        conn.execute(sql, params)


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    with get_db() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# USUARIOS
# ══════════════════════════════════════════════════════════════════════════════

def get_allowed_users() -> set[int]:
    rows = fetchall("SELECT user_id FROM usuarios_permitidos", ())
    return {r["user_id"] for r in rows}


def add_allowed_user(uid: int) -> None:
    execute("INSERT OR IGNORE INTO usuarios_permitidos (user_id) VALUES (?)", (uid,))


def get_usuario(uid: int) -> dict | None:
    return fetchone("SELECT * FROM usuarios WHERE user_id=?", (uid,))


def upsert_usuario(uid: int, **kwargs) -> None:
    """Inserta o actualiza campos del usuario. Solo columnas válidas."""
    COLUMNAS = {
        "nombre","objetivo_vida","objetivo_gym","sexo","edad","peso_kg","altura_cm",
        "bmr","tdee","actividad_nivel","nivel","ambiente","dias_semana","limitaciones",
        "hora_reminder","tipo_dieta","alergias","cocina","patron_comidas","ventana_comida",
        "donde_come","suplementos","alcohol","google_fit_token","google_fit_email",
        "renpho_email","renpho_password","ciclo_actual","onboarding_done","sueño_horas",
    }
    kwargs = {k: v for k, v in kwargs.items() if k in COLUMNAS}
    if not kwargs:
        return

    cols   = ", ".join(kwargs.keys())
    vals   = ", ".join("?" * len(kwargs))
    sets   = ", ".join(f"{k}=excluded.{k}" for k in kwargs)
    params = (*kwargs.values(), uid)

    execute(
        f"INSERT INTO usuarios (user_id, {cols}) VALUES (?, {vals}) "
        f"ON CONFLICT(user_id) DO UPDATE SET {sets}",
        (uid, *kwargs.values()),
    )


def has_plan(uid: int) -> bool:
    row = fetchone(
        "SELECT COUNT(*) as n FROM rutinas WHERE user_id=? AND ciclo=("
        "SELECT ciclo_actual FROM usuarios WHERE user_id=?)",
        (uid, uid)
    )
    return (row["n"] if row else 0) > 0


def get_onboarding_done(uid: int) -> bool:
    row = fetchone("SELECT onboarding_done FROM usuarios WHERE user_id=?", (uid,))
    return bool(row["onboarding_done"]) if row else False


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO DEL PLAN
# ══════════════════════════════════════════════════════════════════════════════

def get_estado(uid: int) -> tuple[int, str]:
    row = fetchone("SELECT semana, dia FROM estado_plan WHERE user_id=?", (uid,))
    return (row["semana"], row["dia"]) if row else (1, "lunes")


def set_estado(uid: int, semana: int, dia: str) -> None:
    execute(
        "INSERT INTO estado_plan (user_id, semana, dia) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET semana=excluded.semana, dia=excluded.dia, "
        "updated_at=datetime('now')",
        (uid, semana, dia),
    )


def avanzar_dia(uid: int, semana: int, dia: str) -> tuple[int, str]:
    """Calcula el siguiente día de entrenamiento."""
    DIAS = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]

    dias_con_rutina = [
        r["dia"] for r in fetchall(
            "SELECT DISTINCT dia FROM rutinas WHERE user_id=? AND ciclo=? AND semana=? ORDER BY orden",
            (uid, _get_ciclo(uid), semana)
        )
    ]
    if not dias_con_rutina:
        return semana, dia

    try:
        idx_actual = dias_con_rutina.index(dia)
    except ValueError:
        idx_actual = -1

    if idx_actual + 1 < len(dias_con_rutina):
        return semana, dias_con_rutina[idx_actual + 1]
    else:
        # Siguiente semana
        nueva_semana = semana + 1 if semana < 4 else 1
        if nueva_semana == 1:
            # Nuevo ciclo
            _incrementar_ciclo(uid)
        nuevos_dias = [
            r["dia"] for r in fetchall(
                "SELECT DISTINCT dia FROM rutinas WHERE user_id=? AND ciclo=? AND semana=? ORDER BY orden",
                (uid, _get_ciclo(uid), nueva_semana)
            )
        ]
        return nueva_semana, (nuevos_dias[0] if nuevos_dias else "lunes")


def _get_ciclo(uid: int) -> int:
    row = fetchone("SELECT ciclo_actual FROM usuarios WHERE user_id=?", (uid,))
    return row["ciclo_actual"] if row else 1


def _incrementar_ciclo(uid: int) -> None:
    execute(
        "UPDATE usuarios SET ciclo_actual = ciclo_actual + 1 WHERE user_id=?", (uid,)
    )


# ══════════════════════════════════════════════════════════════════════════════
# RUTINAS
# ══════════════════════════════════════════════════════════════════════════════

def get_ejercicios_dia(uid: int, semana: int, dia: str) -> list[dict]:
    ciclo = _get_ciclo(uid)
    return fetchall(
        "SELECT * FROM rutinas WHERE user_id=? AND ciclo=? AND semana=? AND dia=? "
        "ORDER BY orden",
        (uid, ciclo, semana, dia)
    )


def insert_plan(uid: int, semanas: list[dict]) -> int:
    """Inserta el plan generado por el planner."""
    ciclo = _get_ciclo(uid)
    n = 0
    with get_db() as conn:
        # Limpiar plan actual de este ciclo
        conn.execute(
            "DELETE FROM rutinas WHERE user_id=? AND ciclo=?", (uid, ciclo)
        )
        for sem in semanas:
            for dia_data in sem["dias"]:
                for ej in dia_data["ejercicios"]:
                    conn.execute("""
                        INSERT INTO rutinas
                        (user_id, ciclo, semana, dia, orden, ejercicio_id, ejercicio,
                         grupo, patron, rol, series, reps, rir_objetivo, notas,
                         es_cardio)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        uid, ciclo,
                        sem["semana"], dia_data["dia"],
                        ej.get("orden", 0),
                        ej["ejercicio_id"], ej["ejercicio"],
                        dia_data.get("grupo", ej.get("grupo","")),
                        ej.get("patron",""),
                        ej.get("rol","principal"),
                        ej.get("series", 3),
                        ej.get("reps","8-10"),
                        ej.get("rir_objetivo", 2),
                        ej.get("notas",""),
                        1 if ej.get("es_cardio") else 0,
                    ))
                    n += 1
    logger.info("Plan insertado uid=%s ciclo=%s: %d ejercicios", uid, ciclo, n)
    return n


def marcar_completado(uid: int, semana: int, dia: str) -> None:
    ciclo = _get_ciclo(uid)
    execute(
        "UPDATE rutinas SET completado=1 WHERE user_id=? AND ciclo=? AND semana=? AND dia=?",
        (uid, ciclo, semana, dia)
    )


def save_swap(uid: int, orig_id: str, nuevo_id: str, grupo: str, motivo: str = "preferencia") -> None:
    execute(
        "INSERT INTO swaps (user_id, ejercicio_orig, ejercicio_nuevo, grupo, motivo) "
        "VALUES (?,?,?,?,?)",
        (uid, orig_id, nuevo_id, grupo, motivo)
    )
    ciclo = _get_ciclo(uid)
    execute(
        "UPDATE rutinas SET ejercicio_id=?, swap_original=? "
        "WHERE user_id=? AND ciclo=? AND ejercicio_id=?",
        (nuevo_id, orig_id, uid, ciclo, orig_id)
    )


# ══════════════════════════════════════════════════════════════════════════════
# PESOS
# ══════════════════════════════════════════════════════════════════════════════

def save_peso(uid: int, ejercicio_id: str, semana: int, dia: str,
              peso_lbs: float, reps: str = None, series: int = None,
              rir_real: int = None) -> None:
    ciclo = _get_ciclo(uid)
    execute("""
        INSERT INTO pesos
        (user_id, ejercicio_id, ciclo, semana, dia, peso_lbs,
         reps_completadas, series_completadas, rir_real)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (uid, ejercicio_id, ciclo, semana, dia, peso_lbs, reps, series, rir_real))


def get_historial_peso(uid: int, ejercicio_id: str, limit: int = 6) -> list[dict]:
    """Últimos N registros de peso de un ejercicio."""
    return fetchall("""
        SELECT peso_lbs, reps_completadas, rir_real, semana, fecha
        FROM pesos
        WHERE user_id=? AND ejercicio_id=?
        ORDER BY fecha DESC LIMIT ?
    """, (uid, ejercicio_id, limit))


def get_peso_sugerido(uid: int, ejercicio_id: str, reps_objetivo: str = "8-10",
                      patron: str = "") -> float | None:
    """
    Doble progresión (Schoenfeld 2021):
    - Si llegó al límite superior de reps 2 sesiones → sube peso
    - Incremento: 5 lbs compuestos, 2.5 lbs accesorios
    """
    hist = get_historial_peso(uid, ejercicio_id, limit=4)
    if not hist:
        return None

    peso_actual = float(hist[0]["peso_lbs"])

    # Incremento por tipo
    COMPUESTOS = {
        "sentadilla","press_horizontal","press_inclinado","press_vertical",
        "bisagra_cadera","remo_horizontal","jalon_vertical","peso_muerto",
    }
    incremento = 5.0 if patron in COMPUESTOS else 2.5

    # Rango objetivo
    try:
        if "-" in reps_objetivo:
            _, rep_max = map(int, reps_objetivo.split("-"))
        else:
            rep_max = int(reps_objetivo.replace("+",""))
    except Exception:
        rep_max = 10

    # ¿Llegó al tope 2 veces seguidas?
    reps_recientes = []
    for h in hist[:2]:
        r = h.get("reps_completadas","")
        if not r:
            continue
        try:
            reps_recientes.append(int(str(r).split("-")[0]))
        except Exception:
            pass

    if len(reps_recientes) >= 2 and all(r >= rep_max for r in reps_recientes):
        return round(peso_actual + incremento, 1)

    return round(peso_actual, 1)


# ══════════════════════════════════════════════════════════════════════════════
# SESIONES
# ══════════════════════════════════════════════════════════════════════════════

def save_sesion(uid: int, semana: int, dia: str, **kwargs) -> None:
    ciclo = _get_ciclo(uid)
    COLS = {"grupo","completada","fatiga_global","rir_promedio",
            "sueño_horas","duracion_min","notas_usuario"}
    kwargs = {k: v for k, v in kwargs.items() if k in COLS}
    cols   = ", ".join(kwargs.keys())
    vals   = ", ".join("?" * len(kwargs))
    params = (uid, ciclo, semana, dia, *kwargs.values())
    execute(
        f"INSERT INTO sesiones (user_id, ciclo, semana, dia, {cols}) "
        f"VALUES (?,?,?,?,{vals})",
        params
    )


def get_sesion_activa(uid: int) -> dict | None:
    """Sesión activa en memoria del contexto del bot."""
    # Se guarda en user_data del bot, no en DB
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PESAJES CORPORALES
# ══════════════════════════════════════════════════════════════════════════════

def save_pesaje(uid: int, datos: dict) -> bool:
    """Guarda pesaje de Renpho. Retorna True si es nuevo."""
    ts = datos.get("Timestamp")
    existing = fetchone("SELECT id FROM pesajes WHERE timestamp=?", (ts,))
    if existing:
        return False
    execute("""
        INSERT INTO pesajes
        (user_id, fecha, timestamp, peso_kg, grasa_pct, musculo_pct, musculo_kg,
         agua_pct, grasa_visceral, bmr_medido, bmi, edad_metabolica, masa_osea,
         proteina_pct, fat_free_weight)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        uid,
        datos.get("Fecha"), ts,
        datos.get("Peso_kg"), datos.get("Grasa_Porcentaje"),
        datos.get("Musculo_Pct"), datos.get("Musculo_kg"),
        datos.get("Agua"), datos.get("VisFat"),
        datos.get("BMR"), datos.get("BMI"),
        datos.get("EdadMetabolica"), datos.get("MasaOsea"),
        datos.get("Proteina"), datos.get("FatFreeWeight"),
    ))
    return True


def get_ultimo_pesaje(uid: int) -> dict | None:
    return fetchone("""
        SELECT * FROM pesajes WHERE user_id=?
        ORDER BY fecha DESC LIMIT 1
    """, (uid,))


def get_pesajes_semana(uid: int, dias: int = 14) -> list[dict]:
    return fetchall("""
        SELECT fecha, peso_kg, grasa_pct, musculo_pct, grasa_visceral
        FROM pesajes WHERE user_id=?
        ORDER BY fecha DESC LIMIT ?
    """, (uid, dias))


# ══════════════════════════════════════════════════════════════════════════════
# ACTIVIDAD DIARIA (Google Fit)
# ══════════════════════════════════════════════════════════════════════════════

def save_actividad(uid: int, fecha: str, datos: dict) -> None:
    execute("""
        INSERT INTO actividad_diaria
        (user_id, fecha, pasos, calorias_activas, calorias_totales,
         minutos_actividad, distancia_km, hrv_promedio, fc_reposo,
         sueño_total_min, sueño_profundo_min, sueño_rem_min, sueño_ligero_min, fuente)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id, fecha) DO UPDATE SET
        pasos=excluded.pasos,
        calorias_activas=excluded.calorias_activas,
        hrv_promedio=excluded.hrv_promedio,
        sueño_total_min=excluded.sueño_total_min,
        sueño_profundo_min=excluded.sueño_profundo_min,
        sueño_rem_min=excluded.sueño_rem_min
    """, (
        uid, fecha,
        datos.get("pasos", 0),
        datos.get("calorias_activas", 0),
        datos.get("calorias_totales", 0),
        datos.get("minutos_actividad", 0),
        datos.get("distancia_km", 0),
        datos.get("hrv_promedio"),
        datos.get("fc_reposo"),
        datos.get("sueño_total_min"),
        datos.get("sueño_profundo_min"),
        datos.get("sueño_rem_min"),
        datos.get("sueño_ligero_min"),
        datos.get("fuente","google_fit"),
    ))


def get_actividad_hoy(uid: int) -> dict | None:
    from datetime import date
    return fetchone(
        "SELECT * FROM actividad_diaria WHERE user_id=? AND fecha=?",
        (uid, str(date.today()))
    )


def get_actividad_semana(uid: int, dias: int = 7) -> list[dict]:
    return fetchall("""
        SELECT fecha, pasos, calorias_activas, minutos_actividad,
               hrv_promedio, sueño_total_min, sueño_profundo_min
        FROM actividad_diaria WHERE user_id=?
        ORDER BY fecha DESC LIMIT ?
    """, (uid, dias))


# ══════════════════════════════════════════════════════════════════════════════
# NUTRICIÓN
# ══════════════════════════════════════════════════════════════════════════════

def get_plan_nutricion_activo(uid: int) -> dict | None:
    return fetchone("""
        SELECT * FROM planes_nutricion WHERE user_id=?
        ORDER BY generado_at DESC LIMIT 1
    """, (uid,))


def save_plan_nutricion(uid: int, datos: dict) -> None:
    execute("""
        INSERT INTO planes_nutricion
        (user_id, semana_inicio, kcal_objetivo, proteina_g, carbs_g, grasas_g,
         kcal_mult, estado_mimo, es_refeed, plan_html, ajuste_calorico, razon_ajuste)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        uid,
        datos["semana_inicio"],
        datos.get("kcal_objetivo"),
        datos.get("proteina_g"),
        datos.get("carbs_g"),
        datos.get("grasas_g"),
        datos.get("kcal_mult", 1.0),
        datos.get("estado_mimo"),
        1 if datos.get("es_refeed") else 0,
        datos.get("plan_html"),
        datos.get("ajuste_calorico", 0),
        datos.get("razon_ajuste"),
    ))


def calcular_ajuste_calorico(uid: int) -> dict:
    """
    SISO real: ajusta calorías basado en tendencia de peso.
    Compara promedio semanal vs semana anterior.
    """
    usuario = get_usuario(uid)
    if not usuario:
        return {"accion": "mantener", "kcal": 0, "razon": "sin perfil"}

    objetivo = usuario.get("objetivo_gym","general")
    peso_ref = float(usuario.get("peso_kg") or 90)

    metas = {
        "peso":    (-0.006, "bajar"),   # -0.6%/semana
        "mamado":  ( 0.003, "subir"),   # +0.3%/semana lean bulk
        "general": ( 0.0,   "mantener"),
        "gluteo":  (-0.003, "bajar"),
    }
    meta_pct, direccion = metas.get(objetivo, (0.0, "mantener"))

    if direccion == "mantener":
        return {"accion": "mantener", "kcal": 0, "razon": "recomposición — calorías estables"}

    pesajes = get_pesajes_semana(uid, dias=21)
    if len(pesajes) < 7:
        return {"accion": "mantener", "kcal": 0,
                "razon": f"necesito más datos — solo {len(pesajes)} pesajes"}

    pesos = [float(p["peso_kg"]) for p in pesajes if p.get("peso_kg")]
    if len(pesos) < 7:
        return {"accion": "mantener", "kcal": 0, "razon": "datos insuficientes"}

    sem_rec  = sum(pesos[:7]) / 7
    sem_ant  = sum(pesos[7:14]) / len(pesos[7:14]) if len(pesos) >= 14 else pesos[-1]
    cambio   = sem_rec - sem_ant
    meta_kg  = sem_ant * abs(meta_pct)

    if direccion == "bajar":
        if cambio > -0.1:
            return {"accion": "reducir", "kcal": 200,
                    "razon": f"bajaste {abs(cambio):.2f}kg, meta era {meta_kg:.2f}kg"}
        elif cambio < -(meta_kg * 2):
            return {"accion": "subir", "kcal": 150,
                    "razon": f"bajaste {abs(cambio):.2f}kg — demasiado rápido, protege el músculo"}
        else:
            return {"accion": "mantener", "kcal": 0,
                    "razon": f"bajaste {abs(cambio):.2f}kg — en meta ✅"}
    else:
        if cambio < 0.05:
            return {"accion": "subir", "kcal": 150,
                    "razon": f"subiste {cambio:.2f}kg — necesitas más calorías"}
        elif cambio > meta_kg * 2:
            return {"accion": "reducir", "kcal": 100,
                    "razon": f"subiste {cambio:.2f}kg — lean bulk demasiado rápido"}
        else:
            return {"accion": "mantener", "kcal": 0,
                    "razon": f"subiste {cambio:.2f}kg — lean bulk perfecto ✅"}


def necesita_refeed(uid: int) -> bool:
    """3+ semanas consecutivas en déficit → refeed."""
    pesajes = get_pesajes_semana(uid, dias=35)
    if len(pesajes) < 21:
        return False

    pesos = [float(p["peso_kg"]) for p in pesajes if p.get("peso_kg")]
    semanas_deficit = 0
    for i in range(0, min(len(pesos)-7, 28), 7):
        bloque = pesos[i:i+7]
        siguiente = pesos[i+7:i+14]
        if not siguiente:
            break
        if sum(bloque)/len(bloque) < sum(siguiente)/len(siguiente) - 0.1:
            semanas_deficit += 1
        else:
            break

    return semanas_deficit >= 3


# ══════════════════════════════════════════════════════════════════════════════
# ANÁLISIS Y TOKENS
# ══════════════════════════════════════════════════════════════════════════════

def save_analisis(uid: int, tipo: str, texto: str, datos: dict = None) -> None:
    execute(
        "INSERT INTO analisis (user_id, tipo, texto, datos_json) VALUES (?,?,?,?)",
        (uid, tipo, texto, json.dumps(datos) if datos else None)
    )


def get_analisis_historial(uid: int, limit: int = 7) -> list[dict]:
    return fetchall("""
        SELECT tipo, texto, fecha FROM analisis WHERE user_id=?
        ORDER BY fecha DESC LIMIT ?
    """, (uid, limit))


def create_login_token(uid: int) -> str:
    import secrets
    token = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO login_tokens (token, user_id) VALUES (?,?)", (token, uid)
    )
    return token


def verify_login_token(token: str) -> int | None:
    row = fetchone(
        "SELECT user_id, usado, created_at FROM login_tokens WHERE token=?", (token,)
    )
    if not row or row["usado"]:
        return None
    from datetime import datetime, timedelta
    created = datetime.fromisoformat(row["created_at"])
    if datetime.utcnow() - created > timedelta(minutes=5):
        return None
    execute("UPDATE login_tokens SET usado=1 WHERE token=?", (token,))
    return row["user_id"]
