"""
Pantalla 3: Audiometría con el aspecto del panel de un audiómetro clínico (Interacoustics AD629 / AC40).

Arriba (bisel negro): la "pantalla LCD" con Canal 1 (dB HL), frecuencia y Canal 2 (enmascaramiento),
los dos audiogramas en vivo con PTA y grado OMS, el veredicto y la línea de estado.
Abajo (placa gris): perilla de INTENSIDAD (canal 1), TONE SWITCH para presentar, teclas con LED
(estímulo, frecuencia, oído, presentación, umbral, enmascaramiento, PARAR) y perilla de
ENMASCARAMIENTO (canal 2).
"""
import time
from datetime import datetime

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.togglebutton import ToggleButton

from .. import __version__
from ..audio.calibracion import NivelFueraDeRango
from ..audio.generador import FRECUENCIAS_ESTANDAR
from ..audio.motor import Enmascaramiento, Estimulo
from ..clinica import clasificacion as C
from ..clinica import seguridad as S
from .audiograma import Audiograma
from .estilo import AMBAR, AZUL, GRIS_BTN, ROJO, TEXTO_SUAVE, VERDE
from .panel import (AMARILLO, AZUL_I, NARANJA, PLACA, ROJO_D, TINTA_PLACA, BotonRedondo, GrupoTeclas,
                    Perilla, Tecla)

# Orden clínico de evaluación: 1 kHz, agudos, luego graves
ORDEN_FRECUENCIAS = [1000, 2000, 3000, 4000, 6000, 8000, 500, 250, 125, 750, 1500]
COLOR_VEREDICTO = {"PASA": VERDE, "CONTROL": (0.85, 0.62, 0.10, 1), "REFERIR": ROJO,
                   "INCOMPLETO": (0.30, 0.32, 0.36, 1)}
NOMBRE_ESTIMULO = {"tono": "Tono puro", "warble": "Warble", "nbn": "Ruido banda estrecha",
                   "banda_ancha": "Ruido banda ancha"}
NOMBRE_MODO = {"pulso": "Pulso 1 s", "pulsado": "Pulsado", "continuo": "Continuo"}
NOMBRE_OIDO_LARGO = {"D": "Derecho", "I": "Izquierdo", "DI": "Binaural"}
BISEL = (0.05, 0.05, 0.06, 1)
BARRA_LCD = (0.15, 0.17, 0.20, 1)


# ---------------------------------------------------------------- utilidades (también las usan otras pantallas)
def fondo(widget, color):
    with widget.canvas.before:
        c = Color(*color)
        r = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, p: setattr(r, "pos", p), size=lambda w, s: setattr(r, "size", s))
    return c


def boton(texto, color=GRIS_BTN, **kw):
    kw.setdefault("font_size", "16sp")
    return Button(text=texto, background_normal="", background_color=color, **kw)


def texto(t="", tam="14sp", color=TEXTO_SUAVE, **kw):
    lb = Label(text=t, markup=True, font_size=tam, color=color, halign="center", valign="middle", **kw)
    lb.bind(size=lambda w, s: setattr(w, "text_size", s))
    return lb


def _hex(color):
    return "%02x%02x%02x" % tuple(int(c * 255) for c in color[:3])


class GrupoOpciones(BoxLayout):
    """Fila de botones de selección única (la usa la pantalla automática)."""

    def __init__(self, titulo, opciones, inicial, al_cambiar, colores=None, **kw):
        super().__init__(orientation="vertical", spacing=dp(2), **kw)
        self.al_cambiar = al_cambiar
        self.colores = colores or {}
        self.add_widget(texto(titulo, "12sp", size_hint_y=None, height=dp(16)))
        fila = BoxLayout(spacing=dp(3))
        self.botones = {}
        for valor, etiqueta in opciones:
            b = ToggleButton(text=etiqueta, group=f"g_{titulo}", allow_no_selection=False, background_normal="",
                             background_down="", font_size="14sp")
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

    def elegir(self, valor):
        for v, b in self.botones.items():
            if v != valor:
                b.state = "normal"
        if self.botones[valor].state == "down":
            self.al_cambiar(valor)
        else:
            self.botones[valor].state = "down"


def serigrafia(t, alto=dp(16), tam="11sp"):
    """Texto impreso en la placa del equipo."""
    return texto(f"[b]{t}[/b]", tam, TINTA_PLACA, size_hint_y=None, height=alto)


