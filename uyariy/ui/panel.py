"""
Piezas del panel físico del audiómetro (estilo Interacoustics AD629 / AC40):
- Tecla: botón con su luz LED encima (verde = activo).
- GrupoTeclas: teclas de selección única (oído, estímulo, presentación...).
- Perilla: perilla giratoria; cada "clic" de giro (18°) es un paso de 5 dB.
- BotonRedondo: el "Tone Switch" plateado para presentar el tono.
"""
import math

from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

PLACA = (0.91, 0.91, 0.89, 1)          # placa gris claro del equipo
TINTA_PLACA = (0.25, 0.27, 0.30, 1)    # serigrafía
TECLA = (0.24, 0.25, 0.27, 1)          # teclas negras
LED_ON = (0.30, 0.90, 0.40, 1)
LED_OFF = (0.62, 0.64, 0.65, 1)
ROJO_D = (0.80, 0.14, 0.15, 1)
AZUL_I = (0.14, 0.36, 0.78, 1)
AMARILLO = (0.93, 0.84, 0.52, 1)
NARANJA = (0.95, 0.60, 0.16, 1)


def _oscurecer(c, f=0.75):
    return (c[0] * f, c[1] * f, c[2] * f, c[3])


class Tecla(ButtonBehavior, BoxLayout):
    """Tecla del panel con LED. color = color de la tecla."""

    def __init__(self, texto, color=TECLA, color_texto=(1, 1, 1, 1), led=True, tam="15sp", **kw):
        super().__init__(orientation="vertical", spacing=dp(3), **kw)
        self.color = color
        self.led = None
        if led:
            self.led = Widget(size_hint_y=None, height=dp(6))
            with self.led.canvas:
                self._c_led = Color(*LED_OFF)
                self._r_led = RoundedRectangle(radius=[dp(2)])
            self.led.bind(pos=self._mover_led, size=self._mover_led)
            self.add_widget(self.led)
        self.cuerpo = Label(text=texto, markup=True, font_size=tam, color=color_texto, bold=True,
                            halign="center", valign="middle")
        self.cuerpo.bind(size=lambda w, s: setattr(w, "text_size", s))
        with self.cuerpo.canvas.before:
            self._c_cuerpo = Color(*color)
            self._r_cuerpo = RoundedRectangle(radius=[dp(7)])
        self.cuerpo.bind(pos=self._mover_cuerpo, size=self._mover_cuerpo)
        self.add_widget(self.cuerpo)

    def _mover_led(self, *_):
        self._r_led.pos = (self.led.x + dp(4), self.led.y)
        self._r_led.size = (self.led.width - dp(8), self.led.height)

    def _mover_cuerpo(self, *_):
        self._r_cuerpo.pos, self._r_cuerpo.size = self.cuerpo.pos, self.cuerpo.size

    def on_state(self, _w, estado):
        self._c_cuerpo.rgba = _oscurecer(self.color) if estado == "down" else self.color

    def encender(self, si=True):
        if self.led:
            self._c_led.rgba = LED_ON if si else LED_OFF

    @property
    def text(self):
        return self.cuerpo.text

    @text.setter
    def text(self, t):
        self.cuerpo.text = t


class GrupoTeclas:
    """Teclas de selección única. No es un widget: las teclas se colocan donde se quiera."""

    def __init__(self, opciones, inicial, al_cambiar, colores=None, **kw_tecla):
        self.al_cambiar = al_cambiar
        self.valor = inicial
        self.teclas = {}
        for valor, etiqueta in opciones:
            t = Tecla(etiqueta, (colores or {}).get(valor, TECLA), **kw_tecla)
            t.bind(on_release=lambda _t, v=valor: self.elegir(v))
            self.teclas[valor] = t
        self._luces()

    def _luces(self):
        for v, t in self.teclas.items():
            t.encender(v == self.valor)

    def elegir(self, valor):
        self.valor = valor
        self._luces()
        self.al_cambiar(valor)


