"""
ai/prompts.py — Invisible Coach v3.0

Todos los prompts de Gemini centralizados.
Principio: datos reales + acción concreta. Nunca frases genéricas de motivación.
"""
from __future__ import annotations


def prompt_briefing_matutino(datos: dict) -> str:
    """
    07:00 AM — El Briefing Matutino.
    Máximo 5 líneas. Accionable en 10 segundos.
    """
    u       = datos.get("usuario", {})
    bann    = datos.get("bannister", {})
    macros  = datos.get("macros", {})
    hoy     = datos.get("hoy", {})

    nombre  = (u.get("nombre") or "").split()[0] or "campeón"
    semana  = hoy.get("semana", 1)
    label   = hoy.get("label", "")
    grupo   = hoy.get("grupo", "").upper()
    ejs     = hoy.get("ejercicios", [])
    snc_pct = bann.get("snc_pct", 85)
    rec_vol = bann.get("rec_volumen", "normal")
    es_gym  = bool(ejs)

    nombre_ejs = "\n".join([
        f"  {e['ejercicio'][:28]}  {e['series']}×{e['reps']} · RIR {e['rir_objetivo']}"
        + (f" · {e['peso_sugerido']} lbs" if e.get("peso_sugerido") else "")
        + (" ↑+5" if e.get("es_nuevo_peso") else "")
        for e in ejs[:4] if not e.get("es_cardio")
    ])

    kcal   = macros.get("kcal", 0)
    prot   = macros.get("proteina_g", 0)
    carbs  = macros.get("carbs_g", 0)
    toma   = macros.get("toma_proteina", 0)

    return f"""Eres el coach personal de {nombre}. Genera el briefing matutino.

DATOS REALES DE HOY:
SNC: {snc_pct}% de recuperación
Estado: {rec_vol} {'⚠️ DELOAD ACTIVO' if rec_vol == 'deload' else ''}
Semana {semana}/4 — {label}
{'GYM HOY: ' + grupo if es_gym else 'DÍA DE DESCANSO ACTIVO'}
{nombre_ejs if es_gym else ''}

MACROS HOY ({('día de gym' if es_gym else 'descanso')}):
{kcal} kcal · {prot}g proteína ({toma}g × 4 tomas) · {carbs}g carbos
{'Refeed esta semana — comes a mantenimiento' if macros.get('es_refeed') else ''}

INSTRUCCIONES ESTRICTAS:
1. Línea 1: Estado del SNC con el porcentaje REAL y qué significa para hoy
2. Línea 2: Si es día de gym → ejercicio principal con el peso exacto sugerido y RIR
   Si es descanso → actividad específica de recuperación activa (pasos meta o movilidad)
3. Línea 3: UNA instrucción de nutrición concreta para hoy (timing, cantidad exacta)
4. Si rec_volumen=deload: NUNCA sugerir subir peso, explicar supercompensación en 1 frase
5. Si SNC < 70%: priorizar sueño y proteína sobre entrenamiento
6. Máximo 4 líneas en total. Sin emojis excesivos. Sin frases motivacionales vacías.
7. Tono: coach directo y científico, no motivador de Instagram.
Solo en español."""


