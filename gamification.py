from db.database import fetchone, fetchall

def get_racha(uid: int) -> int:
    from datetime import date, timedelta
    rows = fetchall(
        "SELECT fecha FROM sesiones WHERE user_id=? AND completada=1 ORDER BY fecha DESC LIMIT 30",
        (uid,)
    )
    if not rows: return 0
    racha = 0
    dia = date.today()
    fechas = {r["fecha"] for r in rows}
    while str(dia) in fechas or str(dia - timedelta(days=1)) in fechas:
        if str(dia) in fechas:
            racha += 1
        dia -= timedelta(days=1)
        if racha > 30: break
    return racha
