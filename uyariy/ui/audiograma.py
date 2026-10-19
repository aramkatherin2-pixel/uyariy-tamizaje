"""
Audiograma de un oído, dibujado en vivo con el estilo de la pantalla de tonos del AC40
(manual AC40, sección 3.5.1, pág. 23; "Show banana overlay", pág. 40).

Eje X: frecuencia (escala logarítmica, 125-8000 Hz): octavas arriba (kHz), interoctavas abajo.
Eje Y: dB HL (-10 arriba, 120 abajo).
- Zona sombreada en forma de "banana": región de los sonidos del habla.
- Zona gris inferior: niveles que el equipo (tablet + audífonos) no alcanza a producir.
Símbolos (norma ASHA): O rojo = derecho, X azul = izquierdo,
triángulo / cuadrado = derecho / izquierdo con enmascaramiento; flecha = sin respuesta.
"""
import math

from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from ..audio.generador import FRECUENCIAS_ESTANDAR
from ..clinica.clasificacion import GRADOS_OMS, pta, pta_fletcher

DB_MIN, DB_MAX = -10, 120
F_MIN, F_MAX = 125, 8000
OCTAVAS = {125: ".125", 250: ".25", 500: ".5", 1000: "1", 2000: "2", 4000: "4", 8000: "8"}
INTEROCTAVAS = {750: ".75", 1500: "1.5", 3000: "3", 6000: "6"}

# Región del habla ("banana"): límite superior e inferior en dB HL por frecuencia
BANANA = {125: (5, 30), 250: (12, 45), 500: (20, 57), 1000: (22, 62), 2000: (18, 58),
          4000: (15, 50), 8000: (10, 43)}

ESTILO = {
    "D": {"linea": (0.82, 0.18, 0.20, 1), "fondo": (1, 1, 1, 1), "banana": (0.95, 0.62, 0.62, 0.55),
          "titulo": "Auricular D"},
    "I": {"linea": (0.15, 0.38, 0.82, 1), "fondo": (0.93, 0.98, 0.99, 1), "banana": (0.55, 0.82, 0.88, 0.60),
          "titulo": "Auricular I"},
}
NOMBRE_ESTIMULO = {"tono": "Tono", "warble": "Warble", "nbn": "NB", "banda_ancha": "BA"}
NOMBRE_CORTO = {"Moderadamente severa": "Mod. severa"}
ANCHO_ESCALA = 74                   # dp a la derecha para la escala de grados OMS


def _interp_log(tabla, f):
    """Interpola linealmente en escala logarítmica de frecuencia."""
    fs = sorted(tabla)
    f = min(max(f, fs[0]), fs[-1])
    for a, b in zip(fs, fs[1:]):
        if a <= f <= b:
            t = math.log2(f / a) / math.log2(b / a)
            return tuple(va + t * (vb - va) for va, vb in zip(tabla[a], tabla[b]))
    return tabla[fs[-1]]


