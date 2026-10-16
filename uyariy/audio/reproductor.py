"""
Reproductor de audio con dos "backends":

  * Android  -> android.media.AudioTrack en modo STREAM (vía pyjnius).
                Prefiere PCM FLOAT para que los niveles muy bajos (cerca de
                0 dB HL, ~ -90 dBFS) no se pierdan por cuantización; si la
                tableta no lo admite, usa PCM 16 bits con dither.
  * PC       -> sounddevice (PortAudio) en float32, para desarrollar en VS Code.
  * Nulo     -> si no hay tarjeta de sonido (pruebas automáticas).

Todos reciben un buffer estéreo float32 de forma (n, 2): columna 0 = izquierdo,
columna 1 = derecho.
"""
import os
import threading
import time

import numpy as np

from .generador import FS

EN_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ


class _BackendNulo:
    nombre = "nulo (sin audio)"

    def __init__(self):
        self._hasta = 0.0

    def reproducir(self, buf, fs, bucle=False):
        self._hasta = float("inf") if bucle else time.time() + len(buf) / fs

    def detener(self):
        self._hasta = 0.0

    def sonando(self):
        return time.time() < self._hasta


class _BackendPC:
    nombre = "sounddevice (PC)"

    def __init__(self):
        import sounddevice as sd  # noqa: lanza OSError si falta PortAudio
        self.sd = sd
        self._hasta = 0.0

    def reproducir(self, buf, fs, bucle=False):
        self.sd.stop()
        self.sd.play(buf, fs, loop=bucle)
        self._hasta = float("inf") if bucle else time.time() + len(buf) / fs

    def detener(self):
        self.sd.stop()
        self._hasta = 0.0

    def sonando(self):
        return time.time() < self._hasta


