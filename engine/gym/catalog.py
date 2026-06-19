from dataclasses import dataclass, field

@dataclass
class Ejercicio:
    id: str
    nombre: str
    grupo: str
    patron: str
    rol: str = "principal"
    ambiente: list = field(default_factory=lambda: ["gym"])
    emg_score: int = 3
    notas: str = ""
    es_cardio: bool = False

CATALOG = [
    # ── EMPUJE ───────────────────────────────────────────────────────────────
    Ejercicio("pp01","Press de pecho con barra","empuje","press_horizontal",notas="escápulas retraídas, arco natural, barra a pecho bajo"),
    Ejercicio("pp02","Press inclinado con barra","empuje","press_inclinado",notas="30-45°, codos a 75°, no flares"),
    Ejercicio("pp03","Press de pecho con mancuernas","empuje","press_horizontal",notas="rango completo, codos ligeramente abajo del hombro"),
    Ejercicio("pp04","Press inclinado con mancuernas","empuje","press_inclinado",notas="palmas neutras al bajar, pronate al subir"),
    Ejercicio("pp05","Press militar con barra","empuje","press_vertical",notas="core apretado, no hiperextender la espalda baja"),
    Ejercicio("pp06","Press de hombro con mancuernas","empuje","press_vertical",notas="codos a 90° al inicio, completa el rango"),
    Ejercicio("pp07","Elevaciones laterales con mancuernas","empuje","press_vertical",rol="accesorio",notas="codos ligeramente flexionados, lento en bajada"),
    Ejercicio("pp08","Elevaciones laterales en polea baja","empuje","press_vertical",rol="accesorio",notas="tensor constante, más activación EMG que mancuerna"),
    Ejercicio("pp09","Fondos en paralelas","empuje","press_horizontal",ambiente=["gym","home"],notas="inclinación adelante para pecho, vertical para tríceps"),
    Ejercicio("pp10","Push up inclinado","empuje","press_horizontal",ambiente=["home","band"],notas="cuerpo en línea, escápulas activas"),
    Ejercicio("pp11","Extensión de tríceps en polea","empuje","press_vertical",rol="accesorio",notas="codos fijos, solo antebrazo se mueve"),
    Ejercicio("pp12","Press en máquina Smith","empuje","press_horizontal",notas="útil para aprender el patrón con seguridad"),

    # ── TIRÓN ─────────────────────────────────────────────────────────────────
    Ejercicio("pt01","Jalón al pecho agarre ancho","tiron","jalon_vertical",notas="codos hacia las caderas, no jales con las manos"),
    Ejercicio("pt02","Jalón al pecho agarre neutro","tiron","jalon_vertical",notas="mayor activación del dorsal inferior"),
    Ejercicio("pt03","Remo con barra","tiron","remo_horizontal",notas="espalda neutra, codos a 45°, retracción completa"),
    Ejercicio("pt04","Remo con mancuerna","tiron","remo_horizontal",notas="apoya rodilla en banco, codo pegado al cuerpo"),
    Ejercicio("pt05","Remo en máquina sentado","tiron","remo_horizontal",notas="pecho en pad, full retracción escápular"),
    Ejercicio("pt06","Dominadas","tiron","jalon_vertical",ambiente=["gym","home"],notas="muerto colgado, escápulas primero, codos a caderas"),
    Ejercicio("pt07","Remo Pendlay","tiron","remo_horizontal",notas="desde el piso cada rep, explosivo, técnica estricta"),
    Ejercicio("pt08","Face pull en polea","tiron","remo_horizontal",rol="accesorio",notas="a altura de cara, manos al lado de orejas, rotación externa"),
    Ejercicio("pt09","Curl de bíceps con barra","tiron","curl",rol="accesorio",notas="codos fijos, supinación al final"),
    Ejercicio("pt10","Curl de bíceps con mancuernas","tiron","curl",rol="accesorio",notas="alterna o simultáneo, no balancear"),
    Ejercicio("pt11","Curl martillo","tiron","curl",rol="accesorio",notas="agarre neutro, trabaja braquial y braquiorradial"),

    # ── PIERNA ────────────────────────────────────────────────────────────────
    Ejercicio("pl01","Sentadilla con barra","pierna","sentadilla",notas="profundidad paralela o abajo, rodillas rastrean pies"),
    Ejercicio("pl02","Sentadilla frontal","pierna","sentadilla",notas="más cuádriceps, codos arriba, torso más vertical"),
    Ejercicio("pl03","Peso muerto rumano","pierna","bisagra_cadera",notas="barra cerca del cuerpo, bisagra pura, siente el isquio"),
    Ejercicio("pl04","Peso muerto convencional","pierna","peso_muerto",notas="bar over mid-foot, escápulas sobre la barra, empuja el piso"),
    Ejercicio("pl05","Prensa de pierna","pierna","sentadilla",notas="pies al ancho de hombros, no bloquees rodillas"),
    Ejercicio("pl06","Hack squat en máquina","pierna","sentadilla",notas="pies juntos y bajos = cuádriceps, altos = glúteo"),
    Ejercicio("pl07","Zancadas con mancuernas","pierna","sentadilla",rol="accesorio",notas="rodilla trasera casi al piso, torso erguido"),
    Ejercicio("pl08","Curl femoral tumbado","pierna","bisagra_cadera",rol="accesorio",notas="cadera pegada al pad, no balancear la cadera"),
    Ejercicio("pl09","Curl femoral sentado","pierna","bisagra_cadera",rol="accesorio",notas="mayor estiramiento, mejor activación EMG"),
    Ejercicio("pl10","Extensión de cuádriceps","pierna","sentadilla",rol="accesorio",notas="útil para finalizar cuádriceps, no como principal"),
    Ejercicio("pl11","Elevación de gemelos de pie","pierna","gemelo",rol="accesorio",notas="rango completo, pausa en estiramiento"),
    Ejercicio("pl12","Caminata inclinada en cinta","pierna","cardio",es_cardio=True,notas="zona 2 — si puedes hablar, estás en la zona correcta"),

    # ── GLÚTEO ────────────────────────────────────────────────────────────────
    Ejercicio("pg01","Hip thrust con barra","gluteo","bisagra_cadera",notas="escápulas en banco, drive con talones, apretar glúteo arriba"),
    Ejercicio("pg02","Hip thrust en máquina","gluteo","bisagra_cadera",notas="igual que barra, permite más foco en el movimiento"),
    Ejercicio("pg03","Peso muerto sumo","gluteo","bisagra_cadera",notas="stance amplio, pies en 45°, cadera a la barra"),
    Ejercicio("pg04","Sentadilla sumo con mancuerna","gluteo","sentadilla",notas="stance amplio, mancuerna al centro, profundidad completa"),
    Ejercicio("pg05","Kickback en polea","gluteo","gluteo_aislamiento",rol="accesorio",notas="cadera neutra, no rotar el tronco"),
    Ejercicio("pg06","Abducción en máquina","gluteo","gluteo_aislamiento",rol="accesorio",notas="lento en bajada, no dejar caer el peso"),
    Ejercicio("pg07","Zancada reversa con mancuerna","gluteo","sentadilla",rol="accesorio",notas="más glúteo que zancada normal"),
    Ejercicio("pg08","Step up en banco","gluteo","sentadilla",rol="accesorio",ambiente=["gym","home"],notas="empuja con el talón del pie de adelante"),

    # ── CORE ──────────────────────────────────────────────────────────────────
    Ejercicio("pc01","Plancha frontal","core","anti_extension",ambiente=["gym","home","band"],rol="accesorio",notas="cuerpo en línea, no elevar cadera, respira"),
    Ejercicio("pc02","Dead bug","core","anti_extension",ambiente=["gym","home","band"],rol="accesorio",notas="espalda baja pegada al piso durante todo el movimiento"),
    Ejercicio("pc03","Pallof press en polea","core","anti_rotacion",rol="accesorio",notas="core resistiendo la rotación, no el torso"),
    Ejercicio("pc04","Crunch en polea","core","flexion",rol="accesorio",notas="cifosis toráxica controlada, no flexión de cadera"),
    Ejercicio("pc05","Ab wheel rollout","core","anti_extension",ambiente=["gym","home"],rol="accesorio",notas="avanzado, espalda baja neutra todo el tiempo"),
]

