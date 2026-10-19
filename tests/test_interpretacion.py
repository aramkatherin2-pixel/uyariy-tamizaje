"""Pruebas de la interpretación ampliada (python -m pytest -v)."""
from uyariy.clinica import interpretacion as I
from uyariy.clinica.clasificacion import Umbral


def audiograma(**db):
    """audiograma(f500=10, f1000=10, ...) -> {500: Umbral(10), ...}"""
    return {int(k[1:]): Umbral(db=v) for k, v in db.items()}


NORMAL = audiograma(f250=10, f500=10, f1000=10, f2000=10, f3000=10, f4000=10, f6000=10, f8000=10)


def test_ama_normal_es_cero():
    assert I.ama_monoaural(NORMAL) == (0.0, False)


def test_ama_formula():
    u = audiograma(f500=45, f1000=45, f2000=45, f3000=45)      # promedio 45 -> 1,5 x 20 = 30 %
    assert I.ama_monoaural(u) == (30.0, False)


def test_ama_estima_3000():
    u = audiograma(f500=50, f1000=50, f2000=40, f4000=40)      # 3000 estimado = 40; promedio 45
    assert I.ama_monoaural(u) == (30.0, True)


def test_ama_binaural():
    assert I.ama_binaural(0.0, 60.0) == 10.0                   # (5x0 + 60) / 6


def test_muesca_ruido():
    u = audiograma(f500=10, f1000=10, f2000=15, f3000=30, f4000=45, f6000=35, f8000=20)
    assert any("ruido" in p for p in I.configuracion(u))


def test_presbiacusia_solo_en_mayores():
    u = audiograma(f500=15, f1000=20, f2000=30, f4000=50, f8000=65)
    assert any("presbiacusia" in p for p in I.configuracion(u, edad=70))
    assert not any("presbiacusia" in p for p in I.configuracion(u, edad=30))
    assert any("descendente" in p for p in I.configuracion(u, edad=30))


def test_ascendente():
    u = audiograma(f250=45, f500=40, f1000=30, f2000=20, f4000=15)
    assert any("ascendente" in p for p in I.configuracion(u))


def test_normal_sin_patrones():
    assert I.configuracion(NORMAL) == []


def test_interpretar_completo():
    r = I.interpretar(NORMAL, NORMAL, edad=25)
    assert r["evaluacion"]["veredicto"] == "PASA"
    assert r["ama"]["binaural"] == 0.0
    assert "1 año" in r["recomendaciones"][0]


def test_recomendacion_nino_referido():
    rec = I.recomendaciones("REFERIR", edad=9)
    assert any("unidad educativa" in t for t in rec)