def bloque(titulo, teclas, peso=1):
    """Grupo de teclas con su rótulo encima, como en el panel del audiómetro."""
    caja = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=peso)
    caja.add_widget(serigrafia(titulo))
    fila = BoxLayout(spacing=dp(6))
    for t in teclas:
        fila.add_widget(t)
    caja.add_widget(fila)
    return caja


# ---------------------------------------------------------------- consola
class BancoAudio(BoxLayout):
    def __init__(self, motor, al_volver=None, al_guardar=None, al_auto=None, **kw):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), **kw)
        fondo(self, (0.12, 0.13, 0.14, 1))
        self.motor = motor
        self.al_volver = al_volver
        self.al_guardar = al_guardar            # función(codigo, resultados) -> bool
        self.al_auto = al_auto                  # abre la audiometría automática
        self.metodo, self.fiabilidad = "manual", None
        self.alto_confirmado = False            # el evaluador aceptó pasar de 80 dB HL
        self.expo = S.Exposicion()              # registro de exposición sonora
        self._inicio_continuo, self._ev_continuo = None, None
        self._popup = False
        self.est = Estimulo(frecuencia=1000, dbhl=30, oido="D", tipo="tono", duracion=1.0)
        self.enm = Enmascaramiento(activo=False, dbem=40, tipo="nbn")
        self.modo = "pulso"
        self.paciente, self.codigo = {}, None
        self.umbrales = {"D": {}, "I": {}}
        self._listo = False

        # ----- cabecera
        cab = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        volver = boton("<  Paciente", size_hint_x=None, width=dp(120))
        volver.bind(on_release=self._volver)
        self.lbl_paciente = texto(f"[b]UYARIY[/b]  ·  Audiometría  ·  v{__version__}", "15sp", (1, 1, 1, 1))
        self.lbl_paciente.halign = "left"
        self.btn_auto = boton("AUTOMÁTICO", NARANJA, bold=True, size_hint_x=None, width=dp(150))
        self.btn_auto.color = (0.15, 0.10, 0.02, 1)
        self.btn_auto.bind(on_release=self._abrir_auto)
        self.btn_guardar_todo = boton("Guardar resultados", AZUL, bold=True, size_hint_x=None, width=dp(200))
        self.btn_guardar_todo.bind(on_release=self._guardar_resultados)
        for w in (volver, self.lbl_paciente, self.btn_auto, self.btn_guardar_todo):
            cab.add_widget(w)
        self.add_widget(cab)

        # ----- bisel negro con la "pantalla LCD"
        bisel = BoxLayout(padding=dp(10))
        fondo(bisel, BISEL)
        lcd = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(4))
        fondo(lcd, (0.96, 0.97, 0.97, 1))

        barra = BoxLayout(size_hint_y=None, height=dp(54), padding=(dp(12), 0), spacing=dp(10))
        fondo(barra, BARRA_LCD)
        self.lbl_ch1 = texto("", "14sp", (1, 1, 1, 1))
        self.lbl_ch1.halign = "left"
        self.lbl_frec = texto("", "14sp", (1, 1, 1, 1))
        self.lbl_ch2 = texto("", "14sp", (1, 1, 1, 1))
        self.lbl_ch2.halign = "right"
        for w in (self.lbl_ch1, self.lbl_frec, self.lbl_ch2):
            barra.add_widget(w)
        lcd.add_widget(barra)

        graficos = BoxLayout(spacing=dp(6))
        self.audiogramas, self.lbl_pta = {}, {}
        for o, col in (("D", ROJO), ("I", AZUL)):
            caja = BoxLayout(orientation="vertical", spacing=dp(2))
            self.lbl_pta[o] = texto("", "13sp", (1, 1, 1, 1), size_hint_y=None, height=dp(22))
            self.lbl_pta[o].fondo = fondo(self.lbl_pta[o], col)
            self.audiogramas[o] = Audiograma(o)
            self.audiogramas[o].limite = lambda f, o=o: self.motor.maximo(f, o)   # zona gris del equipo
            caja.add_widget(self.lbl_pta[o])
            caja.add_widget(self.audiogramas[o])
            graficos.add_widget(caja)
        lcd.add_widget(graficos)

        self.lbl_veredicto = texto("", "14sp", (1, 1, 1, 1), size_hint_y=None, height=dp(26))
        self.fondo_veredicto = fondo(self.lbl_veredicto, COLOR_VEREDICTO["INCOMPLETO"])
        lcd.add_widget(self.lbl_veredicto)
        self.lbl_estado = texto("Conecta los audífonos y sube el volumen de la tableta al 100 %.", "13sp",
                                (0.20, 0.24, 0.28, 1), size_hint_y=None, height=dp(18))
        lcd.add_widget(self.lbl_estado)
        bisel.add_widget(lcd)
        self.add_widget(bisel)

        # ----- placa del equipo
        placa = BoxLayout(size_hint_y=None, height=dp(286), padding=(dp(14), dp(10)), spacing=dp(14))
        fondo(placa, PLACA)

        # perilla de intensidad (canal 1)
        izq = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=None, width=dp(190))
        izq.add_widget(serigrafia("INTENSIDAD  ·  CANAL 1 (dB HL)"))
        self.perilla_nivel = Perilla(self._girar_nivel)
        izq.add_widget(self.perilla_nivel)
        fila = BoxLayout(spacing=dp(4), size_hint_y=None, height=dp(34))
        for t, d in [("-10", -10), ("-5", -5), ("+5", 5), ("+10", 10)]:
            b = Tecla(t, led=False, tam="14sp")
            b.bind(on_release=lambda _b, d=d: self._cambiar_nivel(d))
            fila.add_widget(b)
        izq.add_widget(fila)
        placa.add_widget(izq)

        # tone switch
        tono = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=None, width=dp(130))
        tono.add_widget(serigrafia("TONE SWITCH"))
        ancla = AnchorLayout()
        self.tone_switch = BotonRedondo(size_hint=(None, None), size=(dp(112), dp(112)))
        self.tone_switch.bind(on_release=self._presentar)
        ancla.add_widget(self.tone_switch)
        tono.add_widget(ancla)
        self.lbl_tono = serigrafia("PRESENTAR", dp(34), "14sp")
        tono.add_widget(self.lbl_tono)
        placa.add_widget(tono)

        # teclas centrales
        centro = BoxLayout(orientation="vertical", spacing=dp(8))
        self.grupo_tipo = GrupoTeclas([("tono", "Tono"), ("warble", "Warble"), ("nbn", "Ruido NB"),
                                       ("banda_ancha", "Banda ancha")], "tono", self._cambiar_tipo, tam="14sp")
        f_menos, f_mas = Tecla("Frec  -", tam="15sp"), Tecla("Frec  +", tam="15sp")
        f_menos.bind(on_release=lambda *_: self._mover_frecuencia(-1))
        f_mas.bind(on_release=lambda *_: self._mover_frecuencia(1))
        fila1 = BoxLayout(spacing=dp(12))
        fila1.add_widget(bloque("ESTÍMULO", self.grupo_tipo.teclas.values(), 4))
        fila1.add_widget(bloque("FRECUENCIA", [f_menos, f_mas], 2))
        centro.add_widget(fila1)

        self.grupo_oido = GrupoTeclas([("D", "Derecho"), ("I", "Izquierdo"), ("DI", "Binaural")], "D",
                                      self._cambiar_oido, colores={"D": ROJO_D, "I": AZUL_I}, tam="14sp")
        self.grupo_modo = GrupoTeclas([("pulso", "Pulso 1 s"), ("pulsado", "Pulsado"), ("continuo", "Continuo")],
                                      "pulso", self._cambiar_modo, tam="14sp")
        fila2 = BoxLayout(spacing=dp(12))
        fila2.add_widget(bloque("OÍDO", self.grupo_oido.teclas.values(), 3))
        fila2.add_widget(bloque("PRESENTACIÓN", self.grupo_modo.teclas.values(), 3))
        centro.add_widget(fila2)

        store = Tecla("GUARDAR\nUMBRAL", AMARILLO, (0.20, 0.17, 0.05, 1), tam="13sp")
        store.bind(on_release=lambda *_: self._guardar_umbral(nr=False))
        no_resp = Tecla("Sin\nrespuesta", tam="13sp")
        no_resp.bind(on_release=lambda *_: self._guardar_umbral(nr=True))
        borrar = Tecla("Borrar\npunto", tam="13sp")
        borrar.bind(on_release=self._borrar_umbral)
        self.mask = {"nbn": Tecla("Mask NB", tam="14sp"), "banda_ancha": Tecla("Mask BA", tam="14sp")}
        for tipo, t in self.mask.items():
            t.bind(on_release=lambda _t, tipo=tipo: self._alternar_mask(tipo))
        parar = Tecla("PARAR", ROJO_D, tam="16sp")
        parar.bind(on_release=lambda *_: self._parar())          # botón de pánico: corta todo el sonido
        fila3 = BoxLayout(spacing=dp(12))
        fila3.add_widget(bloque("UMBRAL", [store, no_resp, borrar], 3))
        fila3.add_widget(bloque("ENMASCARAMIENTO", self.mask.values(), 2))
        fila3.add_widget(bloque("SEGURIDAD", [parar], 1))
        centro.add_widget(fila3)
        placa.add_widget(centro)

        # perilla de enmascaramiento (canal 2)
        der = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=None, width=dp(190))
        der.add_widget(serigrafia("ENMASCARAMIENTO  ·  CANAL 2"))
        self.perilla_enm = Perilla(lambda paso: self._cambiar_enm_nivel(5 * paso))
        der.add_widget(self.perilla_enm)
        fila_em = BoxLayout(spacing=dp(4), size_hint_y=None, height=dp(34))
        for t, d in [("EM -5", -5), ("EM +5", 5)]:
            b = Tecla(t, led=False, tam="14sp")
            b.bind(on_release=lambda _b, d=d: self._cambiar_enm_nivel(d))
            fila_em.add_widget(b)
        der.add_widget(fila_em)
        placa.add_widget(der)
        self.add_widget(placa)

        self._listo = True
        self._refrescar()
        Clock.schedule_interval(self._vigilar, 0.1)

    # ---------------------------------------------------------- eventos
    def _cambiar_frecuencia(self, f):
        self.est.frecuencia = f
        self._inicio_seguro()
        self._limitar()

    def _elegir_frecuencia(self, f):
        self._cambiar_frecuencia(f)

    def _mover_frecuencia(self, paso):
        lista = FRECUENCIAS_ESTANDAR
        i = lista.index(self.est.frecuencia) if self.est.frecuencia in lista else lista.index(1000)
        nueva = lista[max(0, min(len(lista) - 1, i + paso))]
        if nueva != self.est.frecuencia:
            self._elegir_frecuencia(nueva)

    def _cambiar_oido(self, o):
        self.est.oido = o
        self._inicio_seguro()
        self._limitar()

    def _inicio_seguro(self):
        """Al cambiar de frecuencia u oído, un nivel alto vuelve a 40 dB HL (seguridad)."""
        self._parar(silencioso=True)
        nuevo = S.nivel_al_cambiar(self.est.dbhl)
        if nuevo != self.est.dbhl:
            self.est.dbhl = nuevo
            self.estado(f"Seguridad: el nivel vuelve a {nuevo} dB HL al cambiar de frecuencia u oído.")
        self.alto_confirmado = False

    def _cambiar_tipo(self, t):
        self.est.tipo = t
        self._refrescar()

    def _cambiar_modo(self, m):
        self._parar(silencioso=True)
        self.modo = m
        self._refrescar()

    def _alternar_mask(self, tipo):
        """Mask NB / Mask BA: la misma tecla otra vez apaga el enmascaramiento."""
        if self.enm.activo and self.enm.tipo == tipo:
            self.enm.activo = False
        else:
            self.enm.activo, self.enm.tipo = True, tipo
        self._refrescar()

    def _girar_nivel(self, paso):
        if not self._popup:
            self._cambiar_nivel(5 * paso)

    def _cambiar_nivel(self, d):
        d = S.paso_permitido(self.est.dbhl, d)
        nuevo = self.est.dbhl + d
        if S.necesita_confirmacion(nuevo, self.alto_confirmado):
            self._confirmar_alto(nuevo)
            return
        self.est.dbhl = nuevo
        self._limitar()

    def _confirmar_alto(self, nuevo):
        """Pide confirmación antes de pasar el límite seguro de 80 dB HL."""
        if self._popup:
            return
        caja = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
        caja.add_widget(texto(f"Va a subir a [b]{nuevo} dB HL[/b], por encima del límite seguro de "
                              f"{S.LIMITE_SEGURO} dB HL.\n\nUse niveles altos solo si el paciente no respondió "
                              "antes y pídale que levante la mano o se quite los audífonos si le molesta.",
                              "16sp", (1, 1, 1, 1)))
        fila = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        si = boton("Sí, subir con cuidado", ROJO, bold=True)
        no = boton("Cancelar", GRIS_BTN)
        fila.add_widget(no)
        fila.add_widget(si)
        caja.add_widget(fila)
        pop = Popup(title="(!) Nivel alto", content=caja, size_hint=(0.6, 0.5), auto_dismiss=False)
        self._popup = True
        pop.bind(on_dismiss=lambda *_: setattr(self, "_popup", False))

        def aceptar(*_):
            self.alto_confirmado = True
            self.est.dbhl = nuevo
            pop.dismiss()
            self._limitar()
        si.bind(on_release=aceptar)
        no.bind(on_release=lambda *_: pop.dismiss())
        pop.open()

    def _cambiar_enm_nivel(self, d):
        self.enm.dbem = max(-10, min(self.enm.dbem + d, S.MAX_ENMASCARAMIENTO))
        if self.enm.dbem == S.MAX_ENMASCARAMIENTO and d > 0:
            self.estado(f"Seguridad: el enmascaramiento máximo es {S.MAX_ENMASCARAMIENTO} dB EM.")
        self._refrescar()

    def _limitar(self):
        maximo = int(self.motor.maximo(self.est.frecuencia, self.est.oido) // 5 * 5)
        self.est.dbhl = max(-10, min(self.est.dbhl, maximo))
        self._refrescar()

    # ------------------------------------------------------- reproducción
    def _presentar(self, *_):
        continuo = self.modo == "continuo"
        if continuo and self.motor.sonando():
            self._parar()
            return
        if continuo and self.est.dbhl > S.LIMITE_SEGURO:
            self.estado(f"Seguridad: el tono continuo no se permite por encima de {S.LIMITE_SEGURO} dB HL. "
                        "Use Pulso o Pulsado.")
            return
        self.est.pulsado = self.modo == "pulsado"
        self.est.duracion = 3.0 if self.modo == "pulsado" else 1.0
        try:
            self.motor.presentar(self.est, self.enm, continuo=continuo)
            if continuo:                       # se apaga solo a los 10 s
                self._inicio_continuo = time.time()
                self._ev_continuo = Clock.schedule_once(lambda dt: self._parar(aviso="Continuo detenido a los "
                                                        f"{S.MAX_CONTINUO_S} s (seguridad)."), S.MAX_CONTINUO_S)
            else:
                self.expo.registrar(self._nivel_expuesto(), self.est.duracion)
            self.estado(f"Sonando: {self.est.frecuencia} Hz · {self.est.dbhl:.0f} dB HL · oído {self.est.oido}"
                        + (f" · enmasc. {self.enm.dbem:.0f} dB EM" if self.enm.activo else ""))
        except NivelFueraDeRango as e:
            self.estado(f"[!] {e}")
        except Exception as e:
            self.estado(f"[ERROR de audio] {type(e).__name__}: {e}")
        self._refrescar()

    def _nivel_expuesto(self):
        return max(self.est.dbhl, self.enm.dbem if self.enm.activo else -99)

    def _parar(self, aviso="Sonido detenido.", silencioso=False):
        """Botón de pánico: corta todo el sonido al instante."""
        self.motor.detener()
        if self._ev_continuo:
            self._ev_continuo.cancel()
            self._ev_continuo = None
        if self._inicio_continuo:
            self.expo.registrar(self._nivel_expuesto(), time.time() - self._inicio_continuo)
            self._inicio_continuo = None
        if not silencioso:
            self.estado(aviso)
            self._refrescar()

    def _vigilar(self, _dt):
        sonando = self.motor.sonando()
        self.tone_switch.encendido = sonando
        if self.modo == "continuo":
            self.lbl_tono.text = "[b]DETENER[/b]" if sonando else "[b]INICIAR CONTINUO[/b]"
        else:
            self.lbl_tono.text = "[b][color=c77700]SONANDO...[/color][/b]" if sonando else "[b]PRESENTAR[/b]"

    # ------------------------------------------------------- umbrales
    def _guardar_umbral(self, nr=False):
        o, f = self.est.oido, self.est.frecuencia
        if o == "DI":
            self.estado("[!] Elige oído Derecho o Izquierdo para guardar el umbral (no Binaural).")
            return
        if nr:
            self.est.dbhl = int(self.motor.maximo(f, o) // 5 * 5)
        self.umbrales[o][f] = C.Umbral(db=self.est.dbhl, enmascarado=self.enm.activo, nr=nr)
        self.estado(f"Umbral guardado: oído {C.NOMBRE_OIDO[o]}, {f} Hz = {self.est.dbhl:.0f} dB HL"
                    + (" (sin respuesta)" if nr else "") + (" · enmascarado" if self.enm.activo else ""))
        self._siguiente_frecuencia()
        self._refrescar()

    def _borrar_umbral(self, *_):
        o, f = self.est.oido, self.est.frecuencia
        if o in self.umbrales and self.umbrales[o].pop(f, None):
            self.estado(f"Punto borrado: oído {C.NOMBRE_OIDO[o]}, {f} Hz")
        else:
            self.estado("No hay punto guardado en esta frecuencia y oído.")
        self._refrescar()

    def _siguiente_frecuencia(self):
        """Salta a la siguiente frecuencia sin medir (orden clínico), como el AC40."""
        hechos = self.umbrales[self.est.oido]
        i = ORDEN_FRECUENCIAS.index(self.est.frecuencia) if self.est.frecuencia in ORDEN_FRECUENCIAS else -1
        for f in ORDEN_FRECUENCIAS[i + 1:] + ORDEN_FRECUENCIAS[:i + 1]:
            if f not in hechos and f in (125, 250, 500, 1000, 2000, 3000, 4000, 6000, 8000):
                self._elegir_frecuencia(f)
                return

    def resultado(self):
        r = C.evaluar(self.umbrales["D"], self.umbrales["I"], self.paciente.get("edad"),
                      self.paciente.get("antecedentes", []))
        if self.fiabilidad and not self.fiabilidad["confiable"]:
            r["avisos"] = r["avisos"] + ["Poco confiable: " + "; ".join(self.fiabilidad["mensajes"])]
        return r

    # ------------------------------------------------------- automático
    def _abrir_auto(self, *_):
        self.motor.detener()
        if not self.codigo:
            self.estado("[!] Primero registra un paciente.")
            return
        if self.al_auto:
            self.al_auto()

    def cargar_automatico(self, umbrales, info):
        """Recibe los umbrales de la prueba automática para revisarlos y guardarlos."""
        for o in ("D", "I"):
            self.umbrales[o].update(umbrales.get(o, {}))
        self.metodo, self.fiabilidad = "automatico", info
        self.estado("Resultado de la prueba automática cargado. Revise el audiograma y presione Guardar resultados."
                    + ("" if info["confiable"] else "  (!) " + "; ".join(info["mensajes"])))
        self._refrescar()

    def _guardar_resultados(self, *_):
        if not self.codigo:
            self.estado("[!] Primero registra un paciente.")
            return
        r = self.resultado()
        datos = dict(r, umbrales={o: C.a_json(u) for o, u in self.umbrales.items()},
                     estimulo=self.est.tipo, calibracion=self.motor.calibracion.nombre,
                     metodo=self.metodo, fiabilidad=self.fiabilidad, exposicion=self.expo.a_dict(),
                     fecha=datetime.now().isoformat(timespec="minutes"))
        ok = self.al_guardar(self.codigo, datos) if self.al_guardar else False
        self.estado(f"Resultados guardados en {self.codigo}: {r['veredicto']}" if ok else "[!] No se pudo guardar.")

    # ------------------------------------------------------- pantalla
    def estado(self, t):
        if hasattr(self, "lbl_estado"):
            self.lbl_estado.text = t

    def _refrescar(self):
        if not self._listo:
            return
        maximo = self.motor.maximo(self.est.frecuencia, self.est.oido)
        riesgo = _hex(S.color_nivel(self.est.dbhl))
        etiqueta = ("NIVEL ALTO" if self.est.dbhl >= S.NIVEL_PELIGRO else
                    "PRECAUCIÓN" if self.est.dbhl >= S.NIVEL_AVISO else "SEGURO")
        col_oido = {"D": "ff7070", "I": "70a8ff", "DI": "c3a6ff"}[self.est.oido]
        self.lbl_ch1.text = (f"[size=30sp][b][color={riesgo}]{self.est.dbhl:.0f}[/color][/b][/size] dB HL   "
                             f"[color={col_oido}][b]{NOMBRE_OIDO_LARGO[self.est.oido]}[/b][/color]\n"
                             f"[size=11sp][color={riesgo}]{etiqueta}[/color] · límite {S.LIMITE_SEGURO} · "
                             f"máx. equipo {maximo:.0f}[/size]")
        f = self.est.frecuencia
        self.lbl_frec.text = (f"[size=26sp][b]{f} Hz[/b][/size]\n[size=11sp]{NOMBRE_ESTIMULO[self.est.tipo]}  ·  "
                              f"{NOMBRE_MODO[self.modo]}[/size]")
        self.lbl_ch2.text = ((f"[size=26sp][b][color=ffc35a]{self.enm.dbem:.0f}[/color][/b][/size] dB EM\n"
                              f"[size=11sp]Canal 2 · enmascaramiento "
                              f"{'NB' if self.enm.tipo == 'nbn' else 'BA'}[/size]") if self.enm.activo else
                             f"[size=26sp][b][color=8a96a3]--[/color][/b][/size] dB EM\n"
                             f"[size=11sp]Canal 2 · apagado ({self.enm.dbem:.0f})[/size]")
        for tipo, t in self.mask.items():
            t.encender(self.enm.activo and self.enm.tipo == tipo)
        for o in ("D", "I"):
            cursor = (self.est.frecuencia, self.est.dbhl) if self.est.oido in (o, "DI") else None
            self.audiogramas[o].actualizar(self.umbrales[o], cursor, self.est.tipo)
        r = self.resultado()
        for o in ("D", "I"):
            p = r["pta"][o]
            nombre, color = C.grado(p)
            faltan = [fr for fr in C.FRECUENCIAS_PTA if fr not in self.umbrales[o]]
            detalle = (f"PTA {p:.0f} dB HL  ·  {nombre}" if p is not None else
                       "PTA: faltan " + ", ".join(str(fr) for fr in faltan) + " Hz")
            self.lbl_pta[o].text = f"[b]{'OÍDO DERECHO' if o == 'D' else 'OÍDO IZQUIERDO'}[/b]   ·   {detalle}"
            self.lbl_pta[o].fondo.rgba = color if p is not None else (ROJO if o == "D" else AZUL)
        texto_v = f"[b]{r['veredicto']}[/b]  ·  " + "  ·  ".join(r["motivos"])
        if r["avisos"]:
            texto_v += "   [color=ffe08a](!) " + "; ".join(r["avisos"]) + "[/color]"
        self.lbl_veredicto.text = texto_v
        self.fondo_veredicto.rgba = COLOR_VEREDICTO[r["veredicto"]]

    def mostrar_paciente(self, p, codigo):
        self.paciente, self.codigo = p, codigo
        self.umbrales = {"D": {}, "I": {}}
        self.metodo, self.fiabilidad = "manual", None
        self._parar(silencioso=True)
        self.expo = S.Exposicion()
        self.alto_confirmado = False
        self.est.dbhl = 30                     # siempre empieza en un nivel seguro
        nombre = f"{p['nombres']} {p.get('ap_paterno', '')} {p.get('ap_materno', '')}".split()
        self.lbl_paciente.text = (f"[b]{' '.join(nombre)}[/b]  ·  {p.get('edad', '')} años  ·  "
                                  f"{'Femenino' if p.get('sexo') == 'F' else 'Masculino'}\n"
                                  f"[color=8fa0b0]C.I. {p['ci']} {p.get('ci_ext', '')}  ·  {codigo}  ·  "
                                  f"Audio: {self.motor.reproductor.nombre_backend}  ·  v{__version__}[/color]")
        self.grupo_oido.elegir("D")
        self._elegir_frecuencia(1000)
        self.estado("Empieza en 1000 Hz, oído derecho. Gire la perilla, presione el TONE SWITCH y, cuando "
                    "el paciente responda, GUARDAR UMBRAL.")
        self._refrescar()

    def _volver(self, *_):
        self._parar(silencioso=True)
        if self.al_volver:
            self.al_volver()


class PantallaAudio(Screen):
    def __init__(self, motor, al_volver, al_guardar=None, al_auto=None, **kw):
        super().__init__(**kw)
        self.banco = BancoAudio(motor, al_volver, al_guardar, al_auto)
        self.add_widget(self.banco)

    def on_leave(self, *_):
        self.banco.motor.detener()