def prompt_checkin_nocturno(datos: dict) -> str:
    """
    09:00 PM — Análisis después del check-in de 2 taps.
    El usuario ya marcó: [rutina: sí/no] [dieta: sí/no]
    """
    u       = datos.get("usuario", {})
    bann    = datos.get("bannister", {})
    sesion  = datos.get("sesion", {})
    macros  = datos.get("macros", {})
    activ   = datos.get("actividad", {})
    pesos   = datos.get("pesos_usados", [])

    nombre       = (u.get("nombre") or "").split()[0] or "tú"
    rutina_ok    = sesion.get("completada", False)
    dieta_ok     = datos.get("dieta_ok", False)
    fatiga       = sesion.get("fatiga_global", 2)
    sueño        = sesion.get("sueño_horas") or u.get("sueño_horas") or "?"
    hrv          = activ.get("hrv_promedio")
    fc_reposo    = activ.get("fc_reposo")
    pasos        = activ.get("pasos", 0)
    hrv_base     = u.get("hrv_baseline")
    snc_pct      = bann.get("snc_pct", 85)

    pesos_str = "\n".join([
        f"  {p['ejercicio']}: {p['peso_lbs']} lbs × {p['reps']}"
        for p in pesos[:3]
    ]) if pesos else "  Sin datos de pesos"

    progresiones = [p for p in pesos if p.get("es_nuevo_peso")]
    prog_str = ", ".join([f"{p['ejercicio']} +5lbs" for p in progresiones]) or "ninguna"

    hrv_str = f"{hrv:.0f} ms" if hrv else "sin datos"
    hrv_vs  = f" ({round(hrv/hrv_base*100)}% del baseline)" if hrv and hrv_base else ""
    manana  = datos.get("manana", {})
    grupo_man = manana.get("grupo","").upper() if manana else ""

    return f"""Eres el coach de {nombre}. Analiza su día y genera el resumen nocturno.

DATOS REALES DE HOY:
Rutina: {'✅ Completada' if rutina_ok else '❌ No completada'}
Dieta: {'✅ Cumplida' if dieta_ok else '❌ Con variación'}
Fatiga reportada: {fatiga}/5
Sueño anoche: {sueño}h
Pasos: {pasos:,}

BIOMETRÍA (Google Fit / OnePlus Watch):
HRV: {hrv_str}{hrv_vs}
FC reposo: {fc_reposo} bpm
SNC: {snc_pct}%

PESOS USADOS HOY:
{pesos_str}
Progresiones (doble progresión activada): {prog_str}

MAÑANA: {grupo_man if grupo_man else 'Descanso activo'}

INSTRUCCIONES ESTRICTAS:
1. Línea 1: Lo más relevante del día con UN número real (peso levantado, HRV, pasos, etc.)
2. Línea 2: Si hubo progresión de peso → mencionarla con el número exacto
   Si no hubo rutina → decir por qué importa mañana (no regañar)
   Si fatiga ≥ 4 → priorizar sueño esta noche con hora exacta
3. Línea 3: UNA acción para mañana — puede ser gym, nutrición o recuperación
4. Si HRV < baseline × 0.85: mencionar recuperación SNC y ajuste de mañana
5. Máximo 3 líneas. Sin emojis excesivos. Directo y con datos.
Solo en español."""


def prompt_notificacion_enganche(tipo: str, datos: dict) -> str:
    """
    Notificaciones de enganche que usa Gemini para generar copy personalizado.
    Tipos: sin_entrenar | progresion_semanal | hrv_bajo | meta_cercana | racha
    """
    u      = datos.get("usuario", {})
    nombre = (u.get("nombre") or "").split()[0] or "tú"

    if tipo == "sin_entrenar":
        dias   = datos.get("dias_sin_gym", 3)
        ej     = datos.get("ejercicio_proximo", "jalón al pecho")
        peso   = datos.get("peso_sugerido", 0)
        return f"""Genera UN mensaje de reenganche para {nombre} que lleva {dias} días sin entrenar.

CONTEXTO:
Próxima sesión: {ej} con {peso} lbs sugeridos
Días sin gym: {dias}

REGLAS:
- Menciona el ejercicio Y el peso exacto que le espera
- Crea urgencia con datos, no con culpa
- Máximo 2 líneas
- NO usar frases genéricas ("¡Tú puedes!", "¡No te rindas!")
- SÍ usar datos reales del entrenamiento
Solo en español."""

    elif tipo == "progresion_semanal":
        semana     = datos.get("semana", 2)
        ejercicios = datos.get("progresiones", [])
        prog_str   = "\n".join([f"  {e['ej']}: +{e['cambio']} lbs" for e in ejercicios[:3]])
        return f"""Genera el resumen de progresión semanal para {nombre}.

PROGRESIONES REALES semana {semana}:
{prog_str}

REGLAS:
- Menciona los números exactos
- Proyecta cuándo llegará a su meta si sigue esta tasa
- Máximo 2 líneas
- Tono de análisis, no de celebración excesiva
Solo en español."""

    elif tipo == "hrv_bajo":
        hrv      = datos.get("hrv", 45)
        hrv_base = datos.get("hrv_baseline", 60)
        pct      = round(hrv / hrv_base * 100)
        return f"""Genera un aviso de recuperación para {nombre}.

HRV actual: {hrv} ms ({pct}% del baseline de {hrv_base} ms)

REGLAS:
- Explicar en términos simples qué significa (sin jerga técnica)
- Decir UNA acción concreta (caminar, dormir X horas, más proteína)
- Máximo 2 líneas
Solo en español."""

    elif tipo == "racha":
        dias  = datos.get("racha", 7)
        logro = datos.get("logro_reciente", "")
        return f"""Genera felicitación por racha de {dias} días para {nombre}.

Logro reciente: {logro}

REGLAS:
- Mencionar la racha con el número exacto
- Conectarlo con el progreso físico real si hay datos
- Máximo 2 líneas. No excesivamente emotivo.
Solo en español."""

    return f"Genera un mensaje motivacional con datos reales para {nombre}. Máximo 2 líneas. Solo español."


