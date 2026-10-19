"""
Seguridad auditiva del paciente (gestión de riesgos, ISO 14971).

El volumen de la tablet queda fijo al 100 % (es la base de la calibración);
la protección se hace dentro de la app:
  - Límite de seguridad: más de 80 dB HL requiere confirmación del evaluador.
  - Por encima de 70 dB HL solo se sube de 5 en 5.
  - Tono continuo: máximo 10 s y prohibido por encima de 80 dB HL.
  - Enmascaramiento: máximo 70 dB EM.
  - Registro de exposición: nivel máximo, tiempo con sonido y dosis estimada (NIOSH).
"""
LIMITE_SEGURO = 80          # dB HL: por encima pide confirmación
NIVEL_AVISO = 65            # desde aquí el número se pone amarillo
NIVEL_PELIGRO = 85          # desde aquí rojo
PASO_ALTO = 70              # por encima, los saltos de +10 se reducen a +5
MAX_CONTINUO_S = 10         # segundos máximos de tono continuo
MAX_ENMASCARAMIENTO = 70    # dB EM
NIVEL_REINICIO = 70         # al cambiar de frecuencia/oído, si el nivel era >= 70 ...
NIVEL_INICIO_SEGURO = 40    # ... vuelve a 40 dB HL

VERDE = (0.18, 0.60, 0.35, 1)
AMARILLO = (0.93, 0.70, 0.12, 1)
ROJO = (0.85, 0.20, 0.22, 1)


def color_nivel(db):
    """Color del número de nivel según el riesgo."""
    if db >= NIVEL_PELIGRO:
        return ROJO
    if db >= NIVEL_AVISO:
        return AMARILLO
    return VERDE


def paso_permitido(actual, delta):
    """Por encima de PASO_ALTO, las subidas se limitan a +5 dB."""
    if delta > 5 and actual + delta > PASO_ALTO:
        return 5
    return delta


def necesita_confirmacion(nuevo, confirmado):
    """True si el nuevo nivel supera el límite seguro y aún no se confirmó."""
    return nuevo > LIMITE_SEGURO and not confirmado


def nivel_al_cambiar(actual):
    """Al cambiar de frecuencia u oído, un nivel alto vuelve a un inicio seguro."""
    return NIVEL_INICIO_SEGURO if actual >= NIVEL_REINICIO else actual


class Exposicion:
    """
    Registra la exposición sonora de una evaluación.
    La dosis usa el criterio NIOSH (85 dB durante 8 h = 100 %, intercambio de 3 dB).
    Se toma el nivel en dB HL como aproximación del nivel en el oído: es una ESTIMACIÓN.
    """

    def __init__(self):
        self.maximo = None
        self.segundos = 0.0
        self.dosis = 0.0            # fracción (1.0 = 100 %)

    def registrar(self, db, segundos):
        if segundos <= 0:
            return
        self.maximo = db if self.maximo is None else max(self.maximo, db)
        self.segundos += segundos
        permitido = 8 * 3600 / (2 ** ((db - 85) / 3))
        self.dosis += segundos / permitido

    def a_dict(self):
        return {"nivel_maximo_dbhl": self.maximo, "segundos_con_sonido": round(self.segundos, 1),
                "dosis_niosh_pct": round(self.dosis * 100, 4)}