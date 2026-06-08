-- ============================================================
-- Coach AI — Database Schema v1.0
-- Diseñado para nunca necesitar ALTER TABLE parche
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── USUARIOS ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usuarios (
    user_id         INTEGER PRIMARY KEY,
    nombre          TEXT,
    created_at      TEXT DEFAULT (datetime('now')),

    -- Objetivo
    objetivo_vida   TEXT,           -- bajar_grasa | ganar_musculo | recomposicion | gluteo_pierna | salud | competitivo
    objetivo_gym    TEXT,           -- peso | mamado | general | gluteo (para planner)

    -- Perfil físico
    sexo            TEXT,           -- hombre | mujer
    edad            INTEGER,
    peso_kg         REAL,           -- actualizado por báscula, si no por onboarding
    altura_cm       REAL,
    bmr             INTEGER,        -- calculado: Mifflin-St Jeor
    tdee            INTEGER,        -- bmr × factor_actividad
    actividad_nivel TEXT DEFAULT 'sedentario',  -- sedentario | moderado | activo

    -- Entrenamiento
    nivel           TEXT DEFAULT 'intermedio',  -- principiante | intermedio | avanzado
    ambiente        TEXT DEFAULT 'gym',         -- gym | home | band
    dias_semana     INTEGER DEFAULT 4,
    limitaciones    TEXT DEFAULT 'ninguna',
    hora_reminder   TEXT,           -- HH:MM o NULL o PAUSA:DD/MM/YYYY

    -- Nutrición
    tipo_dieta      TEXT DEFAULT 'omnivoro',    -- omnivoro | saludable | vegano | proteina
    alergias        TEXT DEFAULT 'ninguna',     -- CSV: lacteos,gluten,huevo...
    cocina          TEXT DEFAULT 'variada',     -- CSV: mexicana,italiana...
    patron_comidas  TEXT DEFAULT '3',           -- 3 | 5 | ayuno | flexible
    ventana_comida  TEXT,           -- 7am | 9am | 12pm-8pm (ayuno)
    donde_come      TEXT DEFAULT 'casa',        -- casa | mixto | fuera
    suplementos     TEXT DEFAULT 'ninguno',
    alcohol         TEXT DEFAULT 'no',

    -- Integraciones
    google_fit_token    TEXT,       -- JSON con access+refresh token
    google_fit_email    TEXT,
    renpho_email        TEXT,
    renpho_password     TEXT,

    -- Estado interno
    ciclo_actual    INTEGER DEFAULT 1,  -- qué ciclo de 4 semanas va
    onboarding_done INTEGER DEFAULT 0,
    sueño_horas     REAL
);

-- ── ESTADO DEL PLAN ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS estado_plan (
    user_id         INTEGER PRIMARY KEY REFERENCES usuarios(user_id),
    semana          INTEGER DEFAULT 1,
    dia             TEXT DEFAULT 'lunes',
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ── RUTINAS (plan de gym generado) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rutinas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    ciclo           INTEGER NOT NULL DEFAULT 1,
    semana          INTEGER NOT NULL,           -- 1-4
    dia             TEXT NOT NULL,              -- lunes | martes...
    orden           INTEGER NOT NULL DEFAULT 0,
    ejercicio_id    TEXT NOT NULL,
    ejercicio       TEXT NOT NULL,
    grupo           TEXT NOT NULL,              -- empuje | tiron | pierna | gluteo | core | cardio
    patron          TEXT NOT NULL,              -- press_horizontal | sentadilla...
    rol             TEXT NOT NULL DEFAULT 'principal',  -- principal | accesorio | calentamiento | cardio
    series          INTEGER NOT NULL DEFAULT 3,
    reps            TEXT NOT NULL DEFAULT '8-10',       -- rango: "8-10" o "12-15"
    rir_objetivo    INTEGER DEFAULT 2,          -- RIR prescrito para esta semana
    notas           TEXT,                       -- cue técnico
    es_cardio       INTEGER DEFAULT 0,
    completado      INTEGER DEFAULT 0,
    swap_original   TEXT                        -- si fue cambiado, el ID original
);

CREATE INDEX IF NOT EXISTS idx_rutinas_user_semana ON rutinas(user_id, ciclo, semana, dia);

-- ── PESOS (historial de pesos levantados) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS pesos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    ejercicio_id    TEXT NOT NULL,
    ciclo           INTEGER NOT NULL DEFAULT 1,
    semana          INTEGER NOT NULL,
    dia             TEXT NOT NULL,
    peso_lbs        REAL NOT NULL,
    reps_completadas TEXT,          -- reps reales hechas (puede ser diferente al objetivo)
    series_completadas INTEGER,
    rir_real        INTEGER,        -- RIR reportado al terminar el set
    fecha           TEXT DEFAULT (date('now'))
);

CREATE INDEX IF NOT EXISTS idx_pesos_user_ej ON pesos(user_id, ejercicio_id, fecha DESC);

