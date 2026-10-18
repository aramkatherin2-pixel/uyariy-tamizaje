"""Colores y piezas visuales comunes de Uyariy (Kivy)."""
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

# Tema oscuro (consola) y tema claro (fichas)
FONDO = (0.07, 0.08, 0.09, 1)
PANEL = (0.13, 0.14, 0.16, 1)
CLARO = (0.93, 0.94, 0.93, 1)
BLANCO = (1, 1, 1, 1)
TINTA = (0.08, 0.13, 0.17, 1)
GRIS = (0.36, 0.41, 0.46, 1)
CAMPO = (0.96, 0.97, 0.98, 1)
BOTON_CLARO = (0.87, 0.90, 0.93, 1)
ROJO = (0.79, 0.21, 0.23, 1)
AZUL = (0.16, 0.39, 0.79, 1)
VERDE = (0.18, 0.60, 0.35, 1)
AMBAR = (0.89, 0.60, 0.12, 1)
GRIS_BTN = (0.24, 0.26, 0.29, 1)
TEXTO_SUAVE = (0.62, 0.66, 0.70, 1)


def fondo(widget, color, radio=0):
    with widget.canvas.before:
        Color(*color)
        r = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radio]) if radio else \
            Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, p: setattr(r, "pos", p), size=lambda w, s: setattr(r, "size", s))
    return r


def etiqueta(texto, tam="13sp", color=GRIS, negrita=False, alto=dp(20), **kw):
    lb = Label(text=texto, markup=True, font_size=tam, color=color, bold=negrita,
               halign="left", valign="middle", size_hint_y=None, height=alto, **kw)
    lb.bind(size=lambda w, s: setattr(w, "text_size", s))
    return lb


def boton(texto, color=GRIS_BTN, color_texto=BLANCO, **kw):
    kw.setdefault("font_size", "16sp")
    return Button(text=texto, background_normal="", background_down="", background_color=color,
                  color=color_texto, **kw)


def campo(texto="", pista="", **kw):
    return TextInput(text=texto, hint_text=pista, multiline=False, font_size="16sp",
                     size_hint_y=None, height=dp(40), padding=(dp(10), dp(10)),
                     background_normal="", background_active="", background_color=CAMPO,
                     foreground_color=TINTA, cursor_color=AZUL, write_tab=False, **kw)


def selector(texto, valores, **kw):
    return Spinner(text=texto, values=valores, font_size="16sp", size_hint_y=None, height=dp(40),
                   background_normal="", background_color=BOTON_CLARO, color=TINTA, **kw)


def bloque(titulo, widget, obligatorio=False):
    """Etiqueta encima de un campo."""
    caja = BoxLayout(orientation="vertical", spacing=dp(3), size_hint_y=None, height=dp(64))
    caja.add_widget(etiqueta(titulo + ("  [color=c9353b]*[/color]" if obligatorio else "")))
    caja.add_widget(widget)
    return caja


class GrupoBotones(BoxLayout):
    """Botones de opción única (como Femenino / Masculino)."""

    def __init__(self, opciones, grupo, colores=None, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        super().__init__(spacing=dp(6), **kw)
        self.colores = colores or {}
        self.valor = None
        self.botones = {}
        for valor, texto in opciones:
            b = ToggleButton(text=texto, group=grupo, font_size="15sp", background_normal="",
                             background_down="")
            b.valor = valor
            b.bind(state=self._cambio)
            self.botones[valor] = b
            self.add_widget(b)
            self._pintar(b)

    def _pintar(self, b):
        activo = b.state == "down"
        b.background_color = self.colores.get(b.valor, AZUL) if activo else BOTON_CLARO
        b.color = BLANCO if activo else TINTA

    def _cambio(self, b, estado):
        self._pintar(b)
        if estado == "down":
            self.valor = b.valor
        elif self.valor == b.valor:
            self.valor = None

    def elegir(self, valor):
        for v, b in self.botones.items():
            b.state = "down" if v == valor else "normal"
        self.valor = valor


class Casilla(BoxLayout):
    """Casilla de verificación con texto."""

    def __init__(self, texto, activo=False, **kw):
        super().__init__(size_hint_y=None, height=dp(32), spacing=dp(4), **kw)
        self.texto = texto
        self.cb = CheckBox(active=activo, size_hint_x=None, width=dp(32), color=(0.1, 0.3, 0.6, 1))
        lb = Label(text=texto, font_size="14sp", color=TINTA, halign="left", valign="middle")
        lb.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self.cb)
        self.add_widget(lb)

    @property
    def activo(self):
        return self.cb.active


class Tarjeta(BoxLayout):
    """Contenedor blanco con título y franja de color (ficha clínica)."""

    def __init__(self, titulo, color=AZUL, **kw):
        kw.setdefault("size_hint_y", None)
        super().__init__(orientation="vertical", padding=(dp(16), dp(12), dp(16), dp(12)), spacing=dp(6), **kw)
        self.bind(minimum_height=self.setter("height"))
        self.color = color
        self.bind(pos=self._dibujar, size=self._dibujar)
        self.add_widget(etiqueta(titulo, "17sp", TINTA, True, dp(28)))

    def _dibujar(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*BLANCO)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
            Color(*self.color)
            RoundedRectangle(pos=(self.x, self.top - dp(5)), size=(self.width, dp(5)), radius=[dp(10), dp(10), 0, 0])