PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

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
    sueño_horas      REAL
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
