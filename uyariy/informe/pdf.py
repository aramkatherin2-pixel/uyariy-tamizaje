"""
Generador de PDF mínimo en Python puro (sin librerías externas: funciona igual en la PC y en Android).

Hoja A4 vertical, medidas en puntos (1 cm = 28,35 pt). El origen (0, 0) está ARRIBA a la
izquierda, como en una hoja de papel: "y" crece hacia abajo.
Fuentes estándar Helvetica y Helvetica-Bold (acentos y ñ con la codificación WinAnsi).
"""
import zlib

ANCHO, ALTO = 595.28, 841.89          # A4
CM = 28.3465

# Anchos de Helvetica (1/1000 del tamaño) para los caracteres 32..126 (de su archivo AFM)
_ANCHOS = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
           556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
           1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
           667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
           333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
           556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_SIN_ACENTO = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ", "aeiouAEIOUnNuU")


def ancho_texto(s, tam, negrita=False):
    total = 0
    for ch in s.translate(_SIN_ACENTO):
        o = ord(ch)
        total += _ANCHOS[o - 32] if 32 <= o <= 126 else 556
    return total * tam / 1000 * (1.06 if negrita else 1.0)


def partir_lineas(s, tam, ancho_max, negrita=False):
    """Corta un texto largo en líneas que entran en ancho_max."""
    lineas, actual = [], ""
    for palabra in s.split():
        prueba = f"{actual} {palabra}".strip()
        if ancho_texto(prueba, tam, negrita) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _escapar(s):
    b = s.encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


class DocumentoPDF:
    def __init__(self, titulo="Informe"):
        self.titulo = titulo
        self.paginas = []
        self.nueva_pagina()

    # ------------------------------------------------------------ páginas
    def nueva_pagina(self):
        self.ops = []
        self.paginas.append(self.ops)

    def _y(self, y):
        return ALTO - y

    def _color(self, rgb, relleno):
        r, g, b = rgb[:3]
        return f"{_num(r)} {_num(g)} {_num(b)} {'rg' if relleno else 'RG'}"

    # ------------------------------------------------------------ dibujo
    def texto(self, x, y, s, tam=10, negrita=False, color=(0, 0, 0), alinear="izq"):
        """y = línea base del texto (desde arriba)."""
        if alinear != "izq":
            w = ancho_texto(s, tam, negrita)
            x -= w if alinear == "der" else w / 2
        fuente = "F2" if negrita else "F1"
        self.ops.append(b"BT " + self._color(color, True).encode() + f" /{fuente} {_num(tam)} Tf "
                        f"{_num(x)} {_num(self._y(y))} Td (".encode() + _escapar(s) + b") Tj ET")

    def parrafo(self, x, y, s, ancho, tam=10, negrita=False, color=(0, 0, 0), interlineado=1.3):
        """Escribe un texto con cortes de línea. Devuelve la 'y' siguiente."""
        for linea in partir_lineas(s, tam, ancho, negrita):
            self.texto(x, y, linea, tam, negrita, color)
            y += tam * interlineado
        return y

    def linea(self, x1, y1, x2, y2, color=(0, 0, 0), grosor=0.5, punteada=False):
        guion = "[2 2] 0 d" if punteada else "[] 0 d"
        self.ops.append(f"q {self._color(color, False)} {_num(grosor)} w {guion} {_num(x1)} {_num(self._y(y1))} m "
                        f"{_num(x2)} {_num(self._y(y2))} l S Q".encode())

    def polilinea(self, puntos, color=(0, 0, 0), grosor=1.0):
        if len(puntos) < 2:
            return
        camino = " ".join(f"{_num(x)} {_num(self._y(y))} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(puntos))
        self.ops.append(f"q {self._color(color, False)} {_num(grosor)} w 1 j {camino} S Q".encode())

    def poligono(self, puntos, relleno=None, borde=None, grosor=0.5):
        camino = " ".join(f"{_num(x)} {_num(self._y(y))} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(puntos))
        self._figura(camino + " h", relleno, borde, grosor)

    def rect(self, x, y, w, h, relleno=None, borde=None, grosor=0.5):
        self._figura(f"{_num(x)} {_num(self._y(y + h))} {_num(w)} {_num(h)} re", relleno, borde, grosor)

    def circulo(self, cx, cy, r, relleno=None, borde=None, grosor=1.0):
        k = 0.5523 * r
        cy = self._y(cy)
        c = (f"{_num(cx + r)} {_num(cy)} m "
             f"{_num(cx + r)} {_num(cy + k)} {_num(cx + k)} {_num(cy + r)} {_num(cx)} {_num(cy + r)} c "
             f"{_num(cx - k)} {_num(cy + r)} {_num(cx - r)} {_num(cy + k)} {_num(cx - r)} {_num(cy)} c "
             f"{_num(cx - r)} {_num(cy - k)} {_num(cx - k)} {_num(cy - r)} {_num(cx)} {_num(cy - r)} c "
             f"{_num(cx + k)} {_num(cy - r)} {_num(cx + r)} {_num(cy - k)} {_num(cx + r)} {_num(cy)} c h")
        self._figura(c, relleno, borde, grosor)

    def _figura(self, camino, relleno, borde, grosor):
        partes = ["q"]
        if relleno:
            partes.append(self._color(relleno, True))
        if borde:
            partes.append(f"{self._color(borde, False)} {_num(grosor)} w [] 0 d")
        partes.append(camino)
        partes.append("B" if relleno and borde else ("f" if relleno else "S"))
        partes.append("Q")
        self.ops.append(" ".join(partes).encode())

    # ------------------------------------------------------------ archivo
    def a_bytes(self):
        objetos = []                                   # contenido de cada objeto (1, 2, 3...)

        def agregar(contenido):
            objetos.append(contenido)
            return len(objetos)

        catalogo = agregar(None)
        paginas_id = agregar(None)
        f1 = agregar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = agregar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        hijos = []
        for ops in self.paginas:
            datos = zlib.compress(b"\n".join(ops))
            flujo = agregar(f"<< /Length {len(datos)} /Filter /FlateDecode >>\nstream\n".encode() + datos
                            + b"\nendstream")
            hijos.append(agregar(
                f"<< /Type /Page /Parent {paginas_id} 0 R /MediaBox [0 0 {_num(ANCHO)} {_num(ALTO)}] "
                f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {flujo} 0 R >>".encode()))
        objetos[catalogo - 1] = f"<< /Type /Catalog /Pages {paginas_id} 0 R >>".encode()
        objetos[paginas_id - 1] = (f"<< /Type /Pages /Count {len(hijos)} /Kids ["
                                   + " ".join(f"{h} 0 R" for h in hijos) + "] >>").encode()
        info = agregar(b"<< /Title (" + _escapar(self.titulo) + b") /Producer (Uyariy) >>")

        salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posiciones = []
        for i, contenido in enumerate(objetos, start=1):
            posiciones.append(len(salida))
            salida += f"{i} 0 obj\n".encode() + contenido + b"\nendobj\n"
        xref = len(salida)
        salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
        for p in posiciones:
            salida += f"{p:010d} 00000 n \n".encode()
        salida += (f"trailer\n<< /Size {len(objetos) + 1} /Root {catalogo} 0 R /Info {info} 0 R >>\n"
                   f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(salida)

    def guardar(self, ruta):
        with open(ruta, "wb") as f:
            f.write(self.a_bytes())
        return ruta