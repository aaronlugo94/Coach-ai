"""
db/database.py — Invisible Coach v2.0
Incluye modelo Fitness-Fatiga de Bannister (1975).
Compatible con DB existente — migraciones seguras.
"""
from __future__ import annotations
import json, logging, math, os, secrets, sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger  = logging.getLogger(__name__)
DB_PATH = os.environ.get("DB_PATH", "/app/data/coach.db")

# ══════════════════════════════════════════════════════════════════════════════
# CONEXIÓN
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
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

def execute(sql: str, params: tuple = ()):
    with get_db() as conn:
        conn.execute(sql, params)

def fetchone(sql: str, params: tuple = ()) -> dict | None:
    with get_db() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def init_db():
    """Inicializa schema y corre migraciones seguras."""
    schema = Path(__file__).parent / "schema.sql"
    with get_db() as conn:
        conn.executescript(schema.read_text())
    _run_migrations()
    logger.info("DB lista: %s", DB_PATH)

def _run_migrations():
    """
    Agrega columnas nuevas a tablas existentes sin romper datos.
    SQLite no soporta IF NOT EXISTS en ALTER TABLE — usamos try/except.
    """
    nuevas_columnas = [
        ("usuarios", "fitness_score",   "REAL DEFAULT 0.0"),
        ("usuarios", "fatiga_score",    "REAL DEFAULT 0.0"),
        ("usuarios", "performance",     "REAL DEFAULT 0.0"),
        ("usuarios", "hrv_baseline",    "REAL"),
        ("usuarios", "rhr_baseline",    "REAL"),
        ("usuarios", "fatiga_snc",      "INTEGER DEFAULT 0"),
        ("usuarios", "semanas_deficit", "INTEGER DEFAULT 0"),
        ("sesiones", "carga_entreno",   "REAL DEFAULT 0.0"),
        ("actividad_diaria", "zona_fc_predominante", "INTEGER DEFAULT 1"),
        ("actividad_diaria", "rer_estimado",          "REAL"),
        # Sesión 3: onboarding discovery
        ("usuarios", "hora_gym",             "TEXT"),
        ("usuarios", "hora_checkin",         "TEXT"),
        ("usuarios", "duracion_sesion",      "INTEGER DEFAULT 60"),
        ("usuarios", "proteinas_favoritas",  "TEXT DEFAULT 'pollo,huevo,atun'"),
        ("usuarios", "nivel_estres",         "TEXT DEFAULT 'moderado'"),
        ("usuarios", "factor_estres",        "REAL DEFAULT 1.0"),
        ("usuarios", "wearable",             "TEXT DEFAULT 'ninguno'"),
        # Sesión 9: Renpho sync rate-limited
        ("usuarios", "renpho_last_sync",     "TEXT"),
        # Sesión 11: onboarding v2
        ("usuarios", "fecha_nac",            "TEXT"),
        ("usuarios", "electrodomesticos",    "TEXT"),
        ("usuarios", "recuperacion_activa",  "TEXT"),
        # Sesión 16 (Fase 2): onboarding v5
        ("usuarios", "cocina",               "TEXT"),
        ("usuarios", "n_comidas",            "INTEGER DEFAULT 3"),
        ("usuarios", "tiempos_comida",       "TEXT"),
        ("usuarios", "suplementos",          "TEXT"),
        ("usuarios", "alcohol",              "TEXT DEFAULT 'no'"),
        # Sesión 22: Google Fit ampliado — SpO2
        ("actividad_diaria", "spo2_pct",      "REAL"),
    ]
    with get_db() as conn:
        for tabla, col, tipo in nuevas_columnas:
            try:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
                logger.info("Migración: %s.%s añadida", tabla, col)
            except Exception:
                pass  # Columna ya existe — OK


# ══════════════════════════════════════════════════════════════════════════════
# USUARIOS
# ══════════════════════════════════════════════════════════════════════════════

def get_allowed_users() -> set[int]:
    return {r["user_id"] for r in fetchall("SELECT user_id FROM usuarios_permitidos", ())}

def add_allowed_user(uid: int):
    execute("INSERT OR IGNORE INTO usuarios_permitidos (user_id) VALUES (?)", (uid,))

