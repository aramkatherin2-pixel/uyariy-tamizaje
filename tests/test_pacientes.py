"""Pruebas de la base de datos de pacientes (python -m pytest -v)."""
from datetime import date, datetime

import pytest

from uyariy.datos.pacientes import BaseDatos, calcular_edad, leer_fecha, validar

HOY = datetime(2026, 10, 17, 10, 0)


def paciente(**cambios):
    d = dict(ci="4567891", ci_ext="LP", nombres="Juana Rosa", ap_paterno="Mamani",
             ap_materno="Quispe", fecha_nac="12/03/1971", sexo="F", telefono="71234567",
             idioma="Aymara", departamento="La Paz", municipio="Achacachi", comunidad="Warisata",
             motivo="Tamizaje comunitario", evaluador="Rubén", antecedentes=["Zumbido (acúfeno)"],
             oido_dificultad="Derecho", consentimiento=True)
    d.update(cambios)
    return d


@pytest.fixture
def bd(tmp_path):
    b = BaseDatos(str(tmp_path / "uyariy.db"))
    yield b
    b.cerrar()


def test_edad():
    assert calcular_edad(date(1971, 3, 12), date(2026, 10, 17)) == 55
    assert calcular_edad(date(2000, 12, 31), date(2026, 10, 17)) == 25


def test_leer_fecha_invalida():
    with pytest.raises(ValueError):
        leer_fecha("31/02/2000")


def test_validar_ok():
    assert validar(paciente(), HOY.date()) == []


@pytest.mark.parametrize("cambio, texto", [
    ({"nombres": ""}, "nombre"),
    ({"ci": "12a"}, "C.I."),
    ({"fecha_nac": "1971-03-12"}, "dd/mm/aaaa"),
    ({"fecha_nac": "01/01/2030"}, "futuro"),
    ({"sexo": ""}, "sexo"),
    ({"consentimiento": False}, "consentimiento"),
    ({"fecha_nac": "01/01/2015", "tutor": ""}, "tutor"),
])
def test_validar_errores(cambio, texto):
    errores = validar(paciente(**cambio), HOY.date())
    assert any(texto in e for e in errores)


def test_registrar_y_buscar(bd):
    pid, codigo = bd.registrar(paciente(), HOY)
    assert codigo == "UY-2026-000001"
    p = bd.buscar_ci("4567891")
    assert p["id"] == pid and p["comunidad"] == "Warisata"


def test_mismo_ci_no_duplica_paciente(bd):
    bd.registrar(paciente(), HOY)
    pid2, codigo2 = bd.registrar(paciente(telefono="76543210"), HOY)
    assert bd.total_pacientes() == 1
    assert codigo2 == "UY-2026-000002"
    assert bd.buscar_ci("4567891")["telefono"] == "76543210"


def test_registro_invalido_no_guarda(bd):
    with pytest.raises(ValueError):
        bd.registrar(paciente(consentimiento=False), HOY)
    assert bd.total_pacientes() == 0


def test_historial_filtra(bd):
    bd.registrar(paciente(), HOY)
    bd.registrar(paciente(ci="1234567", nombres="Pedro", ap_paterno="Condori", sexo="M"), HOY)
    assert len(bd.historial()) == 2
    res = bd.historial("Condori")
    assert len(res) == 1 and res[0]["nombres"] == "Pedro"
    assert res[0]["edad"] == 55


def test_datos_persisten(tmp_path):
    ruta = str(tmp_path / "x.db")
    b = BaseDatos(ruta)
    b.registrar(paciente(), HOY)
    b.cerrar()
    b2 = BaseDatos(ruta)
    assert b2.total_pacientes() == 1
    b2.cerrar()