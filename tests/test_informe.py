"""Pruebas del informe PDF (python -m pytest -v)."""
import zlib

from uyariy.clinica.clasificacion import Umbral
from uyariy.informe.pdf import DocumentoPDF, ancho_texto, partir_lineas
from uyariy.informe.reporte import codigo_verificacion, generar_informe

PACIENTE = {"nombres": "Lucio", "ap_paterno": "Ara", "ap_materno": "Arias", "ci": "7055172", "ci_ext": "LP",
            "edad": 48, "sexo": "M", "comunidad": "Achacachi", "departamento": "La Paz",
            "motivo": "Laboral / exposición a ruido", "establecimiento": "C.S. Achacachi", "evaluador": "Rubén"}
UMB = {"D": {f: Umbral(db=v) for f, v in {500: 10, 1000: 15, 2000: 20, 4000: 45, 8000: 25}.items()},
       "I": {f: Umbral(db=v) for f, v in {500: 10, 1000: 10, 2000: 15, 4000: 20, 8000: 15}.items()}}


def test_ancho_y_cortes():
    assert ancho_texto("ab", 10) > ancho_texto("a", 10)
    lineas = partir_lineas("uno dos tres cuatro cinco seis siete ocho", 10, 60)
    assert len(lineas) > 1 and all(ancho_texto(l, 10) <= 60 for l in lineas)


def test_pdf_valido():
    d = DocumentoPDF("prueba")
    d.texto(50, 50, "Audición: niño, oído (ñ)", 12)
    datos = d.a_bytes()
    assert datos.startswith(b"%PDF-1.4") and datos.rstrip().endswith(b"%%EOF")
    inicio = datos.index(b"stream\n") + 7
    fin = datos.index(b"\nendstream")
    contenido = zlib.decompress(datos[inicio:fin])
    assert "Audición: niño, oído \\(ñ\\)".encode("cp1252") in contenido


def test_codigo_verificacion_cambia_con_los_datos():
    a = codigo_verificacion("UY-1", UMB, "2026-10-18T22:00")
    b = codigo_verificacion("UY-1", {"D": {**UMB["D"], 500: Umbral(db=40)}, "I": UMB["I"]}, "2026-10-18T22:00")
    assert a != b and len(a) == 9 and a[4] == "-"
    assert a == codigo_verificacion("UY-1", UMB, "2026-10-18T22:00")      # mismo dato = mismo código


def test_generar_informe(tmp_path):
    ruta, verif = generar_informe(str(tmp_path / "informe.pdf"), PACIENTE, "UY-2026-000009", UMB,
                                  {"metodo": "manual", "fecha": "2026-10-18T22:00"},
                                  ["Ambiente ruidoso"], "Trabaja en carpintería sin protección")
    datos = open(ruta, "rb").read()
    assert datos.startswith(b"%PDF") and len(datos) > 2000
    assert len(verif) == 9