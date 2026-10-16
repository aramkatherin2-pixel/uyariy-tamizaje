"""
Uyariy - Paso 2: banco de pruebas del motor de audio.

Permite elegir frecuencia, dB HL, oído, tipo de estímulo, modo de presentación
y enmascaramiento, y escuchar el resultado por los audífonos.
Ejecutar:  python main.py
"""
import os

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import platform

from uyariy import __version__
from uyariy.audio.calibracion import Calibracion, NivelFueraDeRango
from uyariy.audio.generador import FRECUENCIAS_ESTANDAR
from uyariy.audio.motor import Enmascaramiento, Estimulo, MotorAudio

if platform not in ("android", "ios"):
    Window.size = (1280, 800)

FONDO = (0.07, 0.08, 0.09, 1)
PANEL = (0.13, 0.14, 0.16, 1)
ROJO = (0.79, 0.21, 0.23, 1)
AZUL = (0.16, 0.39, 0.79, 1)
VERDE = (0.18, 0.60, 0.35, 1)
AMBAR = (0.89, 0.60, 0.12, 1)
GRIS_BTN = (0.24, 0.26, 0.29, 1)
TEXTO_SUAVE = (0.62, 0.66, 0.70, 1)


def fondo(widget, color):
    with widget.canvas.before:
        Color(*color)
        r = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, p: setattr(r, "pos", p), size=lambda w, s: setattr(r, "size", s))


def boton(texto, color=GRIS_BTN, **kw):
    kw.setdefault("font_size", "17sp")
    return Button(text=texto, background_normal="", background_color=color, **kw)


class GrupoOpciones(BoxLayout):
    """Fila de botones de selección única (como los botones con LED del audiómetro)."""

    def __init__(self, titulo, opciones, inicial, al_cambiar, colores=None, **kw):
        super().__init__(orientation="vertical", spacing=4, **kw)
        self.al_cambiar = al_cambiar
        self.colores = colores or {}
        self.add_widget(Label(text=titulo, color=TEXTO_SUAVE, font_size="13sp", size_hint_y=None, height=20,
                              halign="left", valign="middle", text_size=(None, None)))
        fila = BoxLayout(spacing=4)
        self.botones = {}
        grupo = f"g_{titulo}"
        for valor, etiqueta in opciones:
            b = ToggleButton(text=etiqueta, group=grupo, allow_no_selection=False, background_normal="",
                             background_down="", font_size="15sp")
            b.valor = valor
            b.bind(state=self._estado)
            self.botones[valor] = b
            fila.add_widget(b)
        self.add_widget(fila)
        for b in self.botones.values():
            self._pintar(b)
        self.botones[inicial].state = "down"

    def _pintar(self, b):
        b.background_color = self.colores.get(b.valor, VERDE) if b.state == "down" else GRIS_BTN

    def _estado(self, b, estado):
        self._pintar(b)
        if estado == "down":
            self.al_cambiar(b.valor)


