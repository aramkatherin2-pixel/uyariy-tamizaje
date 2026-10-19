"""Pruebas del método automático Hughson-Westlake con un paciente simulado."""
import random

import pytest

from uyariy.clinica.hughson import HughsonWestlake, fiabilidad


def simular(umbral_real, maximo=90, error=0.0, semilla=1):
    """Paciente que oye todo lo que esté en su umbral o por encima (con un % de errores)."""
    azar = random.Random(semilla)
    hw = HughsonWestlake(maximo)
    while not hw.terminado:
        oye = hw.nivel >= umbral_real
        if azar.random() < error:
            oye = not oye
        hw.responder(oye)
    return hw


@pytest.mark.parametrize("real", [-10, 0, 5, 20, 35, 50, 65, 80])
def test_encuentra_el_umbral(real):
    hw = simular(real)
    assert hw.umbral == real and not hw.sin_respuesta


def test_umbral_no_multiplo_de_5_redondea_hacia_arriba():
    assert simular(22).umbral == 25


def test_sin_respuesta_si_no_oye_al_maximo():
    hw = simular(200, maximo=90)
    assert hw.sin_respuesta and hw.umbral is None


def test_patron_baja_10_sube_5():
    hw = HughsonWestlake(90)
    hw.responder(True)          # 30 oye -> 20
    assert hw.nivel == 20
    hw.responder(False)         # 20 no -> 25
    assert hw.nivel == 25
    hw.responder(True)          # 25 oye (ascendente) -> 15
    assert hw.nivel == 15


def test_paciente_con_errores_termina_cerca():
    hw = simular(40, error=0.1, semilla=7)
    assert hw.terminado and abs(hw.umbral - 40) <= 10


def test_fiabilidad():
    assert fiabilidad(8, 0, 1, [(30, 35)])[0]
    ok, msj = fiabilidad(8, 4, 0)
    assert not ok and "silencio" in msj[0]
    assert not fiabilidad(8, 0, 0, [(20, 45)])[0]