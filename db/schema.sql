-- ============================================================
-- Invisible Coach — DB Schema v2.0
-- Compatible con v1: solo agrega tablas y columnas nuevas
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── TABLAS BASE (sin cambios) ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS usuarios_permitidos (
    user_id   INTEGER PRIMARY KEY,
    added_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS usuarios (
    user_id          INTEGER PRIMARY KEY,
    nombre           TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    objetivo_vida    TEXT,
    objetivo_gym     TEXT,
    sexo             TEXT,
    edad             INTEGER,
    peso_kg          REAL,
    altura_cm        REAL,
    bmr              INTEGER,
    tdee             INTEGER,
    actividad_nivel  TEXT DEFAULT 'sedentario',
    nivel            TEXT DEFAULT 'intermedio',
    ambiente         TEXT DEFAULT 'gym',
    dias_semana      INTEGER DEFAULT 4,
    limitaciones     TEXT DEFAULT 'ninguna',
    hora_reminder    TEXT,
    tipo_dieta       TEXT DEFAULT 'omnivoro',
    alergias         TEXT DEFAULT 'ninguna',
    cocina           TEXT DEFAULT 'variada',
    patron_comidas   TEXT DEFAULT '3',
    ventana_comida   TEXT,
    donde_come       TEXT DEFAULT 'casa',
    suplementos      TEXT DEFAULT 'ninguno',
    alcohol          TEXT DEFAULT 'no',
    google_fit_token TEXT,
    renpho_email     TEXT,
    renpho_password  TEXT,
    ciclo_actual     INTEGER DEFAULT 1,
    onboarding_done  INTEGER DEFAULT 0,
    sueño_horas      REAL,
    -- Nuevas en v2: modelo Bannister
    fitness_score    REAL DEFAULT 0.0,   -- Fitness acumulado (τ=42 días)
    fatiga_score     REAL DEFAULT 0.0,   -- Fatiga acumulada (τ=7 días)
    performance      REAL DEFAULT 0.0,   -- Performance = Fitness - Fatiga
    hrv_baseline     REAL,               -- HRV promedio 30 días (baseline)
    rhr_baseline     REAL,               -- FC reposo promedio 30 días
    fatiga_snc       INTEGER DEFAULT 0,  -- 1 si fatiga SNC detectada
    semanas_deficit  INTEGER DEFAULT 0   -- Semanas consecutivas en déficit calórico
);

CREATE TABLE IF NOT EXISTS estado_plan (
    user_id    INTEGER PRIMARY KEY REFERENCES usuarios(user_id),
    semana     INTEGER DEFAULT 1,
    dia        TEXT DEFAULT 'lunes',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rutinas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES usuarios(user_id),
    ciclo        INTEGER NOT NULL DEFAULT 1,
    semana       INTEGER NOT NULL,
    dia          TEXT NOT NULL,
    orden        INTEGER NOT NULL DEFAULT 0,
    ejercicio_id TEXT NOT NULL,
    ejercicio    TEXT NOT NULL,
    grupo        TEXT NOT NULL,
    patron       TEXT NOT NULL DEFAULT '',
    rol          TEXT NOT NULL DEFAULT 'principal',
    series       INTEGER NOT NULL DEFAULT 3,
    reps         TEXT NOT NULL DEFAULT '8-10',
    rir_objetivo INTEGER DEFAULT 2,
    notas        TEXT DEFAULT '',
    es_cardio    INTEGER DEFAULT 0,
    completado   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rutinas ON rutinas(user_id, ciclo, semana, dia);

CREATE TABLE IF NOT EXISTS pesos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES usuarios(user_id),
    ejercicio_id        TEXT NOT NULL,
    ciclo               INTEGER NOT NULL DEFAULT 1,
    semana              INTEGER NOT NULL,
    dia                 TEXT NOT NULL,
    peso_lbs            REAL NOT NULL,
    reps_completadas    TEXT,
    series_completadas  INTEGER,
    rir_real            INTEGER,
    fecha               TEXT DEFAULT (date('now'))
);
CREATE INDEX IF NOT EXISTS idx_pesos ON pesos(user_id, ejercicio_id, fecha DESC);

CREATE TABLE IF NOT EXISTS sesiones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES usuarios(user_id),
    ciclo         INTEGER NOT NULL DEFAULT 1,
    semana        INTEGER NOT NULL,
    dia           TEXT NOT NULL,
    grupo         TEXT,
    completada    INTEGER DEFAULT 0,
    fatiga_global INTEGER DEFAULT 2,
    rir_promedio  REAL,
    sueño_horas   REAL,
    duracion_min  INTEGER,
    -- Nueva en v2: carga de entrenamiento para Bannister
    carga_entreno REAL DEFAULT 0.0,  -- volumen × intensidad del día
    fecha         TEXT DEFAULT (date('now'))
);

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
    proteina_pct    REAL
);
CREATE INDEX IF NOT EXISTS idx_pesajes ON pesajes(user_id, fecha DESC);

