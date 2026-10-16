"""Pruebas del motor de audio (se ejecutan con:  python -m pytest -v)."""
import numpy as np
import pytest

from uyariy.audio import generador as gen
from uyariy.audio.calibracion import Calibracion, NivelFueraDeRango, MARGEN_DBFS
from uyariy.audio.motor import Enmascaramiento, Estimulo, MotorAudio
from uyariy.audio.reproductor import Reproductor, _BackendNulo

FS = gen.FS


def frecuencia_dominante(s):
    esp = np.abs(np.fft.rfft(s * np.hanning(len(s))))
    return np.fft.rfftfreq(len(s), 1 / FS)[np.argmax(esp)]


def motor_sin_audio():
    return MotorAudio(Calibracion(), Reproductor(backend=_BackendNulo()))


# ---------------------------------------------------------------- generador
@pytest.mark.parametrize("f", [250, 1000, 4000, 8000])
def test_tono_puro_frecuencia_y_pico(f):
    s = gen.tono_puro(f, 1.0)
    assert len(s) == FS
    assert abs(frecuencia_dominante(s) - f) <= 1
    medio = s[FS // 4: 3 * FS // 4]          # sin rampas
    # el pico muestreado puede no caer en la cresta (8 kHz = 6 muestras/ciclo): se verifica el RMS
    assert np.sqrt(np.mean(medio ** 2)) == pytest.approx(gen.RMS_SENO, rel=1e-3)


def test_rampas_sin_clic():
    s = gen.tono_puro(1000, 0.5)
    assert abs(s[0]) < 1e-6 and abs(s[-1]) < 1e-3
    r = int(gen.RAMPA_S * FS)
    assert np.max(np.abs(s[: r // 4])) < 0.2          # inicio suave


def test_warble_dentro_de_la_desviacion():
    s = gen.tono_warble(1000, 1.0, desviacion=0.05)
    esp = np.abs(np.fft.rfft(s))
    f = np.fft.rfftfreq(len(s), 1 / FS)
    energia = esp ** 2
    dentro = energia[(f > 940) & (f < 1060)].sum()
    assert dentro / energia.sum() > 0.97


def test_nbn_energia_en_la_banda():
    s = gen.ruido_banda_estrecha(1000, 1.0, ancho_octavas=0.5, semilla=1)
    esp = np.abs(np.fft.rfft(s)) ** 2
    f = np.fft.rfftfreq(len(s), 1 / FS)
    k = 2 ** 0.25
    assert esp[(f >= 1000 / k - 5) & (f <= 1000 * k + 5)].sum() / esp.sum() > 0.97


def test_ruido_rms_igual_a_seno():
    s = gen.ruido_banda_ancha(1.0, semilla=2, rampa=0)
    assert np.sqrt(np.mean(s ** 2)) == pytest.approx(gen.RMS_SENO, rel=0.01)


def test_estereo_canales():
    b = gen.estereo(izquierdo=None, derecho=np.ones(10, dtype=np.float32))
    assert b.shape == (10, 2) and b[:, 0].sum() == 0 and b[:, 1].sum() == 10


def test_pulsado_tiene_silencios():
    s = gen.pulsar(gen.tono_puro(1000, 1.0, rampa=0))
    assert np.max(np.abs(s[int(0.30 * FS):int(0.45 * FS)])) == 0


# --------------------------------------------------------------- calibración
def test_amplitud_sube_10_db():
    c = Calibracion()
    a30, a40 = c.amplitud(1000, 30, "D"), c.amplitud(1000, 40, "D")
    assert 20 * np.log10(a40 / a30) == pytest.approx(10, abs=1e-6)


def test_maximo_no_satura():
    c = Calibracion()
    m = c.maximo_dbhl(1000, "D")
    assert 20 * np.log10(c.amplitud(1000, m, "D")) == pytest.approx(MARGEN_DBFS, abs=1e-6)
    with pytest.raises(NivelFueraDeRango):
        c.amplitud(1000, m + 5, "D")


def test_interpolacion_logaritmica():
    c = Calibracion()
    r = c.referencia(1414, "D")  # entre 1000 y 2000
    assert min(c.ref_dbfs["D"][1000], c.ref_dbfs["D"][2000]) <= r <= max(c.ref_dbfs["D"][1000], c.ref_dbfs["D"][2000])


def test_calibracion_biologica_corrige_mediana():
    c = Calibracion()
    antes = c.ref_dbfs["D"][1000]
    corr = c.aplicar_calibracion_biologica({"D": {1000: [5, 10, 10, 15, 0]}, "I": {}})
    assert corr["D"][1000] == 10
    assert c.ref_dbfs["D"][1000] == pytest.approx(antes + 10)
    assert c.metodo == "biologica"


def test_guardar_y_cargar(tmp_path):
    c = Calibracion()
    c.aplicar_calibracion_biologica({"D": {500: [4, 6]}, "I": {500: [2]}}, fecha="2026-10-16")
    ruta = tmp_path / "cal.json"
    c.guardar(str(ruta))
    c2 = Calibracion.cargar(str(ruta))
    assert c2.ref_dbfs == c.ref_dbfs and c2.fecha == "2026-10-16"


# --------------------------------------------------------------------- motor
def test_motor_oido_derecho_solo_canal_derecho():
    m = motor_sin_audio()
    b = m.construir(Estimulo(1000, 40, "D"))
    assert np.max(np.abs(b[:, 0])) == 0 and np.max(np.abs(b[:, 1])) > 0


def test_motor_binaural():
    b = motor_sin_audio().construir(Estimulo(1000, 40, "DI"))
    assert np.max(np.abs(b[:, 0])) > 0 and np.max(np.abs(b[:, 1])) > 0


def test_motor_enmascaramiento_va_al_oido_contrario():
    m = motor_sin_audio()
    b = m.construir(Estimulo(1000, 40, "D"), Enmascaramiento(True, 50, "nbn"))
    assert np.max(np.abs(b[:, 0])) > 0     # ruido en el izquierdo
    assert abs(frecuencia_dominante(b[:, 1]) - 1000) <= 1


def test_motor_nivel_exacto_en_dbfs():
    m = motor_sin_audio()
    b = m.construir(Estimulo(1000, 50, "D", duracion=1.0))
    esperado = m.calibracion.referencia(1000, "D") + 50
    assert gen.nivel_dbfs_pico(b[:, 1]) == pytest.approx(esperado, abs=0.05)


def test_motor_continuo_sin_rampas_y_periodico():
    m = motor_sin_audio()
    b = m.construir(Estimulo(1000, 40, "D"), continuo=True)
    s = b[:, 1]
    assert len(s) == FS
    # la muestra siguiente a la última sería s[0]: el salto debe ser como el de dos muestras normales
    paso_normal = np.max(np.abs(np.diff(s)))
    assert abs(s[0] - s[-1]) <= paso_normal * 1.01


def test_motor_ruido_que_satura_lanza_error():
    m = motor_sin_audio()
    maxi = m.maximo(1000, "D")
    with pytest.raises(NivelFueraDeRango):
        m.construir(Estimulo(1000, maxi, "D", tipo="banda_ancha"))


def test_reproductor_rechaza_mono():
    r = Reproductor(backend=_BackendNulo())
    with pytest.raises(ValueError):
        r.reproducir(np.zeros(100, dtype=np.float32))