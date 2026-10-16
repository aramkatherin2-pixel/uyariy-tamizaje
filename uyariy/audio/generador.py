"""
Generador de estímulos audiométricos (NumPy).

Todas las señales se generan en punto flotante (float32, rango -1..1) a 48 kHz.
Las funciones devuelven señales MONO normalizadas a amplitud de pico 1.0 (tonos)
o a un valor eficaz (RMS) equivalente al de un seno de pico 1.0 (ruidos), de modo que
la calibración (dB HL -> amplitud) se aplica después con un solo factor.

Referencias:
  - IEC 60645-1: rampas de subida/bajada 20-50 ms; tono warble con modulación
    sinusoidal de 4-20 Hz y desviación de ±5 % (típico).
  - Ruido de banda estrecha (NBN) para enmascaramiento: ancho de 1/3 a 1/2 octava
    centrado en la frecuencia de prueba.
"""
import numpy as np

FS = 48000                      # frecuencia de muestreo (Hz)
RAMPA_S = 0.025                 # 25 ms de rampa (dentro de 20-50 ms, IEC 60645-1)
RMS_SENO = 1 / np.sqrt(2)       # RMS de un seno de pico 1.0

FRECUENCIAS_ESTANDAR = [125, 250, 500, 750, 1000, 1500, 2000, 3000, 4000, 6000, 8000]


def _n(duracion, fs=FS):
    return max(1, int(round(duracion * fs)))


def envolvente(n, fs=FS, rampa=RAMPA_S):
    """Envolvente con rampas coseno-cuadrado al inicio y al final (evita 'clics')."""
    env = np.ones(n, dtype=np.float32)
    r = min(int(rampa * fs), n // 2)
    if r > 0:
        t = np.linspace(0, np.pi / 2, r, dtype=np.float32)
        subida = np.sin(t) ** 2
        env[:r] = subida
        env[-r:] = subida[::-1]
    return env


def tono_puro(frecuencia, duracion=1.0, fs=FS, rampa=RAMPA_S):
    """Tono sinusoidal de pico 1.0 con rampas."""
    n = _n(duracion, fs)
    t = np.arange(n, dtype=np.float64) / fs
    s = np.sin(2 * np.pi * frecuencia * t).astype(np.float32)
    return s * envolvente(n, fs, rampa)


def tono_warble(frecuencia, duracion=1.0, fs=FS, desviacion=0.05, f_mod=5.0, rampa=RAMPA_S):
    """Tono de frecuencia modulada (warble): f(t) = fc·(1 + d·sin(2π·fm·t))."""
    n = _n(duracion, fs)
    t = np.arange(n, dtype=np.float64) / fs
    # fase = integral de 2π f(t) dt
    fase = 2 * np.pi * frecuencia * (t - desviacion * np.cos(2 * np.pi * f_mod * t) / (2 * np.pi * f_mod))
    s = np.sin(fase).astype(np.float32)
    return s * envolvente(n, fs, rampa)


def pulsar(senal, encendido=0.25, apagado=0.25, fs=FS, rampa=0.020):
    """Convierte una señal continua en pulsos (modo 'pulsado' del audiómetro)."""
    periodo = _n(encendido + apagado, fs)
    on = _n(encendido, fs)
    pulso = np.zeros(periodo, dtype=np.float32)
    pulso[:on] = envolvente(on, fs, rampa)
    reps = int(np.ceil(len(senal) / periodo))
    mascara = np.tile(pulso, reps)[: len(senal)]
    return senal * mascara


def _ruido_filtrado(f_baja, f_alta, duracion, fs, semilla, rampa=RAMPA_S):
    """Ruido blanco filtrado en frecuencia (FFT) entre f_baja y f_alta, normalizado a RMS de seno."""
    n = _n(duracion, fs)
    rng = np.random.default_rng(semilla)
    espectro = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / fs)
    espectro[(f < f_baja) | (f > f_alta)] = 0
    s = np.fft.irfft(espectro, n)
    rms = np.sqrt(np.mean(s ** 2))
    if rms > 0:
        s = s / rms * RMS_SENO
    return (s.astype(np.float32)) * envolvente(n, fs, rampa)


def ruido_banda_estrecha(frecuencia, duracion=1.0, fs=FS, ancho_octavas=0.5, semilla=None, rampa=RAMPA_S):
    """NBN: ruido de banda estrecha centrado en 'frecuencia' (ancho en octavas, 1/3 a 1/2)."""
    k = 2 ** (ancho_octavas / 2)
    return _ruido_filtrado(frecuencia / k, frecuencia * k, duracion, fs, semilla, rampa)


def ruido_banda_ancha(duracion=1.0, fs=FS, f_baja=125, f_alta=10000, semilla=None, rampa=RAMPA_S):
    """WN: ruido de banda ancha (blanco limitado a la banda audiométrica)."""
    return _ruido_filtrado(f_baja, f_alta, duracion, fs, semilla, rampa)


def silencio(duracion, fs=FS):
    return np.zeros(_n(duracion, fs), dtype=np.float32)


def estereo(izquierdo=None, derecho=None):
    """Combina dos señales mono en un buffer estéreo (n, 2) [canal 0 = izquierdo, 1 = derecho]."""
    if izquierdo is None and derecho is None:
        raise ValueError("Se necesita al menos un canal")
    n = max(len(x) for x in (izquierdo, derecho) if x is not None)
    buf = np.zeros((n, 2), dtype=np.float32)
    if izquierdo is not None:
        buf[: len(izquierdo), 0] = izquierdo
    if derecho is not None:
        buf[: len(derecho), 1] = derecho
    return buf


def nivel_dbfs_pico(senal):
    p = float(np.max(np.abs(senal)))
    return -np.inf if p == 0 else 20 * np.log10(p)