def get_usuario(uid: int) -> dict | None:
    return fetchone("SELECT * FROM usuarios WHERE user_id=?", (uid,))

def upsert_usuario(uid: int, **kw):
    COLS = {
        "nombre","objetivo_vida","objetivo_gym","sexo","edad","peso_kg","altura_cm",
        "bmr","tdee","actividad_nivel","nivel","ambiente","dias_semana","limitaciones",
        "hora_reminder","tipo_dieta","alergias","cocina","patron_comidas","ventana_comida",
        "donde_come","suplementos","alcohol","google_fit_token","renpho_email",
        "renpho_password","ciclo_actual","onboarding_done","sueño_horas",
        "fitness_score","fatiga_score","performance","hrv_baseline","rhr_baseline",
        "fatiga_snc","semanas_deficit",
        "hora_gym","hora_checkin","duracion_sesion","proteinas_favoritas",
        "nivel_estres","factor_estres","wearable","renpho_last_sync",
        "fecha_nac","electrodomesticos","recuperacion_activa",
        "cocina","n_comidas","tiempos_comida","suplementos","alcohol",
    }
    kw = {k: v for k, v in kw.items() if k in COLS}
    if not kw: return
    cols = ", ".join(kw.keys())
    vals = ", ".join("?" * len(kw))
    sets = ", ".join(f"{k}=excluded.{k}" for k in kw)
    execute(
        f"INSERT INTO usuarios (user_id, {cols}) VALUES (?, {vals}) "
        f"ON CONFLICT(user_id) DO UPDATE SET {sets}",
        (uid, *kw.values()),
    )

def has_plan(uid: int) -> bool:
    u = fetchone("SELECT ciclo_actual FROM usuarios WHERE user_id=?", (uid,))
    ciclo = u["ciclo_actual"] if u else 1
    r = fetchone("SELECT COUNT(*) n FROM rutinas WHERE user_id=? AND ciclo=?", (uid, ciclo))
    return (r["n"] if r else 0) > 0


# ══════════════════════════════════════════════════════════════════════════════
# MODELO FITNESS-FATIGA (Bannister 1975)
# ══════════════════════════════════════════════════════════════════════════════

# Constantes del modelo
TAU_FITNESS = 42.0   # días — tiempo de decaimiento del fitness
TAU_FATIGA  = 7.0    # días — tiempo de decaimiento de la fatiga
K_FITNESS   = 1.0    # factor de ganancia fitness (calibrable)
K_FATIGA    = 2.0    # factor de ganancia fatiga (mayor impacto inmediato)

# HRV/RHR: umbrales para detectar fatiga SNC
HRV_UMBRAL  = 0.85   # si HRV < baseline × 0.85 → posible fatiga SNC
RHR_UMBRAL  = 1.10   # si RHR > baseline × 1.10 → posible fatiga SNC
DIAS_SNC    = 2      # días consecutivos bajo umbral → fatiga SNC confirmada


def calcular_carga_entreno(uid: int, semana: int, dia: str) -> float:
    """
    Calcula la carga de entrenamiento del día (w_t).
    w_t = series_totales × (10 - rir_promedio) / 10
    Escala 0-10: 0 = descanso, 10 = sesión al máximo esfuerzo.
    """
    ejs = get_ejercicios_dia(uid, semana, dia)
    if not ejs:
        return 0.0
    fuerza = [e for e in ejs if not e.get("es_cardio")]
    if not fuerza:
        return 0.5  # solo cardio = carga mínima

    series_total = sum(e.get("series", 3) for e in fuerza)
    rir_obj      = sum(e.get("rir_objetivo", 2) for e in fuerza) / len(fuerza)
    intensidad   = (10 - rir_obj) / 10  # RIR 0 = 100% intensidad, RIR 4 = 60%

    # Normalizar: 20 series a RIR 1 = carga 10
    carga = (series_total / 20) * intensidad * 10
    return round(min(carga, 10.0), 2)