-- ── PROGRESIÓN (métricas por sesión) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sesiones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    ciclo           INTEGER NOT NULL DEFAULT 1,
    semana          INTEGER NOT NULL,
    dia             TEXT NOT NULL,
    grupo           TEXT,
    completada      INTEGER DEFAULT 0,
    fatiga_global   INTEGER DEFAULT 2,  -- 1-5
    rir_promedio    REAL,               -- promedio de RIR reportados
    sueño_horas     REAL,               -- horas de sueño esa noche
    duracion_min    INTEGER,            -- minutos de sesión
    notas_usuario   TEXT,
    fecha           TEXT DEFAULT (date('now'))
);

-- ── PESAJES CORPORALES (Renpho / báscula) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS pesajes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    fecha           TEXT NOT NULL,
    timestamp       INTEGER UNIQUE,
    peso_kg         REAL NOT NULL,
    grasa_pct       REAL,
    musculo_pct     REAL,
    musculo_kg      REAL,
    agua_pct        REAL,
    grasa_visceral  REAL,
    bmr_medido      INTEGER,
    bmi             REAL,
    edad_metabolica INTEGER,
    masa_osea       REAL,
    proteina_pct    REAL,
    fat_free_weight REAL
);

CREATE INDEX IF NOT EXISTS idx_pesajes_user_fecha ON pesajes(user_id, fecha DESC);

-- ── ACTIVIDAD DIARIA (Google Fit / Health Connect) ───────────────────────────
CREATE TABLE IF NOT EXISTS actividad_diaria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    fecha           TEXT NOT NULL,
    pasos           INTEGER DEFAULT 0,
    calorias_activas INTEGER DEFAULT 0,
    calorias_totales INTEGER DEFAULT 0,
    minutos_actividad INTEGER DEFAULT 0,
    distancia_km    REAL DEFAULT 0,
    hrv_promedio    REAL,           -- variabilidad cardíaca (recuperación)
    fc_reposo       INTEGER,        -- frecuencia cardíaca en reposo
    sueño_total_min INTEGER,        -- minutos totales de sueño
    sueño_profundo_min INTEGER,
    sueño_rem_min   INTEGER,
    sueño_ligero_min INTEGER,
    fuente          TEXT DEFAULT 'google_fit',
    UNIQUE(user_id, fecha)
);

-- ── PLAN NUTRICIONAL (generado por Gemini cada domingo) ──────────────────────
CREATE TABLE IF NOT EXISTS planes_nutricion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    semana_inicio   TEXT NOT NULL,  -- lunes de esa semana
    kcal_objetivo   INTEGER,
    proteina_g      INTEGER,
    carbs_g         INTEGER,
    grasas_g        INTEGER,
    kcal_mult       REAL DEFAULT 1.0,  -- multiplicador SISO
    estado_mimo     TEXT,           -- CUTTING_LIMPIO | RECOMPOSICION | CATABOLISMO | ESTANCAMIENTO
    es_refeed       INTEGER DEFAULT 0,
    plan_html       TEXT,           -- plan completo generado por Gemini
    ajuste_calorico INTEGER DEFAULT 0,  -- +/- kcal aplicado por SISO esta semana
    razon_ajuste    TEXT,
    generado_at     TEXT DEFAULT (datetime('now'))
);

-- ── MACROS DIARIOS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS macros_diarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    fecha           TEXT NOT NULL,
    tipo_dia        TEXT DEFAULT 'normal',  -- gym | descanso | refeed
    kcal            INTEGER,
    proteina_g      INTEGER,
    carbs_g         INTEGER,
    grasas_g        INTEGER,
    -- Distribución por comida (JSON)
    comida_1_json   TEXT,   -- desayuno
    comida_2_json   TEXT,   -- almuerzo
    comida_3_json   TEXT,   -- pre-workout o comida 3
    comida_4_json   TEXT,   -- post-workout o cena
    snack_json      TEXT,   -- caseína nocturna
    UNIQUE(user_id, fecha)
);

-- ── ANÁLISIS DE GEMINI ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analisis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    tipo            TEXT NOT NULL,  -- nocturno | corporal | semanal
    texto           TEXT NOT NULL,
    datos_json      TEXT,           -- snapshot de los datos usados
    fecha           TEXT DEFAULT (date('now'))
);

-- ── SWAPS DE EJERCICIOS ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS swaps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    ejercicio_orig  TEXT NOT NULL,
    ejercicio_nuevo TEXT NOT NULL,
    grupo           TEXT,
    motivo          TEXT,           -- preferencia | lesion | equipo
    fecha           TEXT DEFAULT (date('now'))
);

-- ── TOKENS DE LOGIN (web app) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS login_tokens (
    token           TEXT PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    usado           INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ── USUARIOS PERMITIDOS ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usuarios_permitidos (
    user_id         INTEGER PRIMARY KEY,
    added_at        TEXT DEFAULT (datetime('now'))
);
