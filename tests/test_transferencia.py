"""Pruebas de los archivos de respaldo en la PC (python -m pytest -v)."""
import os
from datetime import datetime

from uyariy.datos import intercambio as X
from uyariy.datos import transferencia as T
from uyariy.datos.pacientes import BaseDatos


def test_nombres_de_archivo():
    ahora = datetime(2026, 10, 21, 9, 5)
    assert T.nombre_archivo("respaldo", ahora) == "Uyariy_respaldo_20261021_0905.json"
    assert T.nombre_archivo("tabla", ahora) == "Uyariy_tabla_20261021_0905.csv"


def test_publicar_en_pc_copia_el_archivo(tmp_path, monkeypatch):
    destino_pc = tmp_path / "Documents" / "Uyariy" / "Respaldos"
    destino_pc.mkdir(parents=True)
    monkeypatch.setattr(T, "carpeta_pc", lambda: str(destino_pc))
    bd = BaseDatos(str(tmp_path / "a.db"))
    ruta = os.path.join(T.carpeta_temporal(str(tmp_path)), T.nombre_archivo("respaldo"))
    X.exportar(bd, ruta, T.nombre_equipo())
    texto, destino = T.publicar(ruta)
    bd.cerrar()
    assert os.path.isfile(destino) and texto == destino
    assert X.leer_respaldo(destino)["equipo"]          # el respaldo lleva el nombre del equipo