class BancoAudio(BoxLayout):
    def __init__(self, motor, ruta_cal, **kw):
        super().__init__(orientation="vertical", padding=16, spacing=10, **kw)
        fondo(self, FONDO)
        self.motor = motor
        self.ruta_cal = ruta_cal
        self.est = Estimulo(frecuencia=1000, dbhl=30, oido="D", tipo="tono", duracion=1.0)
        self.enm = Enmascaramiento(activo=False, dbem=40, tipo="nbn")
        self.modo = "pulso"
        self.paso = 5
        self._listo = False  # evita refrescar antes de crear todas las etiquetas

        # ----- cabecera
        cab = BoxLayout(size_hint_y=None, height=50)
        titulo = Label(text=f"[b]UYARIY[/b]  [color=8fa0b0]· Paso 2: motor de audio · v{__version__}[/color]",
                       markup=True, font_size="24sp", halign="left", valign="middle", size_hint_x=0.65)
        titulo.bind(size=lambda w, s: setattr(w, "text_size", s))
        cab.add_widget(titulo)
        self.lbl_backend = Label(text="", color=TEXTO_SUAVE, font_size="13sp", halign="right", valign="middle")
        self.lbl_backend.bind(size=lambda w, s: setattr(w, "text_size", s))
        cab.add_widget(self.lbl_backend)
        self.add_widget(cab)

        # ----- frecuencia
        self.add_widget(GrupoOpciones(
            "FRECUENCIA (Hz)",
            [(f, f"{f // 1000}k" if f >= 1000 and f % 1000 == 0 else (f"{f / 1000:g}k" if f >= 1000 else str(f)))
             for f in FRECUENCIAS_ESTANDAR],
            1000, self._cambiar_frecuencia, colores={f: (0.12, 0.55, 0.75, 1) for f in FRECUENCIAS_ESTANDAR},
            size_hint_y=None, height=78))

        # ----- nivel + oído
        centro = BoxLayout(spacing=14, size_hint_y=None, height=170)
        nivel = BoxLayout(orientation="vertical", padding=10, spacing=6)
        fondo(nivel, PANEL)
        self.lbl_nivel = Label(text="", markup=True, font_size="56sp", bold=True)
        nivel.add_widget(self.lbl_nivel)
        fila = BoxLayout(spacing=6, size_hint_y=None, height=50)
        for t, d in [("-10", -10), ("-5", -5), ("+5", 5), ("+10", 10)]:
            b = boton(t, font_size="20sp")
            b.bind(on_release=lambda _b, d=d: self._cambiar_nivel(d))
            fila.add_widget(b)
        nivel.add_widget(fila)
        self.lbl_max = Label(text="", color=TEXTO_SUAVE, font_size="13sp", size_hint_y=None, height=20)
        nivel.add_widget(self.lbl_max)
        centro.add_widget(nivel)

        der = BoxLayout(orientation="vertical", spacing=10)
        der.add_widget(GrupoOpciones("OÍDO", [("D", "Derecho"), ("I", "Izquierdo"), ("DI", "Binaural")], "D",
                                     self._cambiar_oido, colores={"D": ROJO, "I": AZUL, "DI": (0.45, 0.35, 0.7, 1)}))
        der.add_widget(GrupoOpciones("ESTÍMULO (Tone / Warble / NB / N)",
                                     [("tono", "Tono puro"), ("warble", "Warble"), ("nbn", "Ruido NB"),
                                      ("banda_ancha", "Ruido banda ancha")], "tono", self._cambiar_tipo))
        centro.add_widget(der)
        self.add_widget(centro)

        # ----- presentación + enmascaramiento
        fila2 = BoxLayout(spacing=14, size_hint_y=None, height=78)
        fila2.add_widget(GrupoOpciones("PRESENTACIÓN (Single / Multi / continuo)",
                                       [("pulso", "Pulso 1 s"), ("pulsado", "Pulsado"), ("continuo", "Continuo")],
                                       "pulso", self._cambiar_modo))
        fila2.add_widget(GrupoOpciones("ENMASCARAMIENTO (oído contrario)",
                                       [(False, "Apagado"), ("nbn", "NB"), ("banda_ancha", "Banda ancha")],
                                       False, self._cambiar_enm, colores={"nbn": AMBAR, "banda_ancha": AMBAR}))
        self.add_widget(fila2)

        fila3 = BoxLayout(spacing=6, size_hint_y=None, height=50)
        self.lbl_enm = Label(text="", font_size="18sp", color=(1, 0.8, 0.45, 1))
        fila3.add_widget(self.lbl_enm)
        for t, d in [("EM -5", -5), ("EM +5", 5)]:
            b = boton(t, size_hint_x=None, width=120)
            b.bind(on_release=lambda _b, d=d: self._cambiar_enm_nivel(d))
            fila3.add_widget(b)
        self.add_widget(fila3)

        # ----- botón principal
        self.btn = boton("PRESENTAR TONO", VERDE, font_size="28sp", bold=True)
        self.btn.bind(on_release=self._presentar)
        self.add_widget(self.btn)
        self.lbl_estado = Label(text="Conecta los audífonos y sube el volumen de la tableta al 100 %.",
                                color=TEXTO_SUAVE, font_size="15sp", size_hint_y=None, height=28)
        self.add_widget(self.lbl_estado)

        self._listo = True
        self._refrescar()
        Clock.schedule_interval(self._vigilar, 0.1)

    # ---------------------------------------------------------- eventos
    def _cambiar_frecuencia(self, f):
        self.est.frecuencia = f
        self._limitar()

    def _cambiar_oido(self, o):
        self.est.oido = o
        self._limitar()

    def _cambiar_tipo(self, t):
        self.est.tipo = t
        self._refrescar()

    def _cambiar_modo(self, m):
        self.motor.detener()
        self.modo = m
        self._refrescar()

    def _cambiar_enm(self, v):
        self.enm.activo = bool(v)
        if v:
            self.enm.tipo = v
        self._refrescar()

    def _cambiar_nivel(self, d):
        self.est.dbhl += d
        self._limitar()

    def _cambiar_enm_nivel(self, d):
        self.enm.dbem = max(-10, self.enm.dbem + d)
        self._refrescar()

    def _limitar(self):
        maximo = int(self.motor.maximo(self.est.frecuencia, self.est.oido) // 5 * 5)
        self.est.dbhl = max(-10, min(self.est.dbhl, maximo))
        self._refrescar()

    # ------------------------------------------------------- reproducción
    def _presentar(self, *_):
        if self.modo == "continuo" and self.motor.sonando():
            self.motor.detener()
            self._refrescar()
            return
        self.est.pulsado = self.modo == "pulsado"
        self.est.duracion = 3.0 if self.modo == "pulsado" else 1.0
        try:
            self.motor.presentar(self.est, self.enm, continuo=(self.modo == "continuo"))
            self.lbl_estado.text = (f"Sonando: {self.est.frecuencia} Hz · {self.est.dbhl:.0f} dB HL · "
                                    f"oído {self.est.oido}" + (f" · enmasc. {self.enm.dbem:.0f} dB EM"
                                                                if self.enm.activo else ""))
        except NivelFueraDeRango as e:
            self.lbl_estado.text = f"[!] {e}"
        except Exception as e:
            self.lbl_estado.text = f"[ERROR de audio] {type(e).__name__}: {e}"
        self._refrescar()

    def _vigilar(self, _dt):
        sonando = self.motor.sonando()
        if self.modo == "continuo":
            self.btn.text = "DETENER" if sonando else "INICIAR TONO CONTINUO"
            self.btn.background_color = ROJO if sonando else VERDE
        else:
            self.btn.text = "SONANDO..." if sonando else "PRESENTAR TONO"
            self.btn.background_color = AMBAR if sonando else VERDE

    def _refrescar(self):
        if not self._listo:
            return
        maximo = self.motor.maximo(self.est.frecuencia, self.est.oido)
        col = {"D": "ff6b6b", "I": "6ba4ff", "DI": "b39ddb"}[self.est.oido]
        self.lbl_nivel.text = f"[color={col}]{self.est.dbhl:.0f}[/color] [size=26sp]dB HL[/size]"
        self.lbl_max.text = f"Máximo a {self.est.frecuencia} Hz: {maximo:.0f} dB HL"
        self.lbl_enm.text = (f"Enmascaramiento: {self.enm.dbem:.0f} dB EM ({'NB' if self.enm.tipo == 'nbn' else 'banda ancha'})"
                             if self.enm.activo else "Enmascaramiento apagado")
        cal = self.motor.calibracion
        self.lbl_backend.text = f"Audio: {self.motor.reproductor.nombre_backend}\nCalibración: {cal.nombre}"


class UyariyApp(App):
    title = "Uyariy"

    def build(self):
        ruta_cal = os.path.join(self.user_data_dir, "calibracion.json")
        self.motor = MotorAudio(Calibracion.cargar(ruta_cal))
        return BancoAudio(self.motor, ruta_cal)

    def on_pause(self):
        self.motor.detener()
        return True

    def on_stop(self):
        self.motor.detener()


if __name__ == "__main__":
    UyariyApp().run()