def actualizar_bannister(uid: int, fecha_str: str = None):
    """
    Actualiza el modelo Fitness-Fatiga para el usuario.
    Llamar después de cada sesión completada.

    Bannister (1975):
      Fitness(t) = Fitness(t-1) × e^(-1/τ₁) + K₁ × w(t)
      Fatiga(t)  = Fatiga(t-1) × e^(-1/τ₂) + K₂ × w(t)
      Performance(t) = Fitness(t) - Fatiga(t)
    """
    if fecha_str is None:
        fecha_str = str(date.today())

    u = get_usuario(uid)
    if not u:
        return

    # Estado previo
    fitness_prev = float(u.get("fitness_score") or 0)
    fatiga_prev  = float(u.get("fatiga_score") or 0)

    # Carga del día
    semana, dia = get_estado(uid)
    carga = calcular_carga_entreno(uid, semana, dia)

    # Decaimiento exponencial + ganancia del día
    decay_f = math.exp(-1 / TAU_FITNESS)
    decay_g = math.exp(-1 / TAU_FATIGA)

    fitness_new = fitness_prev * decay_f + K_FITNESS * carga
    fatiga_new  = fatiga_prev  * decay_g + K_FATIGA  * carga
    perf_new    = fitness_new - fatiga_new

    # Datos biométricos del día para el registro
    activ = get_actividad_dia(uid, fecha_str)
    hrv   = activ.get("hrv_promedio")   if activ else None
    rhr   = activ.get("fc_reposo")      if activ else None
    sueño = activ.get("sueño_total_min",0) / 60 if activ else None

    # Detectar fatiga SNC
    fatiga_snc = _detectar_fatiga_snc(uid, hrv, rhr)

    # Guardar en bannister_diario
    execute("""
        INSERT INTO bannister_diario
        (user_id, fecha, carga, fitness, fatiga, performance,
         hrv, fc_reposo, sueño_horas, fatiga_snc)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id, fecha) DO UPDATE SET
        carga=excluded.carga, fitness=excluded.fitness,
        fatiga=excluded.fatiga, performance=excluded.performance,
        hrv=excluded.hrv, fc_reposo=excluded.fc_reposo,
        sueño_horas=excluded.sueño_horas, fatiga_snc=excluded.fatiga_snc
    """, (uid, fecha_str, carga, fitness_new, fatiga_new, perf_new,
          hrv, rhr, sueño, 1 if fatiga_snc else 0))

    # Actualizar resumen en usuarios
    upsert_usuario(uid,
        fitness_score=round(fitness_new, 3),
        fatiga_score=round(fatiga_new, 3),
        performance=round(perf_new, 3),
        fatiga_snc=1 if fatiga_snc else 0,
    )

    logger.info(
        "Bannister uid=%s: carga=%.1f fitness=%.2f fatiga=%.2f perf=%.2f snc=%s",
        uid, carga, fitness_new, fatiga_new, perf_new, fatiga_snc
    )
    return {
        "carga": carga,
        "fitness": round(fitness_new, 2),
        "fatiga": round(fatiga_new, 2),
        "performance": round(perf_new, 2),
        "fatiga_snc": fatiga_snc,
    }


def _detectar_fatiga_snc(uid: int, hrv_hoy: float, rhr_hoy: float) -> bool:
    """
    Detecta fatiga del SNC usando HRV y FC reposo.
    Condición: HRV < baseline×0.85 Y/O RHR > baseline×1.10
    durante DIAS_SNC días consecutivos.
    """
    u = get_usuario(uid)
    if not u:
        return False

    hrv_base = u.get("hrv_baseline")
    rhr_base = u.get("rhr_baseline")

    if not hrv_base and not rhr_base:
        return False  # Sin baseline todavía

    señales_hoy = 0
    if hrv_base and hrv_hoy and hrv_hoy < hrv_base * HRV_UMBRAL:
        señales_hoy += 1
    if rhr_base and rhr_hoy and rhr_hoy > rhr_base * RHR_UMBRAL:
        señales_hoy += 1

    if señales_hoy == 0:
        return False

    # Verificar días consecutivos
    dias_recientes = fetchall("""
        SELECT fatiga_snc FROM bannister_diario
        WHERE user_id=? ORDER BY fecha DESC LIMIT ?
    """, (uid, DIAS_SNC))

    consecutivos = sum(1 for d in dias_recientes if d.get("fatiga_snc") == 1)
    return consecutivos >= DIAS_SNC - 1  # hoy + DIAS_SNC-1 anteriores


