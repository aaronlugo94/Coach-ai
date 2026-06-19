"""
bot/handlers/menu.py — Menú principal y comandos.
"""
from __future__ import annotations
import logging, os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db.database import (get_usuario, get_estado, has_plan, upsert_usuario,
                          create_login_token, get_ultimo_pesaje, get_allowed_users)
from bot.keyboards import TECLADO_PRINCIPAL, MENU_INLINE, BTN_MENU, kb_horario
from engine.body.healthconnect import get_auth_url, esta_conectado
import gamification

logger = logging.getLogger(__name__)
WEB_URL = os.environ.get("FRONTEND_URL","https://coach-ai.vercel.app")
ADMIN   = int(os.environ.get("ADMIN_TELEGRAM_ID","0"))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    nombre = update.effective_user.first_name or ""
    # Siempre registrar el usuario en la DB al hacer /start
    upsert_usuario(uid, nombre=nombre)
    n      = nombre.split()[0] if nombre else "ahí"

    if not has_plan(uid):
        # Un solo mensaje de bienvenida + botón Empezar
        await update.message.reply_text(
            f"Hola {n}! 👋\n\n"
            "<b>Soy tu entrenador y nutriólogo personal con IA.</b>\n\n"
            "En 4 bloques rápidos entiendo tu biología, experiencia y estilo "
            "de vida para diseñar un plan que realmente funcione.\n\n"
            "Lo que hago por ti:\n"
            "  🧠 Ajusto tu entrenamiento según tu fatiga real cada día\n"
            "  📈 Subo tus pesos automáticamente cuando estás listo\n"
            "  🥗 Ajusto tus calorías cada semana según la báscula\n\n"
            "Todo corre solo — tú solo entrenas y registras.\n\n"
            "Toca <b>Empezar</b> cuando estés listo 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Empezar →", callback_data="bienvenida:start")]
            ]))
        return

    semana, dia = get_estado(uid)
    racha = gamification.get_racha(uid)
    racha_str = f"🔥 {racha} días de racha  ·  " if racha >= 3 else ""
    pesaje = get_ultimo_pesaje(uid)
    peso_str = f"⚖️ {pesaje['peso_kg']} kg" if pesaje else ""

    await update.message.reply_text(
        f"Hola {n} 👋  {racha_str}{peso_str}\n\n¿Qué hacemos? 👇",
        reply_markup=TECLADO_PRINCIPAL, parse_mode="HTML")
    await update.message.reply_text("Menú:", reply_markup=MENU_INLINE)


async def cmd_reset_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¿Qué quieres cambiar?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💪 Nueva rutina de gym",  callback_data="rst:gym")],
            [InlineKeyboardButton("🥗 Nuevo plan de dieta",  callback_data="rst:dieta")],
            [InlineKeyboardButton("🔄 Los dos",              callback_data="rst:todo")],
            [InlineKeyboardButton("❌ Cancelar",             callback_data="m:main")],
        ]))


async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    nombre = update.effective_user.first_name or ""
    # Asegurar que el usuario existe en la DB antes de crear el token
    upsert_usuario(uid, nombre=nombre)
    token = create_login_token(uid)
    url   = f"{WEB_URL}/login?token={token}"
    await update.message.reply_text(
        f"Toca para entrar a la web 👇\n<i>Válido 10 minutos.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Invisible Coach", url=url)]]))


async def cmd_conectar_fit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if esta_conectado(uid):
        await update.message.reply_text(
            "✅ Google Fit ya está conectado.\n\n"
            "Los datos del OnePlus Watch 4 se sincronizan cada mañana automáticamente.")
        return
    url = get_auth_url(uid)
    await update.message.reply_text(
        "Conecta Google Fit para que el bot reciba:\n"
        "👟 Pasos · 🔥 Calorías · 😴 Sueño · ❤️ Frecuencia cardíaca\n\n"
        "Toca el botón y autoriza en Google 👇",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 Conectar Google Fit", url=url)
        ]]))


async def cmd_conectar_renpho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_usuario(uid)
    if u and u.get("renpho_email") and u.get("renpho_password"):
        await update.message.reply_text(
            "✅ Báscula Renpho ya conectada.\n\n"
            "Sincroniza automáticamente entre 6-10am.\n"
            "Para cambiar tus datos, escribe /conectar_renpho de nuevo.")
    context.user_data["renpho_step"] = "email"
    await update.message.reply_text(
        "⚖️ <b>Conectar báscula Renpho</b>\n\n"
        "Escribe el <b>email</b> de tu cuenta Renpho:\n"
        "<i>(el mismo que usas en la app)</i>",
        parse_mode="HTML")


