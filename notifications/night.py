from __future__ import annotations
import logging
from datetime import datetime, date, timedelta
from db.database import (fetchall, get_usuario, get_estado, get_ejercicios_dia,
                          get_historial_peso, avanzar_dia, calcular_ajuste_calorico,
                          necesita_refeed, save_analisis)
from engine.nutrition.macros import calcular_macros_dia
from ai.coach import analisis_nocturno
import gamification

logger = logging.getLogger(__name__)
HORA_NOCHE = "21:00"
GRUPO_ICON = {"empuje":"💪","tiron":"🏋️","pierna":"🦵","gluteo":"🍑","core":"🎯"}

async def _resumen(uid: int) -> str:
    u = get_usuario(uid)
    if not u: return ""
    nombre   = (u.get("nombre","") or "").split()[0]
    semana, dia = get_estado(uid)
    ejs      = [e for e in get_ejercicios_dia(uid, semana, dia) if not e.get("es_cardio")]
    grupo    = ejs[0].get("grupo","") if ejs else ""
    icon     = GRUPO_ICON.get(grupo,"💪")

    # Mañana
    sem_man, dia_man = avanzar_dia(uid, semana, dia)
    ejs_man  = [e for e in get_ejercicios_dia(uid, sem_man, dia_man) if not e.get("es_cardio")]
    if ejs_man:
        g2      = ejs_man[0].get("grupo","")
        nom_man = [e["ejercicio"][:22] for e in ejs_man[:3]]
        manana_str = (f"\n\n📅 <b>Mañana — {dia_man.capitalize()}:</b>\n"
                      f"{GRUPO_ICON.get(g2,'💪')} {g2.upper()} · {' · '.join(nom_man)}")
    else:
        manana_str = "\n\n📅 Mañana es día de descanso activo."

    # Macros mañana
    es_gym_man = bool(ejs_man)
    mac = calcular_macros_dia(uid, es_gym=es_gym_man)
    mac_str = ""
    if mac:
        mac_str = (f"\n\n🥗 <b>Nutrición mañana:</b>\n"
                   f"🔥 {mac['kcal']} kcal · 🥩 {mac['proteina_g']}g prot · "
                   f"🍞 {mac['carbs_g']}g carbs\n"
                   f"<i>Prioriza proteína en la primera comida.</i>")

    # Rest day
    if not ejs:
        return (f"🌙 Buenas noches{' ' + nombre if nombre else ''}\n\n"
                f"🌿 Día de recuperación completado. Sigue así."
                f"{manana_str}{mac_str}")

    # Pesos usados
    pesos_lineas = []
    for ej in ejs[:4]:
        hist = get_historial_peso(uid, ej["ejercicio_id"], 1)
        if hist:
            pesos_lineas.append(f"  · {ej['ejercicio'][:22]}: {hist[0]['peso_lbs']} lbs")
    pesos_str = "\n" + "\n".join(pesos_lineas) if pesos_lineas else ""
    racha = gamification.get_racha(uid)
    racha_str = f"  🔥 {racha} días de racha" if racha >= 3 else ""

    # Gemini analiza
    datos_gemini = {
        "usuario": u, "semana": semana, "grupo": grupo,
        "fatiga": u.get("sueño_horas",7),
        "sueño": u.get("sueño_horas","—"),
        "pesos_str": "\n".join(pesos_lineas) or "Sin datos",
        "progresiones": "—", "racha": racha,
    }
    analisis = await analisis_nocturno(datos_gemini)
    if analisis:
        save_analisis(uid, "nocturno", analisis)

    # Ajuste calórico SISO
    ajuste = calcular_ajuste_calorico(uid)
    ajuste_str = ""
    if ajuste["accion"] == "reducir":
        ajuste_str = f"\n\n📉 <b>Ajuste automático:</b> -{ajuste['kcal']} kcal\n<i>{ajuste['razon']}</i>"
    elif ajuste["accion"] == "subir":
        ajuste_str = f"\n\n📈 <b>Ajuste automático:</b> +{ajuste['kcal']} kcal\n<i>{ajuste['razon']}</i>"
    if necesita_refeed(uid):
        ajuste_str += "\n\n🔄 <b>Semana de refeed activada</b> — esta semana comes a mantenimiento."

    return (f"🌙 Buenas noches{' ' + nombre if nombre else ''}\n\n"
            f"{icon} <b>{dia.capitalize()} — {grupo.upper()}</b>{racha_str}"
            f"{pesos_str}\n\n{analisis}"
            f"{ajuste_str}{manana_str}{mac_str}")


async def enviar_resumenes(bot=None):
    if not bot: return
    hora = datetime.now().strftime("%H:%M")
    if hora != HORA_NOCHE: return
    usuarios = fetchall(
        "SELECT u.user_id FROM usuarios u JOIN usuarios_permitidos p ON u.user_id=p.user_id "
        "WHERE u.onboarding_done=1", ()
    )
    for u in usuarios:
        try:
            msg = await _resumen(u["user_id"])
            if msg:
                await bot.send_message(chat_id=u["user_id"], text=msg, parse_mode="HTML")
        except Exception as e:
            logger.error("Error resumen nocturno uid=%s: %s", u["user_id"], e)