def actualizar_baseline_hrv(uid: int):
    """
    Actualiza el baseline de HRV y RHR usando el promedio de 30 días.
    Llamar cada mañana después del sync de Google Fit.
    """
    rows = fetchall("""
        SELECT hrv_promedio, fc_reposo FROM actividad_diaria
        WHERE user_id=? AND hrv_promedio IS NOT NULL
        ORDER BY fecha DESC LIMIT 30
    """, (uid,))

    if len(rows) < 7:
        return  # Necesitamos al menos 7 días para un baseline confiable

    hrv_vals = [r["hrv_promedio"] for r in rows if r.get("hrv_promedio")]
    rhr_vals = [r["fc_reposo"]    for r in rows if r.get("fc_reposo")]

    kw = {}
    if hrv_vals:
        kw["hrv_baseline"] = round(sum(hrv_vals) / len(hrv_vals), 1)
    if rhr_vals:
        kw["rhr_baseline"] = round(sum(rhr_vals) / len(rhr_vals), 1)

    if kw:
        upsert_usuario(uid, **kw)
        logger.info("Baseline HRV uid=%s: %s", uid, kw)


def get_estado_bannister(uid: int) -> dict:
    """
    Retorna el estado actual del modelo para el usuario.
    Usado por Gemini en el análisis matutino.
    """
    u = get_usuario(uid)
    if not u:
        return {}

    fitness = float(u.get("fitness_score") or 0)
    fatiga  = float(u.get("fatiga_score")  or 0)
    perf    = float(u.get("performance")   or 0)

    # Porcentaje de recuperación del SNC (0-100%)
    if u.get("hrv_baseline") and u.get("hrv_baseline") > 0:
        ultimo_activ = get_actividad_dia(uid, str(date.today() - timedelta(days=1)))
        hrv_hoy = ultimo_activ.get("hrv_promedio") if ultimo_activ else None
        if hrv_hoy:
            snc_pct = min(100, round((hrv_hoy / u["hrv_baseline"]) * 100))
        else:
            snc_pct = 85  # default optimista sin datos
    else:
        snc_pct = 85

    # Recomendación de volumen basada en Performance
    if u.get("fatiga_snc"):
        rec_volumen = "deload"          # SNC fatigado → deload automático
    elif perf < -2:
        rec_volumen = "reducir"         # Alta fatiga acumulada
    elif perf > 3:
        rec_volumen = "mantener_max"    # Fitness alto, fatiga baja → explotar
    else:
        rec_volumen = "normal"

    return {
        "fitness":        round(fitness, 2),
        "fatiga":         round(fatiga, 2),
        "performance":    round(perf, 2),
        "snc_pct":        snc_pct,
        "fatiga_snc":     bool(u.get("fatiga_snc")),
        "hrv_baseline":   u.get("hrv_baseline"),
        "rec_volumen":    rec_volumen,
    }


def get_volumen_ajustado(uid: int, series_base: int) -> int:
    """
    Ajusta el volumen de entrenamiento según el estado Bannister.
    Usado por el planner para adaptar las series del día.
    """
    estado = get_estado_bannister(uid)
    rec = estado.get("rec_volumen", "normal")

    multiplicadores = {
        "deload":      0.60,   # Fatiga SNC → -40% volumen
        "reducir":     0.80,   # Performance negativa → -20%
        "normal":      1.00,   # Normal
        "mantener_max":1.00,   # No subir más allá del plan
    }
    mult = multiplicadores.get(rec, 1.0)
    return max(1, round(series_base * mult))


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO DEL PLAN
# ══════════════════════════════════════════════════════════════════════════════

def get_estado(uid: int) -> tuple[int, str]:
    r = fetchone("SELECT semana, dia FROM estado_plan WHERE user_id=?", (uid,))
    return (r["semana"], r["dia"]) if r else (1, "lunes")

def set_estado(uid: int, semana: int, dia: str):
    execute(
        "INSERT INTO estado_plan (user_id,semana,dia) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET semana=excluded.semana,"
        "dia=excluded.dia,updated_at=datetime('now')",
        (uid, semana, dia),
    )