BY_ID = {e.id: e for e in CATALOG}


PATRONES_SIMILARES = {
    "press_horizontal": {"press_horizontal"},
    "press_inclinado":  {"press_inclinado", "press_horizontal"},
    "press_vertical":   {"press_vertical"},
    "jalon_vertical":   {"jalon_vertical"},
    "remo_horizontal":  {"remo_horizontal"},
    "curl":             {"curl"},
    "sentadilla":       {"sentadilla"},
    "bisagra_cadera":   {"bisagra_cadera"},
    "peso_muerto":      {"peso_muerto", "bisagra_cadera"},
}


def buscar_alternativas(ejercicio_id: str, ambiente: str = "gym",
                        excluir_patron: list = None, n: int = 4) -> list[Ejercicio]:
    """
    Busca ejercicios alternativos al actual: mismo patrón de movimiento
    (no solo mismo grupo muscular general — un press de pecho no debe
    sugerir un press militar como alternativa), mismo rol, compatibles
    con el ambiente disponible, excluyendo lesiones. Si no hay suficientes
    alternativas con el mismo patrón exacto, amplía al grupo muscular completo.
    """
    actual = BY_ID.get(ejercicio_id)
    if not actual:
        return []
    excl = excluir_patron or []
    patrones_ok = PATRONES_SIMILARES.get(actual.patron, {actual.patron})

    def _candidatos(solo_patron: bool) -> list[Ejercicio]:
        return [
            e for e in CATALOG
            if e.id != ejercicio_id
            and e.grupo == actual.grupo
            and e.rol == actual.rol
            and ambiente in e.ambiente
            and e.patron not in excl
            and not e.es_cardio
            and (e.patron in patrones_ok if solo_patron else True)
        ]

    candidatos = _candidatos(solo_patron=True)
    if len(candidatos) < n:
        # Ampliar al grupo muscular completo si no hay suficientes
        extra = [e for e in _candidatos(solo_patron=False) if e not in candidatos]
        candidatos += extra

    candidatos.sort(key=lambda e: -e.emg_score)
    return candidatos[:n]
