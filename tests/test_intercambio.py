"""Pruebas de exportar / importar datos entre equipos (python -m pytest -v)."""
import json
from datetime import datetime

import pytest

from uyariy.datos import intercambio as X
from uyariy.datos.pacientes import BaseDatos

AHORA = datetime(2026, 10, 18, 10, 0)
RESULTADOS = {"umbrales": {"D": {"500": {"db": 20}, "1000": {"db": 25}, "2000": {"db": 30}, "4000": {"db": 40}},
                           "I": {"500": {"db": 10}, "1000": {"db": 10}, "2000": {"db": 15}, "4000": {"db": 20}}},
              "metodo": "automatico", "verificacion": "ABCD-1234", "observaciones_evaluador": ["Ambiente ruidoso"]}


def paciente(ci="4567891", nombres="Juana Rosa", **cambios):
    d = dict(ci=ci, ci_ext="LP", nombres=nombres, ap_paterno="Mamani", ap_materno="Quispe",
             fecha_nac="12/03/1971", sexo="F", departamento="La Paz", municipio="Achacachi",
             comunidad="Warisata", motivo="Tamizaje comunitario", evaluador="Rubén",
             antecedentes=["Zumbido (acúfeno)"], consentimiento=True)
    d.update(cambios)
    return d


@pytest.fixture
def dos_bd(tmp_path):
    a, b = BaseDatos(str(tmp_path / "tablet.db")), BaseDatos(str(tmp_path / "laptop.db"))
    yield a, b
    a.cerrar()
    b.cerrar()


def test_exportar_e_importar(dos_bd, tmp_path):
    tablet, laptop = dos_bd
    _, codigo = tablet.registrar(paciente(), AHORA)
    tablet.guardar_resultados(codigo, RESULTADOS)
    ruta = str(tmp_path / "respaldo.json")
    assert X.exportar(tablet, ruta, "Tablet 1") == (1, 1)
    r = X.importar(laptop, ruta)
    assert r["pacientes_nuevos"] == 1 and r["evaluaciones_nuevas"] == 1
    assert laptop.leer_resultados(codigo)["verificacion"] == "ABCD-1234"
    assert laptop.historial()[0]["nombres"] == "Juana Rosa"


def test_importar_dos_veces_no_duplica(dos_bd, tmp_path):
    tablet, laptop = dos_bd
    tablet.registrar(paciente(), AHORA)
    ruta = str(tmp_path / "respaldo.json")
    X.exportar(tablet, ruta)
    X.importar(laptop, ruta)
    r = X.importar(laptop, ruta)
    assert r["evaluaciones_nuevas"] == 0 and r["evaluaciones_repetidas"] == 1
    assert laptop.total_pacientes() == 1


def test_mismo_codigo_en_dos_tablets(dos_bd, tmp_path):
    tablet, laptop = dos_bd
    _, c1 = tablet.registrar(paciente(), AHORA)                       # UY-2026-000001 en la tablet
    _, c2 = laptop.registrar(paciente(ci="7777777", nombres="Pedro"), AHORA)   # UY-2026-000001 en la laptop
    assert c1 == c2
    ruta = str(tmp_path / "respaldo.json")
    X.exportar(tablet, ruta)
    r = X.importar(laptop, ruta)
    assert r["codigos_cambiados"] == [(c1, c1 + "-B")]
    assert len(laptop.historial()) == 2


def test_archivo_que_no_es_respaldo(tmp_path, dos_bd):
    ruta = tmp_path / "otro.json"
    ruta.write_text(json.dumps({"hola": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="no es un respaldo"):
        X.importar(dos_bd[1], str(ruta))


def test_csv_para_excel(dos_bd, tmp_path):
    tablet, _ = dos_bd
    _, codigo = tablet.registrar(paciente(), AHORA)
    tablet.guardar_resultados(codigo, RESULTADOS)
    ruta = tmp_path / "datos.csv"
    assert X.exportar_csv(tablet, str(ruta)) == 1
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0].startswith("codigo;fecha;ci;")
    assert "REFERIR" in lineas[1] and "28,8" in lineas[1]        # asimetría 15 dB; PTA 28,75 -> 28,8