def get_ciclo(uid: int) -> int:
    r = fetchone("SELECT ciclo_actual FROM usuarios WHERE user_id=?", (uid,))
    return r["ciclo_actual"] if r else 1

def avanzar_dia(uid: int, semana: int, dia: str) -> tuple[int, str]:
    ciclo = get_ciclo(uid)
    dias = [r["dia"] for r in fetchall(
        "SELECT DISTINCT dia FROM rutinas WHERE user_id=? AND ciclo=? AND semana=? ORDER BY orden",
        (uid, ciclo, semana)
    )]
    if not dias: return semana, dia
    try: idx = dias.index(dia)
    except ValueError: idx = -1

    if idx + 1 < len(dias):
        return semana, dias[idx + 1]

    nueva = semana + 1 if semana < 4 else 1
    if nueva == 1:
        execute("UPDATE usuarios SET ciclo_actual=ciclo_actual+1 WHERE user_id=?", (uid,))
        ciclo += 1
    nuevos = [r["dia"] for r in fetchall(
        "SELECT DISTINCT dia FROM rutinas WHERE user_id=? AND ciclo=? AND semana=? ORDER BY orden",
        (uid, ciclo, nueva)
    )]
    return nueva, (nuevos[0] if nuevos else "lunes")


# ══════════════════════════════════════════════════════════════════════════════
# RUTINAS
# ══════════════════════════════════════════════════════════════════════════════

def get_ejercicios_dia(uid: int, semana: int, dia: str) -> list[dict]:
    return fetchall(
        "SELECT * FROM rutinas WHERE user_id=? AND ciclo=? AND semana=? AND dia=? ORDER BY orden",
        (uid, get_ciclo(uid), semana, dia)
    )

def sustituir_ejercicio(uid: int, dia: str, ejercicio_id_viejo: str,
                        nuevo: dict, todas_las_semanas: bool = True) -> int:
    """
    Reemplaza un ejercicio por otro en la rutina activa. Por default
    aplica a TODAS las semanas del ciclo actual para ese día — así el
    usuario no tiene que repetir el cambio cada semana si no le gusta
    o no tiene el equipo disponible de forma permanente.
    `nuevo` = {"id","nombre","patron"} del catálogo (Ejercicio).
    Retorna el número de filas actualizadas.
    """
    ciclo = get_ciclo(uid)
    sql = (
        "UPDATE rutinas SET ejercicio_id=?, ejercicio=?, patron=? "
        "WHERE user_id=? AND ciclo=? AND dia=? AND ejercicio_id=?"
    )
    params = (nuevo["id"], nuevo["nombre"], nuevo["patron"], uid, ciclo, dia, ejercicio_id_viejo)
    if not todas_las_semanas:
        sql = sql.replace("AND dia=?", "AND dia=? AND semana=?")
        # No usado por ahora — todas_las_semanas=True es el caso por defecto
    with get_db() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount

def insert_plan(uid: int, semanas: list[dict]) -> int:
    ciclo = get_ciclo(uid)
    n = 0
    with get_db() as conn:
        conn.execute("DELETE FROM rutinas WHERE user_id=? AND ciclo=?", (uid, ciclo))
        for sem in semanas:
            for dia_d in sem["dias"]:
                for ej in dia_d["ejercicios"]:
                    conn.execute(
                        "INSERT INTO rutinas (user_id,ciclo,semana,dia,orden,ejercicio_id,"
                        "ejercicio,grupo,patron,rol,series,reps,rir_objetivo,notas,es_cardio) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (uid, ciclo, sem["semana"], dia_d["dia"], ej.get("orden",0),
                         ej["ejercicio_id"], ej["ejercicio"], dia_d.get("grupo",""),
                         ej.get("patron",""), ej.get("rol","principal"),
                         ej.get("series",3), ej.get("reps","8-10"),
                         ej.get("rir_objetivo",2), ej.get("notas",""),
                         1 if ej.get("es_cardio") else 0)
                    )
                    n += 1
    return n

def marcar_completado(uid: int, semana: int, dia: str):
    execute(
        "UPDATE rutinas SET completado=1 WHERE user_id=? AND ciclo=? AND semana=? AND dia=?",
        (uid, get_ciclo(uid), semana, dia)
    )