async def cmd_sethorario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏰ ¿A qué hora quieres tu recordatorio?",
                                    reply_markup=kb_horario())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>Comandos disponibles</b>\n\n"
        "<code>/start</code>\n"
        "Abre el menú principal. Si no has hecho el setup, te guía paso a paso (objetivo, perfil, dieta, etc.)\n\n"
        "<code>/login</code>\n"
        "Te manda un link para entrar a la web app desde tu navegador — ahí ves tu progreso, gráficas y el plan de nutrición completo\n\n"
        "<code>/sethorario</code>\n"
        "Cambia la hora a la que entrenas. Tu briefing matutino y check-in nocturno se reajustan automáticamente (2h antes/después)\n\n"
        "<code>/reset_plan</code>\n"
        "Genera una nueva rutina y/o dieta SIN repetir todo el setup — solo te pregunta lo que pudo cambiar (días, nivel, lesiones)\n\n"
        "<code>/conectar_fit</code>\n"
        "Conecta Google Fit/WearOS — importa peso, sueño, HRV y FC reposo automáticamente cada día\n\n"
        "<code>/conectar_renpho</code>\n"
        "Conecta tu báscula Renpho — sincroniza tu peso solo, sin que tengas que escribirlo a mano\n\n"
        "💪 <b>Desde el menú principal (botones) también puedes:</b>\n"
        "  • Ver tu rutina del día\n"
        "  • Ver tus macros y plan de comidas\n"
        "  • Revisar tu progreso corporal\n"
        "  • Compartir tu racha en Instagram\n\n"
        "💡 <i>Para todo lo del día a día usa los botones — los comandos son solo para configuración.</i>",
        parse_mode="HTML")


async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN: return
    if not context.args:
        await update.message.reply_text("Uso: /adduser <id>"); return
    from db.database import add_allowed_user
    add_allowed_user(int(context.args[0]))
    await update.message.reply_text(f"✅ {context.args[0]} agregado.")