class _BackendAndroid:
    """
    AudioTrack en modo STREAM (compatible con casi todas las tabletas).
    Intenta PCM FLOAT (mejor precisión en niveles bajos) y, si la tableta no lo
    admite, usa PCM 16 bits. Un hilo escribe el audio por bloques; en modo
    continuo repite el buffer hasta que se llame a detener().
    """
    nombre = "AudioTrack (Android)"
    STREAM_MUSIC = 3          # AudioManager.STREAM_MUSIC
    CANAL_ESTEREO = 12        # AudioFormat.CHANNEL_OUT_STEREO
    PCM_16 = 2                # AudioFormat.ENCODING_PCM_16BIT
    PCM_FLOAT = 4             # AudioFormat.ENCODING_PCM_FLOAT
    MODO_STREAM = 1           # AudioTrack.MODE_STREAM
    INICIALIZADO = 1          # AudioTrack.STATE_INITIALIZED
    BLOQUE = 2048             # cuadros por escritura

    def __init__(self):
        from jnius import autoclass
        self.AudioTrack = autoclass("android.media.AudioTrack")
        self._pista = None
        self._hilo = None
        self._parar = threading.Event()
        self._hasta = 0.0
        self._lock = threading.Lock()
        self.formato = None   # se decide en la primera reproducción
        self.error_float = None
        self.ultimo_error = None
        self._fs = 48000

    def _crear_pista(self, fs, codificacion):
        minimo = self.AudioTrack.getMinBufferSize(int(fs), self.CANAL_ESTEREO, codificacion)
        if minimo <= 0:
            raise RuntimeError(f"formato {codificacion} no soportado (getMinBufferSize={minimo})")
        pista = self.AudioTrack(self.STREAM_MUSIC, int(fs), self.CANAL_ESTEREO, codificacion,
                                int(max(minimo * 2, 32768)), self.MODO_STREAM)
        if pista.getState() != self.INICIALIZADO:
            pista.release()
            raise RuntimeError(f"AudioTrack no se inicializó con formato {codificacion}")
        return pista

    def _abrir(self, fs):
        if self.formato is None:
            try:
                pista = self._crear_pista(fs, self.PCM_FLOAT)
                self.formato = "float"
            except Exception:
                pista = self._crear_pista(fs, self.PCM_16)
                self.formato = "pcm16"
            self.nombre = f"AudioTrack {self.formato} (Android)"
            return pista
        return self._crear_pista(fs, self.PCM_FLOAT if self.formato == "float" else self.PCM_16)

    def _escribir_seguro(self, pista, buf, bucle):
        try:
            self._escribir(pista, buf, bucle)
        except Exception as e:          # p. ej. la pista fue liberada al presionar otro botón
            if not self._parar.is_set():
                self.ultimo_error = repr(e)

    def _escribir(self, pista, buf, bucle):
        datos = np.ascontiguousarray(buf, dtype=np.float32)        # (n, 2)
        n = len(datos)
        while not self._parar.is_set():
            for i in range(0, n, self.BLOQUE):
                if self._parar.is_set():
                    break
                bloque = datos[i:i + self.BLOQUE].ravel()          # L,R,L,R...
                if self.formato == "float":
                    try:
                        pista.write(bloque.tolist(), 0, int(bloque.size), 0)   # WRITE_BLOCKING
                        continue
                    except Exception as e:          # la tableta no acepta float[]: pasar a 16 bits
                        self.error_float = repr(e)
                        try:
                            pista.release()
                        except Exception:
                            pass
                        self.formato = "pcm16"
                        self.nombre = "AudioTrack pcm16 (Android)"
                        pista = self._crear_pista(self._fs, self.PCM_16)
                        pista.play()
                        self._pista = pista
                # 16 bits con "dither" triangular (reduce la distorsión en niveles bajos)
                ruido = (np.random.random(bloque.size) - np.random.random(bloque.size)) / 32768.0
                pcm = np.clip(np.round((bloque + ruido) * 32767), -32768, 32767).astype("<i2")
                b = pcm.tobytes()
                pista.write(b, 0, len(b))
            if not bucle:
                break
        try:
            pista.stop()      # en STREAM termina de sonar lo ya escrito
        except Exception:
            pass

    def reproducir(self, buf, fs, bucle=False):
        with self._lock:
            self._cerrar()
            self._fs = int(fs)
            pista = self._abrir(fs)
            pista.play()
            self._parar.clear()
            self._pista = pista
            self._hilo = threading.Thread(target=self._escribir_seguro, args=(pista, buf, bucle), daemon=True)
            self._hilo.start()
            self._hasta = float("inf") if bucle else time.time() + len(buf) / fs

    def _cerrar(self):
        self._parar.set()
        if self._pista is not None:
            try:
                self._pista.pause()
                self._pista.flush()
            except Exception:
                pass
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
        if self._pista is not None:
            try:
                self._pista.release()
            except Exception:
                pass
            self._pista = None

    def detener(self):
        with self._lock:
            self._cerrar()
            self._hasta = 0.0

    def sonando(self):
        return time.time() < self._hasta


def crear_backend():
    if EN_ANDROID:
        return _BackendAndroid()
    try:
        return _BackendPC()
    except Exception:
        return _BackendNulo()


class Reproductor:
    def __init__(self, backend=None, fs=FS):
        self.backend = backend or crear_backend()
        self.fs = fs

    @property
    def nombre_backend(self):
        return self.backend.nombre

    def reproducir(self, buf, bucle=False):
        buf = np.asarray(buf, dtype=np.float32)
        if buf.ndim != 2 or buf.shape[1] != 2:
            raise ValueError("El buffer debe ser estéreo (n, 2)")
        pico = float(np.max(np.abs(buf))) if buf.size else 0.0
        if pico > 1.0:
            raise ValueError(f"Saturación: pico {pico:.3f} > 1.0")
        self.backend.reproducir(buf, self.fs, bucle)

    def detener(self):
        self.backend.detener()

    def sonando(self):
        return self.backend.sonando()