CREATE TABLE IF NOT EXISTS actividad_diaria (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES usuarios(user_id),
    fecha               TEXT NOT NULL,
    pasos               INTEGER DEFAULT 0,
    calorias_activas    INTEGER DEFAULT 0,
    minutos_actividad   INTEGER DEFAULT 0,
    distancia_km        REAL DEFAULT 0,
    hrv_promedio        REAL,
    fc_reposo           INTEGER,
    sueño_total_min     INTEGER,
    sueño_profundo_min  INTEGER,
    sueño_rem_min       INTEGER,
    sueño_ligero_min    INTEGER,
    fuente              TEXT DEFAULT 'google_fit',
    -- Nueva en v2: zona cardíaca predominante del día
    zona_fc_predominante INTEGER DEFAULT 1,  -- 1-5 según % FCmáx
    rer_estimado         REAL,               -- Cociente respiratorio estimado
    UNIQUE(user_id, fecha)
);

CREATE TABLE IF NOT EXISTS planes_nutricion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES usuarios(user_id),
    semana_inicio   TEXT NOT NULL,
    kcal_objetivo   INTEGER,
    proteina_g      INTEGER,
    carbs_g         INTEGER,
    grasas_g        INTEGER,
    kcal_mult       REAL DEFAULT 1.0,
    es_refeed       INTEGER DEFAULT 0,
    plan_json       TEXT,
    ajuste_kcal     INTEGER DEFAULT 0,
    razon_ajuste    TEXT,
    generado_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analisis (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES usuarios(user_id),
    tipo     TEXT NOT NULL,
    texto    TEXT NOT NULL,
    fecha    TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS login_tokens (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES usuarios(user_id),
    usado      INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- ── TABLA NUEVA v2: Estado Bannister diario ───────────────────────────────────
-- Historial del modelo Fitness-Fatiga por día
-- Bannister (1975), validado Calvert (2003)
CREATE TABLE IF NOT EXISTS bannister_diario (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES usuarios(user_id),
    fecha       TEXT NOT NULL,
    -- Carga del día (w_t): volumen × intensidad relativa
    carga       REAL DEFAULT 0.0,
    -- Fitness acumulado: F(t) = F(t-1)·e^(-1/42) + w(t)
    fitness     REAL DEFAULT 0.0,
    -- Fatiga acumulada: G(t) = G(t-1)·e^(-1/7) + w(t)
    fatiga      REAL DEFAULT 0.0,
    -- Performance: P(t) = Fitness - Fatiga
    performance REAL DEFAULT 0.0,
    -- Datos del día para el cálculo
    hrv         REAL,
    fc_reposo   REAL,
    sueño_horas REAL,
    -- Flags de estado
    fatiga_snc  INTEGER DEFAULT 0,   -- 1 si HRV < baseline×0.85
    deload_auto INTEGER DEFAULT 0,   -- 1 si se aplicó deload automático
    UNIQUE(user_id, fecha)
);
CREATE INDEX IF NOT EXISTS idx_bannister ON bannister_diario(user_id, fecha DESC);

-- ── MIGRACIONES SEGURAS (ALTER TABLE) ────────────────────────────────────────
-- Se ejecutan con IF NOT EXISTS implícito via try/except en Python
-- Columnas nuevas en usuarios (para DB existentes en Railway)
-- Ver: database.py → _run_migrations()