async def handle_menu(query, uid: int, context):
    sub = query.data.split(":")[1]
    if sub == "main":
        u = get_usuario(uid)
        nombre = u.get("nombre","") if u else ""
        racha  = gamification.get_racha(uid)
        racha_str = f"🔥 {racha} días de racha" if racha >= 3 else ""
        try:
            await query.edit_message_text(
                f"{'Hola ' + nombre.split()[0] + ' 👋  ' if nombre else ''}{racha_str}\n\n¿Qué hacemos?",
                reply_markup=MENU_INLINE, parse_mode="HTML")
        except Exception: pass

    elif sub == "hoy":
        from bot.handlers.gym import handle_rutina_preview, _render_ejercicio
        semana, dia = get_estado(uid)
        sesion_activa = context.user_data.get("sesion")

        if sesion_activa and sesion_activa.get("semana") == semana and sesion_activa.get("dia") == dia:
            # Hay una sesión a medio camino — continuar ahí, no reiniciar
            idx = sesion_activa.get("idx", 0)
            txt, kb = _render_ejercicio(uid, semana, dia, idx, context)
            try: await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
            except Exception: pass
        else:
            await handle_rutina_preview(uid, semana, dia, query=query)

    elif sub == "cuerpo":
        pesaje = get_ultimo_pesaje(uid)
        if not pesaje:
            try: await query.edit_message_text("⚖️ Sin pesajes aún.\nPésate en ayunas (6-9am).", reply_markup=BTN_MENU)
            except Exception: pass
            return
        u       = get_usuario(uid) or {}
        obj     = u.get("objetivo_vida","")
        meta    = {"bajar_grasa":"🎯 Bajar grasa","ganar_musculo":"🎯 Ganar músculo",
                   "recomposicion":"🎯 Recomposición","gluteo_pierna":"🎯 Glúteo y pierna",
                   "salud":"🎯 Salud","competitivo":"🎯 Nivel competitivo"}.get(obj,"")

        # Actividad reciente de Google Fit (si está conectado) — pasos,
        # distancia y SpO2, aprovechando todo lo que reporta el reloj
        actividad_str = ""
        from db.database import get_actividad_dia
        activ = get_actividad_dia(uid)
        if activ:
            piezas = []
            if activ.get("pasos"):
                piezas.append(f"👟 {activ['pasos']:,} pasos")
            if activ.get("distancia_km"):
                piezas.append(f"📍 {activ['distancia_km']} km")
            if activ.get("spo2_pct"):
                spo2 = activ["spo2_pct"]
                alerta = " ⚠️" if spo2 < 94 else ""
                piezas.append(f"🫁 SpO2 {spo2}%{alerta}")
            if piezas:
                actividad_str = "\n\n" + "  ·  ".join(piezas)

        try:
            await query.edit_message_text(
                f"⚖️ <b>{pesaje['fecha']}</b>\n\n"
                f"Peso: {pesaje['peso_kg']} kg\n"
                f"Grasa: {pesaje.get('grasa_pct','—')}%  |  Músculo: {pesaje.get('musculo_pct','—')}%\n"
                f"BMR medido: {pesaje.get('bmr_medido','—')} kcal"
                f"{chr(10) + meta if meta else ''}"
                f"{actividad_str}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Ver tendencia", url=f"{WEB_URL}/cuerpo")],
                    [InlineKeyboardButton("🏠 Menú", callback_data="m:main")],
                ]), parse_mode="HTML")
        except Exception: pass

    elif sub == "dieta":
        from engine.nutrition.macros import calcular_macros_dia
        from db.database import get_ejercicios_dia, get_plan_nutricion_activo
        import json as _json

        semana, dia = get_estado(uid)
        es_gym = bool(get_ejercicios_dia(uid, semana, dia))
        mac = calcular_macros_dia(uid, es_gym=es_gym)
        if not mac:
            try: await query.edit_message_text("🥗 Pésate para calcular tus macros.", reply_markup=BTN_MENU)
            except Exception: pass
            return

        ajuste = mac.get("ajuste_siso",{})
        ajuste_str = ""
        if ajuste.get("accion") == "reducir":
            ajuste_str = f"\n📉 Ajuste: -{ajuste['kcal']} kcal — {ajuste['razon']}"
        elif ajuste.get("accion") == "subir":
            ajuste_str = f"\n📈 Ajuste: +{ajuste['kcal']} kcal — {ajuste['razon']}"
        refeed_str = "\n🔄 <b>Semana de refeed</b> — comes a mantenimiento esta semana." if mac.get("es_refeed") else ""

        header = (
            f"🥗 <b>{'Hoy — día de gym' if mac['es_gym'] else 'Hoy — día de descanso'}</b>\n\n"
            f"🔥 {mac['kcal']} kcal\n"
            f"🥩 {mac['proteina_g']}g proteína ({mac['toma_proteina']}g × 4 tomas)\n"
            f"🍞 {mac['carbs_g']}g carbs  🥑 {mac['grasas_g']}g grasas"
            f"{ajuste_str}{refeed_str}"
        )

        # Intentar mostrar las comidas reales del plan semanal generado
        comidas_str = ""
        try:
            plan = get_plan_nutricion_activo(uid)
            if plan and plan.get("plan_json"):
                data = _json.loads(plan["plan_json"])
                dia_plan = data.get("semana", {}).get(dia)
                if dia_plan and dia_plan.get("comidas"):
                    lineas = []
                    for c in dia_plan["comidas"]:
                        alimentos = ", ".join(a.get("nombre","") for a in c.get("alimentos",[])[:3])
                        lineas.append(f"<b>{c.get('hora','')} — {c.get('nombre','')}</b>\n{alimentos}")
                    comidas_str = "\n\n" + "\n\n".join(lineas)
        except Exception:
            pass

        if not comidas_str:
            comidas_str = "\n\n<i>Plan de comidas en camino — genéralo en la web (Nutrición → Generar ahora)</i>"

        try:
            await query.edit_message_text(
                header + comidas_str,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Ver plan completo", url=f"{WEB_URL}/nutricion")],
                    [InlineKeyboardButton("🏠 Menú", callback_data="m:main")],
                ]), parse_mode="HTML")
        except Exception: pass

    elif sub == "nuevo":
        try:
            await query.edit_message_text(
                "¿Qué quieres cambiar?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💪 Nueva rutina de gym",  callback_data="rst:gym")],
                    [InlineKeyboardButton("🥗 Nuevo plan de dieta",  callback_data="rst:dieta")],
                    [InlineKeyboardButton("🔄 Los dos",              callback_data="rst:todo")],
                    [InlineKeyboardButton("❌ Cancelar",             callback_data="m:main")],
                ]))
        except Exception: pass


async def handle_rst(query, uid: int, context):
    tipo = query.data.split(":")[1]
    from bot.handlers.onboarding import iniciar_ciclo, regenerar_dieta

    if tipo in ("gym", "todo"):
        # Solo pregunta parámetros de ciclo (nivel/días/duración/horario/
        # ambiente/lesiones) — reusa peso, dieta, proteínas, etc. de la DB.
        await iniciar_ciclo(query, uid, context, incluir_dieta=(tipo == "todo"))

    elif tipo == "dieta":
        # Regenera el plan de nutrición directo, sin preguntas —
        # usa el perfil y macros actuales.
        try:
            await query.edit_message_text(
                "🥗 <b>Generando tu nuevo plan de nutrición...</b>\n\n"
                "<i>Usando tu perfil actual — puede tardar 30s</i>",
                parse_mode="HTML")
        except Exception: pass

        plan = await regenerar_dieta(uid)

        try:
            if plan:
                await query.edit_message_text(
                    "✅ <b>Plan de nutrición actualizado</b>\n\n"
                    "Tu nuevo plan semanal ya está listo.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🥗 Ver mi dieta", callback_data="m:dieta")],
                        [InlineKeyboardButton("🏠 Menú", callback_data="m:main")],
                    ]))
            else:
                await query.edit_message_text(
                    "⚠️ No se pudo generar el plan. Intenta de nuevo o usa la web.",
                    parse_mode="HTML",
                    reply_markup=BTN_MENU)
        except Exception: pass


