"""Pruebas de la interpretación clínica del audiograma (python -m pytest -v)."""
from datetime import datetime

from uyariy.clinica.clasificacion import (Umbral, a_json, avisos_enmascaramiento, desde_json, evaluar,
                                          grado, pta, pta_fletcher)
from uyariy.datos.pacientes import BaseDatos


def audiograma(*valores, enm=False):
    """valores para 500, 1000, 2000, 4000 Hz."""
    return {f: Umbral(v, enm) for f, v in zip((500, 1000, 2000, 4000), valores)}


def test_pta_y_falta_frecuencia():
    assert pta(audiograma(20, 25, 30, 45)) == 30
    assert pta({1000: Umbral(20)}) is None


def test_grados_oms_2021():
    assert grado(19.9)[0] == "Normal"
    assert grado(20)[0] == "Leve"
    assert grado(35)[0] == "Moderada"
    assert grado(50)[0] == "Moderadamente severa"
    assert grado(65)[0] == "Severa"
    assert grado(80)[0] == "Profunda"
    assert grado(95)[0] == "Completa"


def test_normal_pasa():
    r = evaluar(audiograma(10, 10, 15, 15), audiograma(5, 10, 10, 20), edad=30)
    assert r["veredicto"] == "PASA"


def test_leve_adulto_control_pero_nino_referir():
    leve = audiograma(20, 25, 30, 45)
    normal = audiograma(15, 15, 20, 25)
    assert evaluar(leve, normal, edad=40)["veredicto"] == "CONTROL"
    assert evaluar(leve, normal, edad=8)["veredicto"] == "REFERIR"


def test_moderada_referir():
    r = evaluar(audiograma(50, 55, 60, 70), audiograma(40, 40, 45, 55), edad=70)
    assert r["veredicto"] == "REFERIR" and r["grado"]["D"] == "Moderadamente severa"


def test_asimetria_referir():
    r = evaluar(audiograma(30, 30, 30, 30), audiograma(10, 10, 15, 15), edad=50)
    assert r["veredicto"] == "REFERIR"
    assert any("Asimetría" in m for m in r["motivos"])


def test_otorrea_referir():
    r = evaluar(audiograma(10, 10, 10, 10), audiograma(10, 10, 10, 10), edad=30,
                antecedentes=["Supuración (otorrea)"])
    assert r["veredicto"] == "REFERIR"


def test_incompleto():
    assert evaluar({1000: Umbral(20)}, {}, edad=30)["veredicto"] == "INCOMPLETO"


def test_aviso_enmascaramiento():
    d = {1000: Umbral(70)}
    i = {1000: Umbral(10)}
    assert avisos_enmascaramiento(d, i) == ["Enmascarar oído derecho en 1000 Hz"]
    d[1000] = Umbral(70, enmascarado=True)
    assert avisos_enmascaramiento(d, i) == []


def test_json_ida_y_vuelta():
    u = {1000: Umbral(30), 4000: Umbral(90, nr=True)}
    assert desde_json(a_json(u)) == u


def test_guardar_resultados_en_bd(tmp_path):
    bd = BaseDatos(str(tmp_path / "u.db"))
    _, codigo = bd.registrar(dict(ci="1234567", ci_ext="LP", nombres="Ana", ap_paterno="Quispe",
                                  fecha_nac="01/01/1980", sexo="F", consentimiento=True),
                             datetime(2026, 10, 17, 10, 0))
    assert bd.guardar_resultados(codigo, {"veredicto": "PASA"})
    assert bd.leer_resultados(codigo)["veredicto"] == "PASA"
    bd.cerrar()


def test_pta_fletcher_dos_mejores():
    u = audiograma(20, 25, 40, 60)          # 500, 1000, 2000, 4000
    assert pta_fletcher(u) == 22.5          # (20 + 25) / 2
    assert pta_fletcher({1000: Umbral(20)}) is None
    assert evaluar(u, u, edad=30)["fletcher"]["D"] == 22.5