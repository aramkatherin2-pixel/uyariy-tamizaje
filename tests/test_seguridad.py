"""Pruebas de la seguridad auditiva (python -m pytest -v)."""
from uyariy.clinica import seguridad as S


def test_colores():
    assert S.color_nivel(30) == S.VERDE
    assert S.color_nivel(70) == S.AMARILLO
    assert S.color_nivel(90) == S.ROJO


def test_subida_limitada_por_encima_de_70():
    assert S.paso_permitido(50, 10) == 10       # 60: permitido
    assert S.paso_permitido(65, 10) == 5        # 75 > 70: solo +5
    assert S.paso_permitido(75, -10) == -10     # bajar siempre se permite


def test_confirmacion_sobre_80():
    assert not S.necesita_confirmacion(80, False)
    assert S.necesita_confirmacion(85, False)
    assert not S.necesita_confirmacion(85, True)


def test_inicio_seguro_al_cambiar():
    assert S.nivel_al_cambiar(75) == 40
    assert S.nivel_al_cambiar(35) == 35


def test_dosis_niosh():
    e = S.Exposicion()
    e.registrar(85, 8 * 3600)                  # 8 h a 85 dB = 100 %
    assert abs(e.dosis - 1.0) < 1e-9
    e2 = S.Exposicion()
    e2.registrar(90, 1.0)                      # un pulso de 1 s a 90 dB: dosis ínfima
    assert e2.dosis < 0.001 and e2.maximo == 90      # 0,011 %