async def handle_horario(query, uid: int):
    parts = query.data.split(":")
    hora = None if parts[1] == "none" else f"{parts[1]}:{parts[2]}" if len(parts)>2 else parts[1]
    upsert_usuario(uid, hora_reminder=hora)
    msg = f"⏰ Recordatorio: <b>{hora}</b> ✅" if hora else "❌ Recordatorio desactivado"
    try: await query.edit_message_text(msg, reply_markup=BTN_MENU, parse_mode="HTML")
    except Exception: pass


async def handler_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    texto = (update.message.text or "").strip()

    # ── Texto libre durante onboarding ("Otra...") ───────────────────────────
    esperando = context.user_data.get("esperando_texto")
    if esperando in ("lesion_otra", "restriccion_otra", "recuperacion_otra"):
        from bot.handlers.onboarding import handle_texto_otra
        await handle_texto_otra(update, context, esperando, texto)
        return

    # ── Flujo de conexión Renpho (email + password) ──────────────────────────
    renpho_step = context.user_data.get("renpho_step")
    if renpho_step == "email":
        context.user_data["renpho_email"] = texto
        context.user_data["renpho_step"]  = "password"
        await update.message.reply_text(
            "🔒 Ahora escribe tu <b>contraseña</b> de Renpho:\n\n"
            "<i>Tu mensaje se borrará automáticamente por seguridad.</i>",
            parse_mode="HTML")
        return

    if renpho_step == "password":
        email = context.user_data.pop("renpho_email", "")
        context.user_data.pop("renpho_step", None)
        upsert_usuario(uid, renpho_email=email, renpho_password=texto, renpho_last_sync=None)

        # Borrar el mensaje con la contraseña por seguridad
        try:
            await update.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=uid,
            text=(
                "✅ <b>Báscula Renpho conectada</b>\n\n"
                "Sincroniza automáticamente entre 6-10am.\n"
                "Cuando te peses, los macros se ajustan solos (SISO)."
            ),
            parse_mode="HTML")
        return

    BOTONES = {
        "💪 Rutina de hoy": "hoy",
        "⚖️ Mi cuerpo":     "cuerpo",
        "🥗 Mi dieta":      "dieta",
        "❓ Ayuda":         "ayuda",
    }
    if texto in BOTONES:
        accion = BOTONES[texto]
        if accion == "hoy":
            from bot.handlers.gym import handle_rutina_preview
            semana, dia = get_estado(uid)
            await handle_rutina_preview(uid, semana, dia, msg=update.message)
        elif accion == "cuerpo":
            pesaje = get_ultimo_pesaje(uid)
            if not pesaje:
                await update.message.reply_text("⚖️ Sin pesajes aún. Pésate en ayunas.")
            else:
                await update.message.reply_text(
                    f"⚖️ {pesaje['fecha']}\nPeso: {pesaje['peso_kg']} kg",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🌐 Ver tendencia", url=f"{WEB_URL}/cuerpo")
                    ]]))
        elif accion == "dieta":
            from engine.nutrition.macros import calcular_macros_dia
            from db.database import get_ejercicios_dia
            es_gym = bool(get_ejercicios_dia(uid, *get_estado(uid)))
            mac = calcular_macros_dia(uid, es_gym=es_gym)
            if not mac:
                await update.message.reply_text("🥗 Pésate para calcular tus macros.")
            else:
                await update.message.reply_text(
                    f"🥗 {mac['kcal']} kcal  🥩 {mac['proteina_g']}g  "
                    f"🍞 {mac['carbs_g']}g  🥑 {mac['grasas_g']}g")
        elif accion == "ayuda":
            await update.message.reply_text(
                "/start /login /sethorario /reset_plan /conectar_fit")
        return

    step = context.user_data.get("ob_step")
    if step == "datos":
        from bot.handlers.onboarding import handle_datos_texto
        await handle_datos_texto(uid, texto, update, context)
        return
    if step == "restriccion_otra":
        context.user_data["rest_extra"] = texto.strip()
        context.user_data["ob_step"] = None
        from bot.keyboards import kb_restricciones
        sel = context.user_data.get("rest_sel", set())
        await update.message.reply_text(
            f"✅ Anotado: {texto.strip()}\n\nSelecciona más o confirma:",
            reply_markup=kb_restricciones(sel))
        return

    await update.message.reply_text("Usa los botones 👇", reply_markup=TECLADO_PRINCIPAL)