def prompt_resumen_semanal(datos: dict) -> str:
    """
    Domingo — Resumen semanal con predicción de meta.
    Usado para el reporte y como gancho de retención.
    """
    u         = datos.get("usuario", {})
    nombre    = (u.get("nombre") or "").split()[0] or "tú"
    semana    = datos.get("semana", 1)
    sesiones  = datos.get("sesiones_completadas", 0)
    total_s   = datos.get("sesiones_total", 4)
    cambio_p  = datos.get("cambio_peso_kg", 0)
    cambio_g  = datos.get("cambio_grasa_pct")
    progresiones = datos.get("progresiones_fuerza", [])
    meta_grasa= float(u.get("meta_grasa_pct") or 22)
    grasa_act = datos.get("grasa_pct_actual")
    racha     = datos.get("racha", 0)

    prog_str = "\n".join([
        f"  {p['ejercicio'][:25]}: {p['peso_inicio']} → {p['peso_actual']} lbs (+{p['cambio']})"
        for p in progresiones[:3]
    ]) if progresiones else "  Sin progresiones registradas esta semana"

    semanas_restantes = ""
    if grasa_act and cambio_g and cambio_g < 0:
        tasa = abs(cambio_g)
        sem_rest = round((grasa_act - meta_grasa) / tasa) if tasa > 0 else 0
        semanas_restantes = f"A esta tasa: meta en ~{sem_rest} semanas"

    return f"""Genera el resumen semanal para {nombre}.

SEMANA {semana}/4:
Sesiones completadas: {sesiones}/{total_s}
Cambio de peso: {cambio_p:+.1f} kg esta semana
Cambio de grasa: {f'{cambio_g:+.1f}%' if cambio_g else 'sin datos de báscula'}
Racha actual: {racha} días consecutivos

PROGRESIÓN DE FUERZA:
{prog_str}

META: llegar a {meta_grasa}% grasa corporal
Grasa actual: {f'{grasa_act:.1f}%' if grasa_act else 'sin datos'}
{semanas_restantes}

INSTRUCCIONES:
1. Línea 1: El número más importante de la semana (peso, fuerza, o grasa)
2. Línea 2: Evaluación honesta — ¿va en camino o necesita ajuste?
3. Línea 3: Lo más importante para la semana que viene
4. Si hay datos de meta → incluir fecha estimada de llegada
5. Máximo 4 líneas. Directo. Con datos.
Solo en español."""


