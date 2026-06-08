"""
ai/prompts.py — Todos los prompts de Gemini centralizados.
"""

def prompt_coach_nocturno(datos: dict) -> str:
    u = datos.get("usuario",{})
    return f"""Eres el coach personal de {u.get('nombre','este usuario')}.
Analiza sus datos reales de hoy y da retroalimentación concreta.

PERFIL:
Objetivo: {u.get('objetivo_vida','general')} | Nivel: {u.get('nivel','intermedio')}
Semana {datos.get('semana',1)}/4 del ciclo {'— DELOAD' if datos.get('deload') else ''}
Racha: {datos.get('racha',0)} días consecutivos

HOY — {datos.get('grupo','').upper()}:
Fatiga reportada: {datos.get('fatiga','—')}/5
Sueño: {datos.get('sueño','—')} horas

PESOS USADOS:
{datos.get('pesos_str','Sin datos')}

PROGRESIONES (subió vs semana anterior):
{datos.get('progresiones','Ninguna')}

ACTIVIDAD (Google Fit):
Pasos: {datos.get('pasos','—')} | Calorías activas: {datos.get('calorias_activas','—')}
HRV: {datos.get('hrv','—')} | FC reposo: {datos.get('fc_reposo','—')}

INSTRUCCIONES:
1. Línea 1: lo más relevante de los datos de HOY con números reales
2. Línea 2: si hay estancamiento di POR QUÉ (fatiga, proteína, técnica)
3. Línea 3: UNA acción concreta para mañana — puede ser de entrenamiento O nutrición
4. Si fatiga >= 4: prioridad sueño y proteína
5. Si es deload: NO subir pesos, explicar supercompensación
6. Máximo 3 líneas. Sin bullet points. Sin emojis excesivos. Tono de coach directo.
Solo en español."""


def prompt_plan_nutricion(datos: dict) -> str:
    u   = datos.get("usuario",{})
    mac = datos.get("macros",{})
    return f"""Genera un plan de nutrición para 7 días.

PERFIL:
Nombre: {u.get('nombre','Usuario')}
Objetivo: {u.get('objetivo_vida','general')}
Peso: {u.get('peso_kg','—')}kg | Altura: {u.get('altura_cm','—')}cm | Edad: {u.get('edad','—')} años
Tipo de dieta: {u.get('tipo_dieta','omnivoro')}
Restricciones: {u.get('alergias','ninguna')}
Cocina favorita: {u.get('cocina','variada')}
Patrón de comidas: {u.get('patron_comidas','3')} comidas/día
Suplementos: {u.get('suplementos','ninguno')}
Alcohol: {u.get('alcohol','no')}

MACROS CALCULADOS:
Calorías: {mac.get('kcal','—')} kcal/día
Proteína: {mac.get('proteina_g','—')}g (distribuir en 4 tomas de {mac.get('toma_proteina','—')}g)
Carbos: {mac.get('carbs_g','—')}g
Grasas: {mac.get('grasas_g','—')}g
{'⚠️ SEMANA DE REFEED — comer a mantenimiento' if mac.get('es_refeed') else ''}

REGLAS CIENTÍFICAS OBLIGATORIAS:
1. Proteína en 4 tomas separadas 3-4h. Cada toma mínimo 30g para superar threshold de leucina.
2. Días de gym: 50-60% de carbos en las 2h antes y después del entreno.
3. Última comida del día: siempre incluir 30-40g de proteína de digestión lenta (yogur griego, requesón, cottage cheese).
4. No mezclar grasa alta + carbos altos en la misma comida.
5. Usar ingredientes de la cocina favorita del usuario.
6. Si come fuera frecuentemente: incluir opciones de restaurante/comida rápida saludable.
7. Hidratación: {round(float(u.get('peso_kg',80))*35)}ml de agua mínimo diario.

FORMATO DE RESPUESTA (JSON válido, sin markdown):
{{
  "dias": [
    {{
      "dia": "Lunes",
      "tipo": "gym",
      "kcal": 2300,
      "comidas": [
        {{"nombre": "Desayuno", "alimentos": [{{"nombre": "Avena", "cantidad": "80g", "kcal": 290, "proteina": 10}}], "kcal": 450, "proteina": 40}},
        {{"nombre": "Almuerzo", "alimentos": [...], "kcal": 600, "proteina": 40}},
        {{"nombre": "Pre-workout", "alimentos": [...], "kcal": 400, "proteina": 35}},
        {{"nombre": "Cena", "alimentos": [...], "kcal": 550, "proteina": 35}},
        {{"nombre": "Caseína nocturna", "alimentos": [{{"nombre": "Yogur griego", "cantidad": "200g", "kcal": 130, "proteina": 20}}], "kcal": 200, "proteina": 35}}
      ]
    }}
  ]
}}"""
