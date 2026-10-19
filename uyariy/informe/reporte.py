"""
Informe de tamizaje auditivo en PDF (una hoja A4).

Contenido: datos del paciente, audiogramas de ambos oídos (símbolos ASHA), tabla de umbrales,
veredicto, PTA / grado OMS / % AMA, interpretación AUTOMÁTICA, observaciones del EVALUADOR,
recomendaciones, firma y sello, y un código de verificación que detecta cambios en los datos.
"""
import hashlib
import json
import math
from datetime import datetime

from .. import __version__
from ..clinica import clasificacion as C
from ..clinica import interpretacion as I
from .pdf import CM, DocumentoPDF

M = 1.5 * CM                                   # margen
GRIS = (0.40, 0.44, 0.48)
CLARO = (0.85, 0.87, 0.89)
ROJO = (0.80, 0.16, 0.18)
AZUL = (0.15, 0.36, 0.80)
COLOR_OIDO = {"D": ROJO, "I": AZUL}
COLOR_VEREDICTO = {"PASA": (0.18, 0.60, 0.35), "CONTROL": (0.85, 0.62, 0.10), "REFERIR": (0.79, 0.21, 0.23),
                   "INCOMPLETO": (0.45, 0.48, 0.52)}
BANANA = {125: (5, 30), 250: (12, 45), 500: (20, 57), 1000: (22, 62), 2000: (18, 58),
          4000: (15, 50), 8000: (10, 43)}
FRECS_TABLA = (250, 500, 1000, 2000, 3000, 4000, 6000, 8000)
DB_MIN, DB_MAX, F_MIN, F_MAX = -10, 120, 125, 8000
LIMITE_PAGINA = 800


def codigo_verificacion(codigo, umbrales, fecha):
    """Huella corta de los datos del examen: si alguien cambia un valor, el código ya no coincide."""
    datos = json.dumps({"c": codigo, "f": fecha, "u": {o: C.a_json(u) for o, u in umbrales.items()}},
                       sort_keys=True)
    h = hashlib.sha256(datos.encode()).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}"


def _valor(u):
    if u is None:
        return "-"
    return f">{u.db:.0f}" if u.nr else f"{u.db:.0f}"