class Audiograma(Widget):
    def __init__(self, oido="D", **kw):
        super().__init__(**kw)
        self.oido = oido
        self.estilo = ESTILO[oido]
        self.color = self.estilo["linea"]
        self.umbrales = {}          # {frecuencia: Umbral}
        self.cursor = None          # (frecuencia, dB) que se está presentando
        self.limite = None          # función f -> dB HL máximo del equipo (zona gris)
        self.estimulo = "tono"
        self._etiquetas = []
        self._dinamicas = {}
        self.bind(pos=self._todo, size=self._todo)

    # ------------------------------------------------------------ geometría
    @property
    def _area(self):
        """Rectángulo de la cuadrícula: (x, y, ancho, alto)."""
        izq, der, abajo, arriba = dp(34), dp(ANCHO_ESCALA), dp(20), dp(40)
        return self.x + izq, self.y + abajo, max(1, self.width - izq - der), max(1, self.height - abajo - arriba)

    def x_de(self, f):
        x, _, w, _ = self._area
        return x + w * math.log2(f / F_MIN) / math.log2(F_MAX / F_MIN)

    def y_de(self, db):
        _, y, _, h = self._area
        db = min(max(db, DB_MIN), DB_MAX)
        return y + h * (1 - (db - DB_MIN) / (DB_MAX - DB_MIN))

    def _franja(self, f_arriba, f_abajo):
        """Dibuja una banda entre dos curvas (funciones f -> dB), muestreada cada 1/12 de octava."""
        pasos = [F_MIN * 2 ** (i / 12) for i in range(0, 73)]
        for a, b in zip(pasos, pasos[1:]):
            xa, xb = self.x_de(a), self.x_de(b)
            v = [xa, self.y_de(f_arriba(a)), 0, 0, xb, self.y_de(f_arriba(b)), 0, 0,
                 xb, self.y_de(f_abajo(b)), 0, 0, xa, self.y_de(f_abajo(a)), 0, 0]
            Mesh(vertices=v, indices=[0, 1, 2, 3], mode="triangle_fan")

    # -------------------------------------------------------------- dibujo
    def actualizar(self, umbrales=None, cursor="igual", estimulo=None):
        if umbrales is not None:
            self.umbrales = umbrales
        if cursor != "igual":
            self.cursor = cursor
        if estimulo:
            self.estimulo = estimulo
        self._datos()

    def _todo(self, *_):
        self._fondo()
        self._datos()

    def _fondo(self):
        x, y, w, h = self._area
        self.canvas.before.clear()
        for e in self._etiquetas:
            self.remove_widget(e)
        self._etiquetas = []
        with self.canvas.before:
            Color(1, 1, 1, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(*self.estilo["fondo"])
            Rectangle(pos=(x, y), size=(w, h))
            # zona que el equipo no alcanza (gris), como en el AC40
            if self.limite:
                Color(0.80, 0.81, 0.83, 0.75)
                self._franja(lambda f: self.limite(f), lambda f: DB_MAX)
            # región del habla (banana)
            Color(*self.estilo["banana"])
            self._franja(lambda f: _interp_log(BANANA, f)[0], lambda f: _interp_log(BANANA, f)[1])
            # cuadrícula
            for db in range(DB_MIN, DB_MAX + 1, 10):
                Color(0.45, 0.47, 0.50, 1) if db == 0 else Color(0.78, 0.80, 0.83, 1)
                Line(points=[x, self.y_de(db), x + w, self.y_de(db)], width=1.1 if db == 0 else 1)
            for f in FRECUENCIAS_ESTANDAR:
                inter = f in INTEROCTAVAS
                Color(0.80, 0.82, 0.85, 1) if inter else Color(0.62, 0.65, 0.69, 1)
                Line(points=[self.x_de(f), y, self.x_de(f), y + h],
                     dash_offset=3 if inter else 0, dash_length=3 if inter else 1)
            Color(0.40, 0.43, 0.47, 1)
            Line(rectangle=(x, y, w, h), width=1.1)
            # escala de grados OMS 2021 al costado derecho (franja de color + marcas)
            xe = x + w + dp(8)
            inicio = DB_MIN
            for limite, _nombre, color in GRADOS_OMS:
                fin = min(limite, DB_MAX)
                Color(*color[:3], 0.85)
                Rectangle(pos=(xe, self.y_de(fin)), size=(dp(5), self.y_de(inicio) - self.y_de(fin)))
                Color(0.35, 0.37, 0.40, 1)
                Line(points=[xe - dp(3), self.y_de(fin), xe + dp(8), self.y_de(fin)], width=1)
                inicio = fin
        gris = (0.30, 0.33, 0.37, 1)
        paso = 10 if h / 13 > dp(14) else 20
        for db in range(DB_MIN, DB_MAX + 1, paso):
            self._texto(str(db), self.x, self.y_de(db) - dp(8), dp(30), dp(16), "right", gris)
        for f, t in OCTAVAS.items():                       # octavas arriba (kHz), como el AC40
            self._texto(t, self.x_de(f) - dp(16), y + h + dp(1), dp(32), dp(16), "center", gris)
        self._texto("kHz", x + w - dp(30), y + h - dp(16), dp(28), dp(14), "right", gris, "10sp")
        for f, t in INTEROCTAVAS.items():                  # interoctavas abajo
            self._texto(t, self.x_de(f) - dp(16), self.y + dp(1), dp(32), dp(16), "center", gris)
        self._texto("dB HL", x + dp(3), y + dp(2), dp(50), dp(14), "left", gris, "10sp")
        inicio = DB_MIN
        for limite, nombre, color in GRADOS_OMS:           # nombres de los grados OMS
            fin = min(limite, DB_MAX)
            centro = (self.y_de(inicio) + self.y_de(fin)) / 2
            self._texto(NOMBRE_CORTO.get(nombre, nombre), x + w + dp(15), centro - dp(8), dp(ANCHO_ESCALA - 16),
                        dp(16), "left", color[:3] + (1,), "10sp")
            inicio = fin
        self._texto("Grado OMS", x + w + dp(14), y + h + dp(1), dp(60), dp(16), "left", gris, "10sp")
        self._texto("Región del habla", self.x_de(700) - dp(60), self.y_de(48) - dp(8), dp(120), dp(16),
                    "center", (0.35, 0.38, 0.42, 0.8), "10sp")
        # títulos dinámicos (se actualizan en _datos)
        self._dinamicas["titulo"] = self._texto("", x, y + h + dp(18), w, dp(20), "left", self.color, "13sp")
        self._dinamicas["pta"] = self._texto("", x, y + h + dp(18), w + dp(ANCHO_ESCALA - 6), dp(20), "right",
                                             self.color, "11sp")

    def _texto(self, t, x, y, w, h, alineacion, color, tam="11sp"):
        lb = Label(text=t, markup=True, font_size=tam, color=color, pos=(x, y), size=(w, h),
                   halign=alineacion, valign="middle", text_size=(w, h))
        self._etiquetas.append(lb)
        self.add_widget(lb)
        return lb

    def _datos(self):
        if "titulo" in self._dinamicas:
            enm = any(u.enmascarado for u in self.umbrales.values())
            self._dinamicas["titulo"].text = (f"[b]{self.estilo['titulo']} - "
                                              f"{NOMBRE_ESTIMULO.get(self.estimulo, 'Tono')}[/b]"
                                              + ("  (enmascarado)" if enm else ""))
            p, fl = pta(self.umbrales), pta_fletcher(self.umbrales)
            self._dinamicas["pta"].text = ("AC PTA: " + (f"{p:.1f}" if p is not None else "-") + " dB   "
                                           "Fletcher: " + (f"{fl:.1f}" if fl is not None else "-"))
        # se dibuja en canvas.after: canvas.clear() borraría también las etiquetas de los ejes
        self.canvas.after.clear()
        r = dp(7)
        with self.canvas.after:
            if self.cursor:                                # estímulo actual (cuadrado gris, como el AC40)
                f, db = self.cursor
                Color(0.35, 0.37, 0.40, 0.55)
                Rectangle(pos=(self.x_de(f) - r, self.y_de(db) - r), size=(2 * r, 2 * r))
            pts = []
            for f in sorted(self.umbrales):
                u = self.umbrales[f]
                if not u.nr:
                    pts += [self.x_de(f), self.y_de(u.db)]
            Color(*self.color)
            if len(pts) >= 4:
                Line(points=pts, width=1.3)
            for f, u in self.umbrales.items():
                self._simbolo(self.x_de(f), self.y_de(u.db), u, r)

    def _simbolo(self, cx, cy, u, r):
        Color(1, 1, 1, 1)
        Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))       # fondo blanco bajo el símbolo
        Color(*self.color)
        if self.oido == "D" and not u.enmascarado:              # O
            Line(circle=(cx, cy, r), width=1.7)
        elif self.oido == "D":                                  # triángulo
            Line(points=[cx, cy + r, cx - r, cy - r * 0.8, cx + r, cy - r * 0.8], close=True, width=1.7)
        elif not u.enmascarado:                                 # X
            Line(points=[cx - r, cy - r, cx + r, cy + r], width=1.7)
            Line(points=[cx - r, cy + r, cx + r, cy - r], width=1.7)
        else:                                                   # cuadrado
            Line(rectangle=(cx - r, cy - r, 2 * r, 2 * r), width=1.7)
        if u.nr:                                                # flecha de "sin respuesta"
            s = -1 if self.oido == "D" else 1
            x2, y2 = cx + s * r * 2, cy - r * 2.2
            Line(points=[cx + s * r * 0.7, cy - r * 0.7, x2, y2], width=1.5)
            Line(points=[x2, y2, x2 - s * r * 0.9, y2 + r * 0.1], width=1.5)
            Line(points=[x2, y2, x2 - s * r * 0.1, y2 + r * 0.9], width=1.5)