# ══════════════════════════════════════════════════════════════════════════════
# PESOS (doble progresión)
# ══════════════════════════════════════════════════════════════════════════════

COMPUESTOS = {
    "sentadilla","press_horizontal","press_inclinado","press_vertical",
    "bisagra_cadera","remo_horizontal","jalon_vertical","peso_muerto",
}

def save_peso(uid: int, ejercicio_id: str, semana: int, dia: str,
              peso_lbs: float, reps: str = None, series: int = None, rir: int = None):
    execute(
        "INSERT INTO pesos (user_id,ejercicio_id,ciclo,semana,dia,peso_lbs,"
        "reps_completadas,series_completadas,rir_real) VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, ejercicio_id, get_ciclo(uid), semana, dia, peso_lbs, reps, series, rir)
    )

def get_historial_peso(uid: int, ejercicio_id: str, limit: int = 4) -> list[dict]:
    return fetchall(
        "SELECT peso_lbs, reps_completadas, rir_real, fecha FROM pesos "
        "WHERE user_id=? AND ejercicio_id=? ORDER BY fecha DESC LIMIT ?",
        (uid, ejercicio_id, limit)
    )

def get_peso_sugerido(uid: int, ejercicio_id: str,
                      reps_obj: str = "8-10", patron: str = "") -> float | None:
    """
    Doble progresión (Schoenfeld 2021):
    Sube peso cuando el usuario llega al límite superior de reps
    en 2 sesiones consecutivas.
    """
    hist = get_historial_peso(uid, ejercicio_id, 4)
    if not hist:
        return None

    peso = float(hist[0]["peso_lbs"])
    inc  = 5.0 if patron in COMPUESTOS else 2.5

    try:
        rep_max = int(reps_obj.split("-")[-1].replace("+",""))
    except Exception:
        rep_max = 10

    # ¿Llegó al tope 2 veces seguidas?
    recientes = []
    for h in hist[:2]:
        r = h.get("reps_completadas","")
        try: recientes.append(int(str(r).split("-")[0]))
        except Exception: pass

    if len(recientes) >= 2 and all(r >= rep_max for r in recientes):
        return round(peso + inc, 1)

    return round(peso, 1)


# ══════════════════════════════════════════════════════════════════════════════
# SESIONES
# ══════════════════════════════════════════════════════════════════════════════

def save_sesion(uid: int, semana: int, dia: str, **kw):
    COLS = {"grupo","completada","fatiga_global","rir_promedio",
            "sueño_horas","duracion_min","carga_entreno"}
    kw = {k: v for k, v in kw.items() if k in COLS}
    cols = ", ".join(kw.keys())
    vals = ", ".join("?" * len(kw))
    execute(
        f"INSERT INTO sesiones (user_id,ciclo,semana,dia,{cols}) VALUES (?,?,?,?,{vals})",
        (uid, get_ciclo(uid), semana, dia, *kw.values())
    )


# ══════════════════════════════════════════════════════════════════════════════
# PESAJES (Renpho)
# ══════════════════════════════════════════════════════════════════════════════

def save_pesaje(uid: int, datos: dict) -> bool:
    ts = datos.get("Timestamp")
    if ts and fetchone("SELECT id FROM pesajes WHERE timestamp=?", (ts,)):
        return False
    execute(
        "INSERT INTO pesajes (user_id,fecha,timestamp,peso_kg,grasa_pct,musculo_pct,"
        "musculo_kg,agua_pct,grasa_visceral,bmr_medido,bmi,edad_metabolica,proteina_pct) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid, datos.get("Fecha"), ts, datos.get("Peso_kg"), datos.get("Grasa_Porcentaje"),
         datos.get("Musculo_Pct"), datos.get("Musculo_kg"), datos.get("Agua"),
         datos.get("VisFat"), datos.get("BMR"), datos.get("BMI"),
         datos.get("EdadMetabolica"), datos.get("Proteina"))
    )
    return True

def get_ultimo_pesaje(uid: int) -> dict | None:
    return fetchone(
        "SELECT * FROM pesajes WHERE user_id=? ORDER BY fecha DESC LIMIT 1", (uid,)
    )

