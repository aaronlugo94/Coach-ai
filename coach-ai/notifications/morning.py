from __future__ import annotations
import logging
from datetime import datetime, date, timedelta
from db.database import fetchall, get_usuario, get_estado, get_ejercicios_dia, get_peso_sugerido
from engine.nutrition.macros import calcular_macros_dia
import gamification

logger = logging.getLogger(__name__)
TZ = "America/Phoenix"
GRUPO_ICON = {"empuje":"💪","tiron":"🏋️","pierna":"🦵","gluteo":"🍑","core":"🎯","cardio":"🏃"}

def _msg_manana(uid: int) -> str:
    import random
    u = get_usuario(uid)
    if not u: return ""
    nombre = (u.get("nombre","") or "").split()[0]
    saludo = f"Buenos días {nombre} ☀️" if nombre else "Buenos días ☀️"
    racha  = gamification.get_racha(uid)
    racha_str = f"\n🔥 {racha} días de racha — no la rompas." if racha >= 3 else ""
    semana, dia = get_estado(uid)
    ejs = [e for e in get_ejercicios_dia(uid, semana, dia) if not e.get("es_cardio")]
    es_gym = bool(ejs)
    mac = calcular_macros_dia(uid, es_gym=es_gym)
    mac_str = ""
    if mac:
        mac_str = (f"\n\n🥗 Macros de hoy: {mac['kcal']} kcal · "
                   f"🥩 {mac['proteina_g']}g prot")
    if not ejs:
        RECOVERY = [
            "🧘 Movilidad 15 min — caderas, hombros, columna",
            "🚶 Caminata 20-30 min a ritmo cómodo",
            "🚴 Bici suave 20 min — FC < 110 bpm",
            "🎯 Core: plancha · dead bug · bird dog",
        ]
        return (f"{saludo}{racha_str}\n\n"
                f"Hoy es día de <b>recuperación activa</b>:\n"
                f"{random.choice(RECOVERY)}\n\n"
                f"Proteína alta y 7-9h de sueño."
                f"{mac_str}")
    grupo  = ejs[0].get("grupo","")
    icon   = GRUPO_ICON.get(grupo,"💪")
    primer = ejs[0]
    sug    = get_peso_sugerido(uid, primer["ejercicio_id"], primer.get("reps","8-10"), primer.get("patron",""))
    sug_str = f"\n→ Empieza con <b>{sug} lbs</b> en {primer['ejercicio'][:22]}" if sug else ""
    nombres = [e["ejercicio"][:25] for e in ejs[:3]]
    resto   = f" +{len(ejs)-3} más" if len(ejs) > 3 else ""
    return (f"{saludo}{racha_str}\n\n"
            f"{icon} Hoy toca <b>{grupo.upper()}</b>{sug_str}\n"
            f"📋 {' · '.join(nombres)}{resto}\n\n"
            f"Abre el bot cuando estés listo 👇"
            f"{mac_str}")

async def enviar_recordatorios(bot=None):
    if not bot: return
    hora_actual = datetime.now().strftime("%H:%M")
    usuarios = fetchall(
        "SELECT u.user_id, u.hora_reminder FROM usuarios u "
        "JOIN usuarios_permitidos p ON u.user_id=p.user_id "
        "WHERE u.onboarding_done=1 AND u.hora_reminder IS NOT NULL", ()
    )
    for u in usuarios:
        hora = u.get("hora_reminder","")
        if not hora or hora.startswith("PAUSA"): continue
        if hora != hora_actual: continue
        try:
            msg = _msg_manana(u["user_id"])
            if msg:
                await bot.send_message(chat_id=u["user_id"], text=msg, parse_mode="HTML")
        except Exception as e:
            logger.error("Error recordatorio uid=%s: %s", u["user_id"], e)