def prompt_plan_nutricion(datos: dict) -> str:
    """
    Genera el plan de nutrición semanal completo (JSON).
    Gemini lo devuelve como JSON puro, sin markdown.
    """
    u      = datos.get("usuario", {})
    macros = datos.get("macros", {})

    nombre    = (u.get("nombre") or "").split()[0] or "usuario"
    peso      = u.get("peso_kg", 80)
    objetivo  = u.get("objetivo_vida","")
    dieta     = u.get("tipo_dieta","omnivoro")
    cocina    = u.get("cocina","variada")
    alergias  = u.get("alergias","ninguna")
    prots_fav = u.get("proteinas_favoritas","pollo,huevo,atun")
    donde     = u.get("donde_come","casa")
    suplementos= u.get("suplementos","ninguno")
    hora_gym  = u.get("hora_gym","17:00")
    dias_gym  = datos.get("dias_gym", ["lunes","miercoles","viernes","domingo"])

    kcal    = macros.get("kcal", 2200)
    prot_g  = macros.get("proteina_g", 180)
    carbs_g = macros.get("carbs_g", 200)
    grasas_g= macros.get("grasas_g", 70)
    toma_g  = macros.get("toma_proteina", 45)
    refeed  = macros.get("es_refeed", False)
    caseina = macros.get("caseina_nocturna", 0)

    dias_gym_str = ", ".join(dias_gym)

    return f"""Eres un nutriólogo clínico. Genera el plan de nutrición semanal para {nombre}.

PERFIL:
Peso: {peso} kg | Objetivo: {objetivo}
Tipo de dieta: {dieta}
Cocinas favoritas: {cocina}
Restricciones/alergias: {alergias}
Proteínas favoritas: {prots_fav}
Preparación: {donde}
Suplementos disponibles: {suplementos}
Hora de gym: {hora_gym}
Días de gym esta semana: {dias_gym_str}
{'⚠️ SEMANA DE REFEED — calorías a mantenimiento' if refeed else ''}

MACROS CALCULADOS (IIFYM — flexible):
Calorías: {kcal} kcal/día (gym) / {round(kcal * 0.92)} kcal/día (descanso)
Proteína: {prot_g}g → distribuir en 4 tomas de {toma_g}g (threshold leucina: mínimo 30g/toma)
Carbohidratos: {carbs_g}g (gym) / {round(carbs_g * 0.70)}g (descanso)
Grasas: {grasas_g}g

REGLAS CIENTÍFICAS OBLIGATORIAS:
1. Proteína: 4 tomas separadas 3-4h mínimo. Cada toma ≥30g.
2. Pre-workout (1h antes): 30-40g carbs de digestión media + 30g proteína
3. Post-workout (0-2h después): 30-50g carbs rápidos + proteína completa
4. Última comida: {caseina}g proteína de digestión lenta (caseína, requesón, yogur griego)
5. Usar SÓLO los alimentos y cocinas que le gustan al usuario
6. Si come fuera: incluir opciones de restaurante/comida rápida saludable reales
7. No repetir el mismo plato más de 2 veces en la semana

RESPONDE ÚNICAMENTE CON JSON VÁLIDO, sin backticks, sin explicación:
{{
  "semana": {{
    "lunes": {{
      "tipo": "gym",
      "kcal": {kcal},
      "comidas": [
        {{"nombre": "Desayuno", "hora": "7:00", "alimentos": [{{"nombre": "...", "cantidad": "...", "kcal": 0, "prot_g": 0, "carbs_g": 0, "grasas_g": 0}}], "total_kcal": 0, "total_prot": 0}},
        {{"nombre": "Pre-workout", "hora": "...", "alimentos": [...], "total_kcal": 0, "total_prot": 0}},
        {{"nombre": "Post-workout", "hora": "...", "alimentos": [...], "total_kcal": 0, "total_prot": 0}},
        {{"nombre": "Cena", "hora": "20:00", "alimentos": [...], "total_kcal": 0, "total_prot": 0}},
        {{"nombre": "Caseína nocturna", "hora": "22:00", "alimentos": [...], "total_kcal": 0, "total_prot": 0}}
      ]
    }},
    "martes": {{...}},
    "miercoles": {{...}},
    "jueves": {{...}},
    "viernes": {{...}},
    "sabado": {{...}},
    "domingo": {{...}}
  }}
}}"""
