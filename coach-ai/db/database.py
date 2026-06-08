from __future__ import annotations
import json, logging, os, sqlite3, secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DB_PATH = os.environ.get("DB_PATH", "/app/data/coach.db")

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

def init_db():
    schema = Path(__file__).parent / "schema.sql"
    with get_db() as conn:
        conn.executescript(schema.read_text())
    logger.info("DB lista: %s", DB_PATH)

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

# ── USUARIOS ──────────────────────────────────────────────────────────────────

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

# ── ESTADO ────────────────────────────────────────────────────────────────────

def get_estado(uid: int) -> tuple[int, str]:
    r = fetchone("SELECT semana, dia FROM estado_plan WHERE user_id=?", (uid,))
    return (r["semana"], r["dia"]) if r else (1, "lunes")

def set_estado(uid: int, semana: int, dia: str):
    execute(
        "INSERT INTO estado_plan (user_id,semana,dia) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET semana=excluded.semana,dia=excluded.dia,updated_at=datetime('now')",
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

# ── RUTINAS ───────────────────────────────────────────────────────────────────

def get_ejercicios_dia(uid: int, semana: int, dia: str) -> list[dict]:
    return fetchall(
        "SELECT * FROM rutinas WHERE user_id=? AND ciclo=? AND semana=? AND dia=? ORDER BY orden",
        (uid, get_ciclo(uid), semana, dia)
    )

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

# ── PESOS ─────────────────────────────────────────────────────────────────────

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
    hist = get_historial_peso(uid, ejercicio_id, 4)
    if not hist: return None
    peso = float(hist[0]["peso_lbs"])
    COMPUESTOS = {"sentadilla","press_horizontal","press_inclinado","press_vertical",
                  "bisagra_cadera","remo_horizontal","jalon_vertical","peso_muerto"}
    inc = 5.0 if patron in COMPUESTOS else 2.5
    try:
        rep_max = int(reps_obj.split("-")[-1].replace("+",""))
    except Exception:
        rep_max = 10
    recientes = []
    for h in hist[:2]:
        r = h.get("reps_completadas","")
        try: recientes.append(int(str(r).split("-")[0]))
        except Exception: pass
    if len(recientes) >= 2 and all(r >= rep_max for r in recientes):
        return round(peso + inc, 1)
    return round(peso, 1)

# ── SESIONES ──────────────────────────────────────────────────────────────────

def save_sesion(uid: int, semana: int, dia: str, **kw):
    COLS = {"grupo","completada","fatiga_global","rir_promedio","sueño_horas","duracion_min"}
    kw = {k: v for k, v in kw.items() if k in COLS}
    cols = ", ".join(kw.keys())
    vals = ", ".join("?" * len(kw))
    execute(
        f"INSERT INTO sesiones (user_id,ciclo,semana,dia,{cols}) VALUES (?,?,?,?,{vals})",
        (uid, get_ciclo(uid), semana, dia, *kw.values())
    )

# ── PESAJES ───────────────────────────────────────────────────────────────────

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
    return fetchone("SELECT * FROM pesajes WHERE user_id=? ORDER BY fecha DESC LIMIT 1", (uid,))

def get_pesajes_recientes(uid: int, dias: int = 21) -> list[dict]:
    return fetchall(
        "SELECT fecha, peso_kg, grasa_pct, musculo_pct FROM pesajes "
        "WHERE user_id=? ORDER BY fecha DESC LIMIT ?", (uid, dias)
    )

# ── ACTIVIDAD (Google Fit) ────────────────────────────────────────────────────

def save_actividad(uid: int, fecha: str, datos: dict):
    execute(
        "INSERT INTO actividad_diaria (user_id,fecha,pasos,calorias_activas,"
        "minutos_actividad,distancia_km,hrv_promedio,fc_reposo,sueño_total_min,"
        "sueño_profundo_min,sueño_rem_min,sueño_ligero_min,fuente) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,fecha) DO UPDATE SET "
        "pasos=excluded.pasos, calorias_activas=excluded.calorias_activas,"
        "hrv_promedio=excluded.hrv_promedio, sueño_total_min=excluded.sueño_total_min,"
        "sueño_profundo_min=excluded.sueño_profundo_min, sueño_rem_min=excluded.sueño_rem_min",
        (uid, fecha, datos.get("pasos",0), datos.get("calorias_activas",0),
         datos.get("minutos_actividad",0), datos.get("distancia_km",0),
         datos.get("hrv_promedio"), datos.get("fc_reposo"),
         datos.get("sueño_total_min"), datos.get("sueño_profundo_min"),
         datos.get("sueño_rem_min"), datos.get("sueño_ligero_min"),
         datos.get("fuente","google_fit"))
    )

def get_actividad_semana(uid: int, dias: int = 7) -> list[dict]:
    return fetchall(
        "SELECT * FROM actividad_diaria WHERE user_id=? ORDER BY fecha DESC LIMIT ?",
        (uid, dias)
    )

# ── NUTRICIÓN ─────────────────────────────────────────────────────────────────

def calcular_ajuste_calorico(uid: int) -> dict:
    u = get_usuario(uid)
    if not u: return {"accion":"mantener","kcal":0,"razon":"sin perfil"}
    obj = u.get("objetivo_gym","general")
    metas = {"peso":(-0.006,"bajar"),"mamado":(0.003,"subir"),
             "gluteo":(-0.003,"bajar"),"general":(0.0,"mantener")}
    meta_pct, dir_ = metas.get(obj,(0.0,"mantener"))
    if dir_ == "mantener":
        return {"accion":"mantener","kcal":0,"razon":"recomposición — calorías estables"}
    pesos = [float(p["peso_kg"]) for p in get_pesajes_recientes(uid,21) if p.get("peso_kg")]
    if len(pesos) < 7:
        return {"accion":"mantener","kcal":0,"razon":f"necesito más datos ({len(pesos)}/7 pesajes)"}
    sem_rec = sum(pesos[:7])/7
    sem_ant = sum(pesos[7:14])/len(pesos[7:14]) if len(pesos)>=14 else pesos[-1]
    cambio = sem_rec - sem_ant
    meta_kg = sem_ant * abs(meta_pct)
    if dir_ == "bajar":
        if cambio > -0.1: return {"accion":"reducir","kcal":200,"razon":f"bajaste {abs(cambio):.2f}kg, meta {meta_kg:.2f}kg"}
        if cambio < -(meta_kg*2): return {"accion":"subir","kcal":150,"razon":f"bajaste {abs(cambio):.2f}kg — muy rápido"}
        return {"accion":"mantener","kcal":0,"razon":f"bajaste {abs(cambio):.2f}kg ✅"}
    else:
        if cambio < 0.05: return {"accion":"subir","kcal":150,"razon":"necesitas más calorías para crecer"}
        if cambio > meta_kg*2: return {"accion":"reducir","kcal":100,"razon":"lean bulk muy rápido"}
        return {"accion":"mantener","kcal":0,"razon":f"subiste {cambio:.2f}kg ✅"}

def necesita_refeed(uid: int) -> bool:
    pesos = [float(p["peso_kg"]) for p in get_pesajes_recientes(uid,35) if p.get("peso_kg")]
    if len(pesos) < 21: return False
    semanas = 0
    for i in range(0, 21, 7):
        b1 = pesos[i:i+7]; b2 = pesos[i+7:i+14]
        if not b2: break
        if sum(b1)/len(b1) < sum(b2)/len(b2) - 0.1: semanas += 1
        else: break
    return semanas >= 3

# ── ANÁLISIS Y TOKENS ─────────────────────────────────────────────────────────

def save_analisis(uid: int, tipo: str, texto: str):
    execute("INSERT INTO analisis (user_id,tipo,texto) VALUES (?,?,?)", (uid,tipo,texto))

def create_login_token(uid: int) -> str:
    token = secrets.token_urlsafe(32)
    execute("INSERT INTO login_tokens (token,user_id) VALUES (?,?)", (token,uid))
    return token

def verify_login_token(token: str) -> int | None:
    r = fetchone("SELECT user_id,usado,created_at FROM login_tokens WHERE token=?", (token,))
    if not r or r["usado"]: return None
    created = datetime.fromisoformat(r["created_at"])
    if datetime.utcnow() - created > timedelta(minutes=5): return None
    execute("UPDATE login_tokens SET usado=1 WHERE token=?", (token,))
    return r["user_id"]