def get_pesajes_recientes(uid: int, dias: int = 21) -> list[dict]:
    return fetchall(
        "SELECT fecha, peso_kg, grasa_pct, musculo_pct FROM pesajes "
        "WHERE user_id=? ORDER BY fecha DESC LIMIT ?", (uid, dias)
    )


# ══════════════════════════════════════════════════════════════════════════════
# ACTIVIDAD DIARIA (Google Fit)
# ══════════════════════════════════════════════════════════════════════════════

def save_actividad(uid: int, fecha: str, datos: dict):
    execute("""
        INSERT INTO actividad_diaria
        (user_id, fecha, pasos, calorias_activas, minutos_actividad, distancia_km,
         hrv_promedio, fc_reposo, sueño_total_min, sueño_profundo_min,
         sueño_rem_min, sueño_ligero_min, zona_fc_predominante, rer_estimado,
         spo2_pct, fuente)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id, fecha) DO UPDATE SET
        pasos=excluded.pasos, calorias_activas=excluded.calorias_activas,
        hrv_promedio=excluded.hrv_promedio, fc_reposo=excluded.fc_reposo,
        sueño_total_min=excluded.sueño_total_min,
        sueño_profundo_min=excluded.sueño_profundo_min,
        sueño_rem_min=excluded.sueño_rem_min,
        zona_fc_predominante=excluded.zona_fc_predominante,
        rer_estimado=excluded.rer_estimado,
        spo2_pct=excluded.spo2_pct
    """, (
        uid, fecha,
        datos.get("pasos", 0), datos.get("calorias_activas", 0),
        datos.get("minutos_actividad", 0), datos.get("distancia_km", 0),
        datos.get("hrv_promedio"), datos.get("fc_reposo"),
        datos.get("sueño_total_min"), datos.get("sueño_profundo_min"),
        datos.get("sueño_rem_min"), datos.get("sueño_ligero_min"),
        datos.get("zona_fc_predominante", 1), datos.get("rer_estimado"),
        datos.get("spo2_pct"),
        datos.get("fuente", "google_fit"),
    ))

def get_actividad_dia(uid: int, fecha: str = None) -> dict | None:
    if fecha is None:
        fecha = str(date.today() - timedelta(days=1))
    return fetchone(
        "SELECT * FROM actividad_diaria WHERE user_id=? AND fecha=?", (uid, fecha)
    )

def get_actividad_semana(uid: int, dias: int = 7) -> list[dict]:
    return fetchall(
        "SELECT * FROM actividad_diaria WHERE user_id=? ORDER BY fecha DESC LIMIT ?",
        (uid, dias)
    )


# ══════════════════════════════════════════════════════════════════════════════
# NUTRICIÓN (SISO + Refeed)
# ══════════════════════════════════════════════════════════════════════════════

def calcular_ajuste_calorico(uid: int) -> dict:
    """
    SISO: ajuste calórico basado en cambio de peso real vs meta.
    Meta bajar grasa: -0.5% del peso/semana
    Meta lean bulk:   +0.3% del peso/semana
    """
    u = get_usuario(uid)
    if not u:
        return {"accion": "mantener", "kcal": 0, "razon": "sin perfil"}

    obj = u.get("objetivo_gym", "general")
    metas = {
        "peso":    (-0.005, "bajar"),
        "mamado":  ( 0.003, "subir"),
        "gluteo":  (-0.003, "bajar"),
        "general": ( 0.0,   "mantener"),
    }
    meta_pct, dir_ = metas.get(obj, (0.0, "mantener"))

    if dir_ == "mantener":
        return {"accion": "mantener", "kcal": 0, "razon": "recomposición — calorías estables"}

    pesos = [float(p["peso_kg"]) for p in get_pesajes_recientes(uid, 21) if p.get("peso_kg")]
    if len(pesos) < 7:
        return {"accion": "mantener", "kcal": 0, "razon": f"faltan datos ({len(pesos)}/7 pesajes)"}

    sem_rec = sum(pesos[:7]) / 7
    sem_ant = sum(pesos[7:14]) / len(pesos[7:14]) if len(pesos) >= 14 else pesos[-1]
    cambio  = sem_rec - sem_ant
    meta_kg = sem_ant * abs(meta_pct)

    if dir_ == "bajar":
        if cambio > -0.1:
            return {"accion": "reducir", "kcal": 200,
                    "razon": f"bajaste {abs(cambio):.2f}kg, meta {meta_kg:.2f}kg/sem"}
        if cambio < -(meta_kg * 2):
            return {"accion": "subir", "kcal": 150,
                    "razon": f"bajaste {abs(cambio):.2f}kg — muy rápido, protege músculo"}
        return {"accion": "mantener", "kcal": 0,
                "razon": f"bajaste {abs(cambio):.2f}kg — en meta ✅"}
    else:
        if cambio < 0.05:
            return {"accion": "subir", "kcal": 150,
                    "razon": "necesitas más calorías para crecer"}
        if cambio > meta_kg * 2:
            return {"accion": "reducir", "kcal": 100,
                    "razon": "lean bulk muy rápido — reduce para evitar grasa"}
        return {"accion": "mantener", "kcal": 0,
                "razon": f"subiste {cambio:.2f}kg — lean bulk perfecto ✅"}


