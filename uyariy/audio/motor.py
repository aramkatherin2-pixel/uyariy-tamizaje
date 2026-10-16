"""
Motor de audio de Uyariy: une generador + calibración + reproductor.

Equivale a la parte "audio" del panel del AC40:
  - Canal 1 (estímulo): tono puro / warble / NBN / ruido de banda ancha, en dB HL.
  - Canal 2 (enmascaramiento): NBN o banda ancha al oído contrario, en dB EM.
  - Oído: D (derecho), I (izquierdo) o DI (binaural).
  - Presentación: pulso único (duración fija), pulsado, o continuo (bucle).
"""
from dataclasses import dataclass

import numpy as np

from . import generador as gen
from .calibracion import Calibracion, NivelFueraDeRango
from .reproductor import Reproductor

TIPOS_ESTIMULO = ("tono", "warble", "nbn", "banda_ancha")
TIPOS_RUIDO = ("nbn", "banda_ancha")


@dataclass
class Estimulo:
    frecuencia: int = 1000
    dbhl: float = 30.0
    oido: str = "D"                 # "D", "I" o "DI"
    tipo: str = "tono"              # ver TIPOS_ESTIMULO
    duracion: float = 1.0           # segundos
    pulsado: bool = False


@dataclass
class Enmascaramiento:
    activo: bool = False
    dbem: float = 40.0              # nivel efectivo de enmascaramiento
    tipo: str = "nbn"               # "nbn" o "banda_ancha"


class MotorAudio:
    def __init__(self, calibracion=None, reproductor=None):
        self.calibracion = calibracion or Calibracion()
        self.reproductor = reproductor or Reproductor()

    # -------------------------------------------------------------- límites
    def maximo(self, frecuencia, oido="D"):
        oidos = ("D", "I") if oido == "DI" else (oido,)
        return min(self.calibracion.maximo_dbhl(frecuencia, o) for o in oidos)

    # ------------------------------------------------------------- síntesis
    def _senal_mono(self, tipo, frecuencia, duracion, rampa=gen.RAMPA_S):
        if tipo == "tono":
            return gen.tono_puro(frecuencia, duracion, rampa=rampa)
        if tipo == "warble":
            return gen.tono_warble(frecuencia, duracion, rampa=rampa)
        if tipo == "nbn":
            return gen.ruido_banda_estrecha(frecuencia, duracion, rampa=rampa)
        if tipo == "banda_ancha":
            return gen.ruido_banda_ancha(duracion, rampa=rampa)
        raise ValueError(f"Tipo de estímulo desconocido: {tipo}")

    def construir(self, est: Estimulo, enm: Enmascaramiento = None, continuo=False):
        """
        Devuelve el buffer estéreo listo para reproducir (n, 2).
        continuo=True: 1 s SIN rampas, periódico (frecuencias enteras, ruido circular por FFT),
        para repetirse en bucle sin cortes.
        """
        dur, rampa = (1.0, 0.0) if continuo else (est.duracion, gen.RAMPA_S)
        base = self._senal_mono(est.tipo, est.frecuencia, dur, rampa)
        if est.pulsado:
            base = gen.pulsar(base)
        izq = der = None
        if est.oido in ("I", "DI"):
            izq = base * self.calibracion.amplitud(est.frecuencia, est.dbhl, "I")
        if est.oido in ("D", "DI"):
            der = base * self.calibracion.amplitud(est.frecuencia, est.dbhl, "D")
        if enm is not None and enm.activo and est.oido in ("D", "I"):
            contrario = "I" if est.oido == "D" else "D"
            ruido = self._senal_mono(enm.tipo, est.frecuencia, dur, rampa)
            ruido = ruido * self.calibracion.amplitud(est.frecuencia, enm.dbem, contrario)
            if contrario == "I":
                izq = ruido
            else:
                der = ruido
        buf = gen.estereo(izq, der)
        # los ruidos tienen factor de cresta alto: pueden saturar antes que el tono
        canal = {"I": 0, "D": 1}
        oidos_est = ("D", "I") if est.oido == "DI" else (est.oido,)
        for o in ("D", "I"):
            pico = float(np.max(np.abs(buf[:, canal[o]])))
            if pico > 1.0:
                exceso = 20 * np.log10(pico)
                nivel = est.dbhl if o in oidos_est else enm.dbem
                raise NivelFueraDeRango(est.frecuencia, nivel, nivel - exceso)
        return buf

    # --------------------------------------------------------- reproducción
    def presentar(self, est: Estimulo, enm: Enmascaramiento = None, continuo=False):
        """Reproduce el estímulo. Si continuo=True queda en bucle hasta detener()."""
        buf = self.construir(est, enm, continuo)
        self.reproductor.reproducir(buf, bucle=continuo)
        return buf

    def detener(self):
        self.reproductor.detener()

    def sonando(self):
        return self.reproductor.sonando()


__all__ = ["MotorAudio", "Estimulo", "Enmascaramiento", "NivelFueraDeRango", "TIPOS_ESTIMULO", "TIPOS_RUIDO"]