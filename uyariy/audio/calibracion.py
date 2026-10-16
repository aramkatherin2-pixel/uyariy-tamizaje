"""
Calibración: convierte dB HL en amplitud digital para UNA combinación concreta
de tableta + audífonos.

Modelo:
    amplitud_pico = 10 ** ((ref_dbfs[f, oído] + dB_HL) / 20)

donde ref_dbfs es el nivel digital (dBFS de pico) que produce 0 dB HL en esa
frecuencia y ese oído. El máximo nivel posible es aquel cuya amplitud llega al
techo digital (MARGEN_DBFS), así que cada frecuencia tiene su propio máximo en dB HL.

Valores iniciales: se suponen audífonos que entregan ~100 dB SPL con un seno a 0 dBFS
y volumen al 100 %, y los RETSPL típicos de auriculares supraaurales (ISO 389-1,
aprox.). Son SOLO un punto de partida: la calibración biológica (o con sonómetro)
los reemplaza.
"""
import json
import math
import os

from .generador import FRECUENCIAS_ESTANDAR

MARGEN_DBFS = -1.0          # techo digital (deja 1 dB de margen contra la saturación)
SPL_A_0DBFS = 100.0         # suposición inicial: dB SPL que produce un seno de pico 1.0

# RETSPL aproximados (dB SPL equivalentes a 0 dB HL), auricular supraaural
RETSPL_INICIAL = {125: 45.0, 250: 27.0, 500: 13.5, 750: 9.0, 1000: 7.5, 1500: 7.5,
                  2000: 9.0, 3000: 11.5, 4000: 12.0, 6000: 16.0, 8000: 15.5}

OIDOS = ("D", "I")          # D = derecho, I = izquierdo


class Calibracion:
    def __init__(self, ref_dbfs=None, nombre="Valores iniciales (sin calibrar)", fecha=None, metodo="inicial"):
        if ref_dbfs is None:
            ref_dbfs = {o: {f: RETSPL_INICIAL[f] - SPL_A_0DBFS for f in FRECUENCIAS_ESTANDAR} for o in OIDOS}
        self.ref_dbfs = {o: {int(f): float(v) for f, v in ref_dbfs[o].items()} for o in OIDOS}
        self.nombre = nombre
        self.fecha = fecha
        self.metodo = metodo

    # ------------------------------------------------------------------ cálculo
    def referencia(self, frecuencia, oido):
        """ref_dbfs interpolado en escala logarítmica de frecuencia."""
        tabla = self.ref_dbfs[oido]
        if frecuencia in tabla:
            return tabla[frecuencia]
        fs = sorted(tabla)
        if frecuencia <= fs[0]:
            return tabla[fs[0]]
        if frecuencia >= fs[-1]:
            return tabla[fs[-1]]
        for a, b in zip(fs, fs[1:]):
            if a <= frecuencia <= b:
                w = (math.log(frecuencia) - math.log(a)) / (math.log(b) - math.log(a))
                return tabla[a] + w * (tabla[b] - tabla[a])

    def maximo_dbhl(self, frecuencia, oido):
        """Nivel máximo en dB HL que se puede producir sin saturar."""
        return MARGEN_DBFS - self.referencia(frecuencia, oido)

    def amplitud(self, frecuencia, dbhl, oido):
        """Amplitud de pico (0..1) para presentar 'dbhl' dB HL. Lanza error si excede el máximo."""
        maximo = self.maximo_dbhl(frecuencia, oido)
        if dbhl > maximo + 1e-9:
            raise NivelFueraDeRango(frecuencia, dbhl, maximo)
        return 10 ** ((self.referencia(frecuencia, oido) + dbhl) / 20)

    # ----------------------------------------------------- calibración biológica
    def aplicar_calibracion_biologica(self, umbrales, fecha=None):
        """
        umbrales = {"D": {1000: [5, 0, 10, ...], ...}, "I": {...}}
        Umbrales medidos (en dB HL con la calibración ACTUAL) en personas jóvenes
        otológicamente normales. Su MEDIANA debería ser 0 dB HL; la diferencia se
        corrige desplazando ref_dbfs: si la mediana sale +8 dB, los tonos eran 8 dB
        más débiles de lo debido, así que ref_dbfs sube 8 dB.
        Devuelve las correcciones aplicadas {oído: {f: dB}}.
        """
        correcciones = {o: {} for o in OIDOS}
        for o, por_f in umbrales.items():
            for f, valores in por_f.items():
                if not valores:
                    continue
                v = sorted(valores)
                m = len(v) // 2
                mediana = v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2
                self.ref_dbfs[o][int(f)] += mediana
                correcciones[o][int(f)] = mediana
        self.metodo = "biologica"
        self.nombre = "Calibración biológica"
        self.fecha = fecha
        return correcciones

    def aplicar_medicion_spl(self, frecuencia, oido, dbfs_presentado, spl_medido, retspl=None):
        """Calibración con sonómetro: se presentó un seno de 'dbfs_presentado' y se midió 'spl_medido'."""
        retspl = RETSPL_INICIAL[frecuencia] if retspl is None else retspl
        self.ref_dbfs[oido][frecuencia] = dbfs_presentado - (spl_medido - retspl)
        self.metodo = "sonometro"

    # ----------------------------------------------------------- persistencia
    def a_dict(self):
        return {"nombre": self.nombre, "fecha": self.fecha, "metodo": self.metodo,
                "ref_dbfs": {o: {str(f): v for f, v in t.items()} for o, t in self.ref_dbfs.items()}}

    @classmethod
    def desde_dict(cls, d):
        return cls(ref_dbfs=d["ref_dbfs"], nombre=d.get("nombre", ""), fecha=d.get("fecha"),
                   metodo=d.get("metodo", "inicial"))

    def guardar(self, ruta):
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(self.a_dict(), fh, indent=2, ensure_ascii=False)

    @classmethod
    def cargar(cls, ruta):
        if not os.path.exists(ruta):
            return cls()
        with open(ruta, encoding="utf-8") as fh:
            return cls.desde_dict(json.load(fh))


class NivelFueraDeRango(ValueError):
    def __init__(self, frecuencia, dbhl, maximo):
        self.frecuencia, self.dbhl, self.maximo = frecuencia, dbhl, maximo
        super().__init__(f"{dbhl:.0f} dB HL a {frecuencia} Hz supera el máximo de {maximo:.0f} dB HL")