def necesita_refeed(uid: int) -> bool:
    """
    Refeed automático: 3+ semanas consecutivas en déficit.
    Dirlewanger (2000): restaura leptina y mejora adherencia.
    """
    pesos = [float(p["peso_kg"]) for p in get_pesajes_recientes(uid, 35) if p.get("peso_kg")]
    if len(pesos) < 21:
        return False
    semanas = 0
    for i in range(0, 21, 7):
        b1 = pesos[i:i+7]
        b2 = pesos[i+7:i+14]
        if not b2: break
        if sum(b1)/len(b1) < sum(b2)/len(b2) - 0.1:
            semanas += 1
        else:
            break
    return semanas >= 3


def get_plan_nutricion_activo(uid: int) -> dict | None:
    return fetchone(
        "SELECT * FROM planes_nutricion WHERE user_id=? ORDER BY generado_at DESC LIMIT 1",
        (uid,)
    )

def save_plan_nutricion(uid: int, plan_json: dict, macros: dict):
    """Guarda el plan de nutrición semanal generado por Gemini."""
    import json as _json
    execute("""
        INSERT INTO planes_nutricion
        (user_id, semana_inicio, kcal_objetivo, proteina_g, carbs_g, grasas_g,
         es_refeed, plan_json, ajuste_kcal, razon_ajuste)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        uid, str(date.today()),
        macros.get("kcal"), macros.get("proteina_g"),
        macros.get("carbs_g"), macros.get("grasas_g"),
        1 if macros.get("es_refeed") else 0,
        _json.dumps(plan_json, ensure_ascii=False),
        macros.get("ajuste_siso",{}).get("kcal",0),
        macros.get("ajuste_siso",{}).get("razon",""),
    ))


# ══════════════════════════════════════════════════════════════════════════════
# ANÁLISIS Y TOKENS
# ══════════════════════════════════════════════════════════════════════════════

def save_analisis(uid: int, tipo: str, texto: str):
    execute(
        "INSERT INTO analisis (user_id, tipo, texto) VALUES (?,?,?)", (uid, tipo, texto)
    )

def get_analisis_historial(uid: int, limit: int = 7) -> list[dict]:
    return fetchall(
        "SELECT tipo, texto, fecha FROM analisis WHERE user_id=? ORDER BY fecha DESC LIMIT ?",
        (uid, limit)
    )

def create_login_token(uid: int) -> str:
    token = secrets.token_urlsafe(32)
    execute("INSERT INTO login_tokens (token, user_id) VALUES (?,?)", (token, uid))
    return token

def verify_login_token(token: str) -> int | None:
    r = fetchone(
        "SELECT user_id, usado, created_at FROM login_tokens WHERE token=?", (token,)
    )
    if not r or r["usado"]:
        return None
    created = datetime.fromisoformat(r["created_at"])
    if datetime.utcnow() - created > timedelta(minutes=10):
        return None
    execute("UPDATE login_tokens SET usado=1 WHERE token=?", (token,))
    return r["user_id"]
