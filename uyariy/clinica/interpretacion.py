"""
Interpretación ampliada para el informe (Paso 7).

- Porcentaje de discapacidad auditiva AMA / AAO-1979 (500, 1000, 2000, 3000 Hz):
    monoaural = 1,5 x (promedio - 25), entre 0 y 100 %
    binaural  = (5 x oído mejor + oído peor) / 6
  Si falta 3000 Hz (protocolo rápido) se estima como el promedio de 2000 y 4000 Hz.
- Configuración (forma) del audiograma: muesca en 4 kHz, descendente, ascendente, plana.
  Son DESCRIPCIONES "compatibles con", no diagnósticos.
- Recomendaciones según el veredicto de tamizaje.
"""
from . import clasificacion as C

FRECUENCIAS_AMA = (500, 1000, 2000, 3000)
AVISO_TAMIZAJE = ("Resultado de TAMIZAJE: no reemplaza una evaluación audiológica diagnóstica "
                  "(vía ósea, logoaudiometría, timpanometría).")


def _db(umb, f):
    return umb[f].db if f in umb else None


def ama_monoaural(umb):
    """Devuelve (porcentaje, estimado). None si faltan frecuencias."""
    valores, estimado = [], False
    for f in FRECUENCIAS_AMA:
        v = _db(umb, f)
        if v is None and f == 3000 and _db(umb, 2000) is not None and _db(umb, 4000) is not None:
            v, estimado = (_db(umb, 2000) + _db(umb, 4000)) / 2, True
        if v is None:
            return None, False
        valores.append(v)
    promedio = sum(valores) / 4
    return round(max(0.0, min(100.0, 1.5 * (promedio - 25))), 1), estimado


def ama_binaural(pct_d, pct_i):
    if pct_d is None or pct_i is None:
        return None
    mejor, peor = min(pct_d, pct_i), max(pct_d, pct_i)
    return round((5 * mejor + peor) / 6, 1)


def configuracion(umb, edad=None):
    """Lista de patrones descriptivos del audiograma de un oído."""
    patrones = []
    d = {f: _db(umb, f) for f in (250, 500, 1000, 2000, 3000, 4000, 6000, 8000)}

    # Muesca 3-6 kHz con recuperación en 8 kHz (Coles et al., 2000): compatible con ruido
    graves = [v for v in (d[1000], d[2000]) if v is not None]
    muesca = [v for v in (d[3000], d[4000], d[6000]) if v is not None]
    if graves and muesca and d[8000] is not None:
        fondo = max(muesca)
        if fondo - min(graves) >= 10 and fondo - d[8000] >= 10 and fondo >= 25:
            patrones.append("Muesca en 3-6 kHz con recuperación en 8 kHz (compatible con exposición a ruido)")

    # Descendente: agudos peores que graves
    bajos = [v for v in (d[500], d[1000]) if v is not None]
    altos = [v for v in (d[4000], d[8000]) if v is not None]
    if bajos and altos and not any("Muesca" in p for p in patrones):
        if sum(altos) / len(altos) - sum(bajos) / len(bajos) >= 20:
            texto = "Configuración descendente (peor en agudos)"
            if edad is not None and edad >= 60:
                texto += ", compatible con presbiacusia"
            patrones.append(texto)

    # Ascendente: graves peores que agudos
    gr = [v for v in (d[250], d[500]) if v is not None]
    ag = [v for v in (d[2000], d[4000]) if v is not None]
    if gr and ag and sum(gr) / len(gr) - sum(ag) / len(ag) >= 15:
        patrones.append("Configuración ascendente (peor en graves): descartar componente conductivo")

    # Plana: pérdida pareja en las frecuencias del PTA
    pta = C.pta(umb)
    if not patrones and pta is not None and pta >= 20:
        vals = [d[f] for f in C.FRECUENCIAS_PTA]
        if max(vals) - min(vals) <= 15:
            patrones.append("Configuración plana")

    if any(u.nr for u in umb.values()):
        patrones.append("Sin respuesta en alguna frecuencia al nivel máximo de la prueba")
    return patrones


def recomendaciones(veredicto, edad=None, patrones=()):
    rec = []
    nino = edad is not None and edad < 18
    if veredicto == "PASA":
        rec.append("Audición dentro de lo normal. Repetir el tamizaje en 1 año.")
    elif veredicto == "CONTROL":
        rec.append("Repetir el tamizaje en 6 meses. Revisar los oídos (otoscopia) en el centro de salud.")
    elif veredicto == "REFERIR":
        rec.append("Referir a otorrinolaringología / audiología para una evaluación auditiva completa.")
        if nino:
            rec.append("Informar a los padres y a la unidad educativa: sentar al estudiante en las primeras filas.")
    else:
        rec.append("Prueba incompleta: completar 500, 1000, 2000 y 4000 Hz en ambos oídos.")
    todos = " ".join(patrones)
    if "ruido" in todos:
        rec.append("Usar protección auditiva (tapones u orejeras) en ambientes ruidosos.")
    if "conductivo" in todos:
        rec.append("Revisar cerumen u otitis media antes de repetir la prueba.")
    rec.append("Evitar música fuerte con audífonos (regla 60/60: máx. 60 % de volumen, 60 minutos).")
    return rec


def interpretar(umb_d, umb_i, edad=None, antecedentes=()):
    """Todo lo que necesita la pantalla de resultados y el informe PDF."""
    ev = C.evaluar(umb_d, umb_i, edad, antecedentes)
    pat = {"D": configuracion(umb_d, edad), "I": configuracion(umb_i, edad)}
    pd, est_d = ama_monoaural(umb_d)
    pi, est_i = ama_monoaural(umb_i)
    return {
        "evaluacion": ev,
        "patrones": pat,
        "ama": {"D": pd, "I": pi, "binaural": ama_binaural(pd, pi), "estimado": est_d or est_i},
        "recomendaciones": recomendaciones(ev["veredicto"], edad, pat["D"] + pat["I"]),
        "aviso": AVISO_TAMIZAJE,
    }