class Informe:
    def __init__(self, paciente, codigo, umbrales, extra=None, observaciones=(), nota=""):
        self.p = paciente or {}
        self.codigo = codigo
        self.umb = {"D": umbrales.get("D", {}), "I": umbrales.get("I", {})}
        self.extra = extra or {}
        self.observaciones = list(observaciones)
        self.nota = (nota or "").strip()
        self.fecha = self.extra.get("fecha") or datetime.now().isoformat(timespec="minutes")
        self.r = I.interpretar(self.umb["D"], self.umb["I"], self.p.get("edad"), self.p.get("antecedentes", []))
        self.verif = codigo_verificacion(codigo, self.umb, self.fecha)
        self.doc = DocumentoPDF(f"Informe de tamizaje auditivo {codigo}")
        self.y = M

    # ------------------------------------------------------------ utilidades
    def _espacio(self, alto):
        if self.y + alto > LIMITE_PAGINA:
            self._pie()
            self.doc.nueva_pagina()
            self.y = M

    def _titulo_seccion(self, t):
        self._espacio(40)
        self.y += 8
        self.doc.texto(M, self.y, t.upper(), 9.5, True, (0.10, 0.20, 0.30))
        self.doc.linea(M, self.y + 3, 595.28 - M, self.y + 3, CLARO, 0.8)
        self.y += 16

    def _vinetas(self, lineas, tam=9.5, color=(0, 0, 0)):
        ancho = 595.28 - 2 * M - 12
        for t in lineas:
            self._espacio(tam * 2.6)
            self.doc.texto(M + 2, self.y, "\u2022", tam, False, color)
            self.y = self.doc.parrafo(M + 12, self.y, t, ancho, tam, False, color) + 2

    # ------------------------------------------------------------ partes
    def _encabezado(self):
        d = self.doc
        d.rect(M, M - 6, 595.28 - 2 * M, 46, relleno=(0.07, 0.20, 0.30))
        d.texto(M + 12, M + 14, "INFORME DE TAMIZAJE AUDITIVO", 15, True, (1, 1, 1))
        d.texto(M + 12, M + 30, f"Uyariy v{__version__}  ·  Audiometría tonal por vía aérea", 9, False,
                (0.80, 0.88, 0.94))
        fecha = self.fecha.replace("T", "  ")
        d.texto(595.28 - M - 12, M + 14, self.codigo, 12, True, (1, 1, 1), "der")
        d.texto(595.28 - M - 12, M + 30, f"Fecha: {fecha}", 9, False, (0.80, 0.88, 0.94), "der")
        self.y = M + 58

    def _paciente(self):
        p, d = self.p, self.doc
        nombre = " ".join(x for x in (p.get("nombres"), p.get("ap_paterno"), p.get("ap_materno")) if x)
        sexo = {"F": "Femenino", "M": "Masculino"}.get(p.get("sexo"), "")
        lugar = ", ".join(x for x in (p.get("comunidad"), p.get("municipio"), p.get("departamento")) if x)
        izq = [("Paciente", nombre), ("C.I.", f"{p.get('ci', '')} {p.get('ci_ext', '')}".strip()),
               ("Edad / sexo", f"{p.get('edad', '')} años  ·  {sexo}"), ("Procedencia", lugar or "-")]
        der = [("Motivo", p.get("motivo") or "-"), ("Establecimiento", p.get("establecimiento") or "-"),
               ("Evaluador", p.get("evaluador") or "-"),
               ("Método", "Automático (Hughson-Westlake)" if self.extra.get("metodo") == "automatico"
                else "Manual")]
        y0 = self.y
        for col, filas in ((M, izq), (M + 265, der)):
            y = y0
            for etiqueta, valor in filas:
                d.texto(col, y, etiqueta, 8, False, GRIS)
                d.texto(col + 78, y, str(valor)[:48], 9.5, etiqueta == "Paciente")
                y += 14
        self.y = y0 + 4 * 14 + 4

    def _audiograma(self, x, y, w, h, oido):
        d, col = self.doc, COLOR_OIDO[oido]
        titulo = "OÍDO DERECHO" if oido == "D" else "OÍDO IZQUIERDO"
        d.texto(x + w / 2, y, titulo, 10, True, col, "centro")
        gx, gy, gw, gh = x + 26, y + 18, w - 32, h - 34

        def fx(f):
            return gx + gw * math.log(f / F_MIN) / math.log(F_MAX / F_MIN)

        def fy(db):
            return gy + gh * (db - DB_MIN) / (DB_MAX - DB_MIN)

        d.rect(gx, gy, gw, gh, relleno=(1, 1, 1) if oido == "D" else (0.95, 0.98, 1.0))
        frs = sorted(BANANA)
        banana = [(fx(f), fy(BANANA[f][0])) for f in frs] + [(fx(f), fy(BANANA[f][1])) for f in reversed(frs)]
        d.poligono(banana, relleno=(0.98, 0.86, 0.86) if oido == "D" else (0.83, 0.92, 0.96))
        for db in range(DB_MIN, DB_MAX + 1, 10):
            d.linea(gx, fy(db), gx + gw, fy(db), (0.25, 0.25, 0.25) if db == 0 else CLARO, 0.8 if db == 0 else 0.4)
            d.texto(gx - 4, fy(db) + 2.5, str(db), 6.5, False, GRIS, "der")
        for f, t in ((125, ".125"), (250, ".25"), (500, ".5"), (1000, "1"), (2000, "2"), (4000, "4"), (8000, "8")):
            d.linea(fx(f), gy, fx(f), gy + gh, CLARO, 0.4)
            d.texto(fx(f), gy - 3, t, 6.5, False, GRIS, "centro")
        for f in (750, 1500, 3000, 6000):
            d.linea(fx(f), gy, fx(f), gy + gh, CLARO, 0.3, punteada=True)
        d.rect(gx, gy, gw, gh, borde=GRIS, grosor=0.6)
        d.texto(gx + gw, gy + gh + 9, "kHz  ·  dB HL", 6.5, False, GRIS, "der")

        puntos = sorted(self.umb[oido].items())
        unir = [(fx(f), fy(u.db)) for f, u in puntos if not u.nr]
        d.polilinea(unir, col, 1.0)
        for f, u in puntos:
            px, py = fx(f), fy(u.db)
            if u.enmascarado and oido == "D":
                d.poligono([(px, py - 4.5), (px - 4.5, py + 3.5), (px + 4.5, py + 3.5)], relleno=(1, 1, 1), borde=col,
                           grosor=1.1)
            elif u.enmascarado:
                d.rect(px - 3.8, py - 3.8, 7.6, 7.6, relleno=(1, 1, 1), borde=col, grosor=1.1)
            elif oido == "D":
                d.circulo(px, py, 3.8, relleno=(1, 1, 1), borde=col, grosor=1.2)
            else:
                d.linea(px - 3.6, py - 3.6, px + 3.6, py + 3.6, col, 1.3)
                d.linea(px - 3.6, py + 3.6, px + 3.6, py - 3.6, col, 1.3)
            if u.nr:                                  # flecha "sin respuesta" hacia abajo y afuera
                s = -1 if oido == "D" else 1
                ax, ay = px + s * 3, py + 3
                bx, by = px + s * 10, py + 10
                d.linea(ax, ay, bx, by, col, 1.0)
                d.linea(bx, by, bx - s * 4, by, col, 1.0)
                d.linea(bx, by, bx, by - 4, col, 1.0)

    def _audiogramas(self):
        w = (595.28 - 2 * M - 14) / 2
        self._espacio(212)
        self._audiograma(M, self.y + 8, w, 196, "D")
        self._audiograma(M + w + 14, self.y + 8, w, 196, "I")
        self.y += 212
        self.doc.texto(M, self.y, "O derecho   X izquierdo   triángulo/cuadrado = con enmascaramiento   "
                                  "flecha = sin respuesta al nivel indicado   zona color = región del habla",
                       6.8, False, GRIS)
        self.y += 10

    def _tabla(self):
        d = self.doc
        self._espacio(60)
        x0, ancho_col = M + 80, (595.28 - 2 * M - 80) / len(FRECS_TABLA)
        y = self.y + 10
        d.rect(M, y - 10, 595.28 - 2 * M, 14, relleno=(0.93, 0.95, 0.96))
        d.texto(M + 4, y, "Hz", 8, True, GRIS)
        for i, f in enumerate(FRECS_TABLA):
            d.texto(x0 + ancho_col * (i + 0.5), y, f"{f:g}", 8, True, GRIS, "centro")
        for fila, oido in enumerate(("D", "I")):
            yy = y + 15 * (fila + 1)
            d.texto(M + 4, yy, "Derecho (dB HL)" if oido == "D" else "Izquierdo (dB HL)", 8.5, True, COLOR_OIDO[oido])
            for i, f in enumerate(FRECS_TABLA):
                d.texto(x0 + ancho_col * (i + 0.5), yy, _valor(self.umb[oido].get(f)), 9, False, (0, 0, 0), "centro")
            d.linea(M, yy + 4, 595.28 - M, yy + 4, CLARO, 0.4)
        self.y = y + 15 * 2 + 12

    def _resultado(self):
        d, ev, ama = self.doc, self.r["evaluacion"], self.r["ama"]
        self._espacio(90)
        ver = ev["veredicto"]
        d.rect(M, self.y, 595.28 - 2 * M, 26, relleno=COLOR_VEREDICTO[ver])
        d.texto(M + 10, self.y + 17, f"RESULTADO: {ver}", 13, True, (1, 1, 1))
        d.texto(595.28 - M - 10, self.y + 17, "; ".join(ev["motivos"])[:80], 8.5, False, (1, 1, 1), "der")
        self.y += 40
        for oido in ("D", "I"):
            p, fl = ev["pta"][oido], ev["fletcher"][oido]
            pct = ama[oido]
            texto = (f"PTA {p:.0f} dB HL  ·  grado OMS: {ev['grado'][oido]}" if p is not None else "PTA incompleto")
            texto += f"  ·  Fletcher {fl:.0f} dB" if fl is not None else ""
            texto += f"  ·  AMA {pct:.1f} %" if pct is not None else ""
            d.texto(M, self.y, "Oído derecho:" if oido == "D" else "Oído izquierdo:", 9.5, True, COLOR_OIDO[oido])
            d.texto(M + 80, self.y, texto, 9.5)
            self.y += 14
        if ama["binaural"] is not None:
            nota = "  (3 kHz estimado con 2 y 4 kHz)" if ama["estimado"] else ""
            d.texto(M, self.y, "Discapacidad auditiva binaural (AMA/AAO-1979):", 9.5, True)
            d.texto(M + 232, self.y, f"{ama['binaural']:.1f} %{nota}", 9.5)
            self.y += 14

    def _interpretacion(self):
        ev, lineas = self.r["evaluacion"], []
        for oido, nombre in (("D", "derecho"), ("I", "izquierdo")):
            for patron in self.r["patrones"][oido]:
                lineas.append(f"Oído {nombre}: {patron}.")
        fia = self.extra.get("fiabilidad")
        if fia:
            if fia.get("confiable"):
                lineas.append(f"Respuestas confiables (prueba automática: {fia.get('trampas', 0)} pruebas trampa, "
                              f"{fia.get('falsos_trampa', 0)} respondidas; {fia.get('falsos_fuera', 0)} toques sin estímulo).")
            else:
                lineas.append("Respuestas POCO confiables: " + "; ".join(fia.get("mensajes", [])) + ". Repetir la prueba.")
        lineas += [a + "." for a in ev["avisos"]]
        if not lineas:
            lineas.append("Sin hallazgos adicionales en la forma del audiograma.")
        self._titulo_seccion("Interpretación automática")
        self._vinetas(lineas)

    def _observaciones(self):
        self._titulo_seccion("Observaciones del evaluador")
        lineas = []
        if self.observaciones:
            lineas.append("  ·  ".join(self.observaciones))
        if self.nota:
            lineas.append(f"«{self.nota}»")
        self._vinetas(lineas or ["Ninguna."])

    def _recomendaciones(self):
        self._titulo_seccion("Recomendaciones")
        self._vinetas(self.r["recomendaciones"])
        self._espacio(30)
        self.y += 4
        self.y = self.doc.parrafo(M, self.y, self.r["aviso"], 595.28 - 2 * M, 8, False, GRIS)

    def _firma(self):
        d = self.doc
        if self.y + 44 > 802:                       # la firma no entra: va en una hoja nueva
            self._pie()
            self.doc.nueva_pagina()
            self.y = M
        self.y = max(self.y + 44, 770)
        d.linea(M + 20, self.y, M + 210, self.y, (0, 0, 0), 0.6)
        d.texto(M + 115, self.y + 11, "Firma y sello del evaluador", 8, False, GRIS, "centro")
        d.rect(595.28 - M - 150, self.y - 40, 150, 52, borde=CLARO)
        d.texto(595.28 - M - 75, self.y - 26, "Código de verificación", 7.5, False, GRIS, "centro")
        d.texto(595.28 - M - 75, self.y - 8, self.verif, 15, True, (0.07, 0.20, 0.30), "centro")
        d.texto(595.28 - M - 75, self.y + 6, self.codigo, 7.5, False, GRIS, "centro")

    def _pie(self):
        cal = self.extra.get("calibracion", "")
        self.doc.texto(M, 822, f"Generado por Uyariy v{__version__} el {datetime.now():%d/%m/%Y %H:%M}"
                               + (f"  ·  calibración: {cal}" if cal else ""), 7, False, GRIS)
        self.doc.texto(595.28 - M, 822, f"{self.codigo}  ·  {self.verif}", 7, False, GRIS, "der")

    # ------------------------------------------------------------ todo junto
    def generar(self, ruta):
        self._encabezado()
        self._paciente()
        self._audiogramas()
        self._tabla()
        self._resultado()
        self._interpretacion()
        self._observaciones()
        self._recomendaciones()
        self._firma()
        self._pie()
        return self.doc.guardar(ruta)


def generar_informe(ruta, paciente, codigo, umbrales, extra=None, observaciones=(), nota=""):
    """Crea el PDF y devuelve (ruta, codigo_de_verificacion)."""
    inf = Informe(paciente, codigo, umbrales, extra, observaciones, nota)
    inf.generar(ruta)
    return ruta, inf.verif