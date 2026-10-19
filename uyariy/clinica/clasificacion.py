"""
Interpretación del audiograma de tamizaje (vía aérea).

- Promedio tonal (PTA) de 500, 1000, 2000 y 4000 Hz.
- Grado de pérdida según la OMS (World Report on Hearing, 2021).
- Veredicto de tamizaje: PASA / CONTROL / REFERIR, con sus motivos.
- Avisos de enmascaramiento (atenuación interaural de auriculares supraaurales ~40 dB).

Umbrales: diccionario {frecuencia: Umbral}. Un umbral "sin respuesta" (nr) significa
que el paciente no respondió al nivel máximo: se trata como pérdida en ese nivel.
"""
from dataclasses import asdict, dataclass

FRECUENCIAS_PTA = (500, 1000, 2000, 4000)
FRECUENCIAS_FLETCHER = (500, 1000, 2000)
ATENUACION_INTERAURAL = 40          # dB, auriculares supraaurales
ASIMETRIA_REFERIR = 15              # dB de diferencia entre PTA de ambos oídos

# (límite superior exclusivo, nombre, color RGBA)
GRADOS_OMS = [
    (20, "Normal", (0.18, 0.60, 0.35, 1)),
    (35, "Leve", (0.85, 0.70, 0.10, 1)),
    (50, "Moderada", (0.93, 0.55, 0.13, 1)),
    (65, "Moderadamente severa", (0.90, 0.40, 0.12, 1)),
    (80, "Severa", (0.79, 0.21, 0.23, 1)),
    (95, "Profunda", (0.60, 0.10, 0.15, 1)),
    (999, "Completa", (0.25, 0.25, 0.28, 1)),
]

SINTOMAS_REFERIR = ("Supuración (otorrea)", "Dolor de oído (otalgia)")
NOMBRE_OIDO = {"D": "derecho", "I": "izquierdo"}


@dataclass
class Umbral:
    db: float
    enmascarado: bool = False
    nr: bool = False                # sin respuesta al nivel máximo


def pta(umbrales):
    """Promedio de 500-1000-2000-4000 Hz. None si falta alguna de esas frecuencias."""
    if not all(f in umbrales for f in FRECUENCIAS_PTA):
        return None
    return round(sum(umbrales[f].db for f in FRECUENCIAS_PTA) / len(FRECUENCIAS_PTA), 1)


def pta_fletcher(umbrales):
    """Promedio de Fletcher: las 2 mejores (más bajas) de 500, 1000 y 2000 Hz (AC40, pág. 40)."""
    if not all(f in umbrales for f in FRECUENCIAS_FLETCHER):
        return None
    mejores = sorted(umbrales[f].db for f in FRECUENCIAS_FLETCHER)[:2]
    return round(sum(mejores) / 2, 1)


def grado(valor):
    """Devuelve (nombre, color) del grado OMS para un PTA."""
    if valor is None:
        return "Incompleto", (0.45, 0.48, 0.52, 1)
    for limite, nombre, color in GRADOS_OMS:
        if valor < limite:
            return nombre, color
    return GRADOS_OMS[-1][1], GRADOS_OMS[-1][2]


def avisos_enmascaramiento(umb_d, umb_i):
    """Frecuencias donde la diferencia entre oídos supera la atenuación interaural
    y el oído peor se midió SIN enmascarar (posible respuesta del oído contrario)."""
    avisos = []
    for f in sorted(set(umb_d) & set(umb_i)):
        d, i = umb_d[f], umb_i[f]
        if d.db - i.db >= ATENUACION_INTERAURAL and not d.enmascarado:
            avisos.append(f"Enmascarar oído derecho en {f} Hz")
        elif i.db - d.db >= ATENUACION_INTERAURAL and not i.enmascarado:
            avisos.append(f"Enmascarar oído izquierdo en {f} Hz")
    return avisos


def evaluar(umb_d, umb_i, edad=None, antecedentes=()):
    """Interpreta los dos audiogramas. Devuelve un diccionario con el resultado."""
    p = {"D": pta(umb_d), "I": pta(umb_i)}
    g = {o: grado(v)[0] for o, v in p.items()}
    fl = {"D": pta_fletcher(umb_d), "I": pta_fletcher(umb_i)}
    motivos, veredicto = [], "PASA"
    nino = edad is not None and edad < 18

    if p["D"] is None or p["I"] is None:
        faltan = [NOMBRE_OIDO[o] for o in ("D", "I") if p[o] is None]
        return {"pta": p, "fletcher": fl, "grado": g, "veredicto": "INCOMPLETO",
                "motivos": ["Faltan 500, 1000, 2000 o 4000 Hz en oído " + " y ".join(faltan)],
                "avisos": avisos_enmascaramiento(umb_d, umb_i)}

    for o in ("D", "I"):
        if p[o] >= 35:
            motivos.append(f"Pérdida {g[o].lower()} en oído {NOMBRE_OIDO[o]}")
        elif p[o] >= 20 and nino:
            motivos.append(f"Pérdida leve en oído {NOMBRE_OIDO[o]} (menor de edad)")
    if abs(p["D"] - p["I"]) >= ASIMETRIA_REFERIR:
        motivos.append(f"Asimetría entre oídos de {abs(p['D'] - p['I']):.0f} dB")
    sintomas = [s for s in SINTOMAS_REFERIR if s in (antecedentes or ())]
    if sintomas:
        motivos.append("Síntomas de oído: " + ", ".join(s.split(" (")[0].lower() for s in sintomas))

    if motivos:
        veredicto = "REFERIR"
    elif max(p.values()) >= 20:
        veredicto = "CONTROL"
        motivos.append("Pérdida leve: control en 6 meses y medidas de protección auditiva")
    else:
        motivos.append("Audición normal: control en 1 año")

    return {"pta": p, "fletcher": fl, "grado": g, "veredicto": veredicto, "motivos": motivos,
            "avisos": avisos_enmascaramiento(umb_d, umb_i)}


def a_json(umbrales):
    """{1000: Umbral} -> {"1000": {...}} para guardar en la base de datos."""
    return {str(f): asdict(u) for f, u in sorted(umbrales.items())}


def desde_json(d):
    return {int(f): Umbral(**u) for f, u in (d or {}).items()}