class Perilla(Widget):
    """Perilla giratoria. Girar a la derecha = subir. al_girar(pasos) recibe +1 / -1 por cada clic."""

    GRADOS_POR_PASO = 18

    def __init__(self, al_girar, color=(0.17, 0.18, 0.20, 1), **kw):
        super().__init__(**kw)
        self.al_girar = al_girar
        self.angulo = 0.0               # ángulo visual de la marca
        self._acumulado = 0.0
        self._previo = None
        with self.canvas:
            Color(0.72, 0.73, 0.74, 1)
            self._aro = Ellipse()
            Color(*color)
            self._cuerpo = Ellipse()
            Color(0.27, 0.28, 0.31, 1)
            self._brillo = Line(width=dp(1.4))
            Color(0.95, 0.95, 0.95, 1)
            self._marca = Line(width=dp(3), cap="round")
        self.bind(pos=self._dibujar, size=self._dibujar)

    def _centro_radio(self):
        r = min(self.width, self.height) / 2
        return self.center_x, self.center_y, r

    def _dibujar(self, *_):
        cx, cy, r = self._centro_radio()
        self._aro.pos, self._aro.size = (cx - r, cy - r), (2 * r, 2 * r)
        r2 = r - dp(6)
        self._cuerpo.pos, self._cuerpo.size = (cx - r2, cy - r2), (2 * r2, 2 * r2)
        self._brillo.circle = (cx, cy, r2 * 0.80)
        a = math.radians(90 - self.angulo)
        self._marca.points = [cx + math.cos(a) * r2 * 0.45, cy + math.sin(a) * r2 * 0.45,
                              cx + math.cos(a) * r2 * 0.85, cy + math.sin(a) * r2 * 0.85]

    def _angulo_toque(self, touch):
        cx, cy, _ = self._centro_radio()
        return math.degrees(math.atan2(touch.y - cy, touch.x - cx))

    def on_touch_down(self, touch):
        cx, cy, r = self._centro_radio()
        if (touch.x - cx) ** 2 + (touch.y - cy) ** 2 > r * r:
            return super().on_touch_down(touch)
        touch.grab(self)
        self._previo = self._angulo_toque(touch)
        self._acumulado = 0.0
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        actual = self._angulo_toque(touch)
        delta = (self._previo - actual + 180) % 360 - 180      # positivo = sentido horario
        self._previo = actual
        self._acumulado += delta
        while abs(self._acumulado) >= self.GRADOS_POR_PASO:
            paso = 1 if self._acumulado > 0 else -1
            self._acumulado -= paso * self.GRADOS_POR_PASO
            self.girar(paso)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def girar(self, paso):
        self.angulo = (self.angulo + paso * self.GRADOS_POR_PASO) % 360
        self._dibujar()
        self.al_girar(paso)


class BotonRedondo(ButtonBehavior, Widget):
    """Botón plateado redondo (Tone Switch). 'encendido' lo ilumina en ámbar mientras suena."""

    encendido = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas:
            self._c_aro = Color(0.55, 0.57, 0.60, 1)
            self._aro = Ellipse()
            self._c = Color(0.82, 0.84, 0.86, 1)
            self._disco = Ellipse()
            Color(0.94, 0.95, 0.96, 1)
            self._brillo = Ellipse()
        self.bind(pos=self._dibujar, size=self._dibujar, state=self._color, encendido=self._color)

    def _dibujar(self, *_):
        r = min(self.width, self.height) / 2
        cx, cy = self.center
        self._aro.pos, self._aro.size = (cx - r, cy - r), (2 * r, 2 * r)
        r2 = r - dp(5)
        self._disco.pos, self._disco.size = (cx - r2, cy - r2), (2 * r2, 2 * r2)
        r3 = r2 * 0.45
        self._brillo.pos, self._brillo.size = (cx - r3 - r2 * 0.18, cy - r3 + r2 * 0.18), (2 * r3, 2 * r3)

    def _color(self, *_):
        if self.encendido:
            self._c.rgba = (0.98, 0.72, 0.25, 1)
        elif self.state == "down":
            self._c.rgba = (0.66, 0.68, 0.70, 1)
        else:
            self._c.rgba = (0.82, 0.84, 0.86, 1)

    def collide_point(self, x, y):
        r = min(self.width, self.height) / 2
        return (x - self.center_x) ** 2 + (y - self.center_y) ** 2 <= r * r
