"""
Pantalla 3: Audiometría (consola del audiómetro + audiograma en vivo).

Arriba: frecuencias. Centro: audiogramas derecho e izquierdo que se dibujan en vivo,
con su promedio tonal (PTA) y grado OMS. Abajo: nivel, oído, estímulo, presentación,
enmascaramiento y los botones PRESENTAR / GUARDAR UMBRAL / SIN RESPUESTA / BORRAR.
"""
from datetime import datetime

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.togglebutton import ToggleButton

from .. import __version__
from ..audio.calibracion import NivelFueraDeRango
from ..audio.generador import FRECUENCIAS_ESTANDAR
from ..audio.motor import Enmascaramiento, Estimulo
from ..clinica import clasificacion as C
from .audiograma import Audiograma
from .estilo import AMBAR, AZUL, FONDO, GRIS_BTN, PANEL, ROJO, TEXTO_SUAVE, VERDE

# Orden clínico de evaluación: 1 kHz, agudos, luego graves
ORDEN_FRECUENCIAS = [1000, 2000, 3000, 4000, 6000, 8000, 500, 250, 125, 750, 1500]
COLOR_VEREDICTO = {"PASA": VERDE, "CONTROL": (0.85, 0.62, 0.10, 1), "REFERIR": ROJO,
                   "INCOMPLETO": (0.30, 0.32, 0.36, 1)}


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


class GrupoOpciones(BoxLayout):
    """Fila de botones de selección única (como los botones con LED del audiómetro)."""

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
        """Selecciona un botón desde el código (Kivy no suelta los demás del grupo por sí solo)."""
        for v, b in self.botones.items():
            if v != valor:
                b.state = "normal"
        if self.botones[valor].state == "down":
            self.al_cambiar(valor)
        else:
            self.botones[valor].state = "down"


class BancoAudio(BoxLayout):
    def __init__(self, motor, al_volver=None, al_guardar=None, **kw):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), **kw)
        fondo(self, FONDO)
        self.motor = motor
        self.al_volver = al_volver
        self.al_guardar = al_guardar            # función(codigo, resultados) -> bool
        self.est = Estimulo(frecuencia=1000, dbhl=30, oido="D", tipo="tono", duracion=1.0)
        self.enm = Enmascaramiento(activo=False, dbem=40, tipo="nbn")
        self.modo = "pulso"
        self.paciente, self.codigo = {}, None
        self.umbrales = {"D": {}, "I": {}}
        self._listo = False

        # ----- cabecera
        cab = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        volver = boton("<  Paciente", size_hint_x=None, width=dp(120))
        volver.bind(on_release=self._volver)
        self.lbl_paciente = texto(f"[b]UYARIY[/b]  ·  Audiometría  ·  v{__version__}", "16sp", (1, 1, 1, 1))
        self.lbl_paciente.halign = "left"
        self.btn_guardar_todo = boton("Guardar resultados", AZUL, bold=True, size_hint_x=None, width=dp(200))
        self.btn_guardar_todo.bind(on_release=self._guardar_resultados)
        for w in (volver, self.lbl_paciente, self.btn_guardar_todo):
            cab.add_widget(w)
        self.add_widget(cab)

        # ----- frecuencias
        self.grupo_f = GrupoOpciones(
            "FRECUENCIA (Hz)",
            [(f, f"{f / 1000:g}k" if f >= 1000 else str(f)) for f in FRECUENCIAS_ESTANDAR],
            1000, self._cambiar_frecuencia, colores={f: (0.12, 0.55, 0.75, 1) for f in FRECUENCIAS_ESTANDAR},
            size_hint_y=None, height=dp(56))
        self.add_widget(self.grupo_f)

        # ----- audiogramas en vivo
        graficos = BoxLayout(spacing=dp(10))
        self.audiogramas, self.lbl_pta = {}, {}
        for o, nombre, col in (("D", "OÍDO DERECHO", ROJO), ("I", "OÍDO IZQUIERDO", AZUL)):
            caja = BoxLayout(orientation="vertical", spacing=dp(2))
            self.lbl_pta[o] = texto("", "14sp", (1, 1, 1, 1), size_hint_y=None, height=dp(24))
            self.lbl_pta[o].fondo = fondo(self.lbl_pta[o], col)
            self.audiogramas[o] = Audiograma(o)
            self.audiogramas[o].limite = lambda f, o=o: self.motor.maximo(f, o)   # zona gris del equipo
            caja.add_widget(self.lbl_pta[o])
            caja.add_widget(self.audiogramas[o])
            graficos.add_widget(caja)
        self.add_widget(graficos)

        # ----- veredicto
        self.lbl_veredicto = texto("", "15sp", (1, 1, 1, 1), size_hint_y=None, height=dp(30))
        self.fondo_veredicto = fondo(self.lbl_veredicto, COLOR_VEREDICTO["INCOMPLETO"])
        self.add_widget(self.lbl_veredicto)

        # ----- controles
        ctrl = BoxLayout(size_hint_y=None, height=dp(118), spacing=dp(8))
        nivel = BoxLayout(orientation="vertical", padding=dp(4), spacing=dp(3), size_hint_x=0.27)
        fondo(nivel, PANEL)
        self.lbl_nivel = Label(text="", markup=True, font_size="38sp", bold=True)
        nivel.add_widget(self.lbl_nivel)
        fila = BoxLayout(spacing=dp(3), size_hint_y=None, height=dp(40))
        for t, d in [("-10", -10), ("-5", -5), ("+5", 5), ("+10", 10)]:
            b = boton(t, font_size="18sp")
            b.bind(on_release=lambda _b, d=d: self._cambiar_nivel(d))
            fila.add_widget(b)
        nivel.add_widget(fila)
        self.lbl_max = texto("", "11sp", size_hint_y=None, height=dp(14))
        nivel.add_widget(self.lbl_max)
        ctrl.add_widget(nivel)

        medio = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=0.38)
        medio.add_widget(GrupoOpciones("OÍDO", [("D", "Derecho"), ("I", "Izquierdo"), ("DI", "Binaural")], "D",
                                       self._cambiar_oido,
                                       colores={"D": ROJO, "I": AZUL, "DI": (0.45, 0.35, 0.7, 1)}))
        medio.add_widget(GrupoOpciones("ESTÍMULO", [("tono", "Tono"), ("warble", "Warble"), ("nbn", "Ruido NB"),
                                                    ("banda_ancha", "Banda ancha")], "tono", self._cambiar_tipo))
        ctrl.add_widget(medio)

        der = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=0.35)
        der.add_widget(GrupoOpciones("PRESENTACIÓN", [("pulso", "Pulso 1 s"), ("pulsado", "Pulsado"),
                                                      ("continuo", "Continuo")], "pulso", self._cambiar_modo))
        enm = BoxLayout(spacing=dp(3))
        enm.add_widget(GrupoOpciones("ENMASCARAMIENTO",
                                     [(False, "No"), ("nbn", "NB"), ("banda_ancha", "BA")], False,
                                     self._cambiar_enm, colores={"nbn": AMBAR, "banda_ancha": AMBAR}))
        caja_em = BoxLayout(orientation="vertical", size_hint_x=0.45, spacing=dp(2))
        self.lbl_enm = texto("", "12sp", (1, 0.8, 0.45, 1), size_hint_y=None, height=dp(16))
        caja_em.add_widget(self.lbl_enm)
        fila_em = BoxLayout(spacing=dp(3))
        for t, d in [("EM-5", -5), ("EM+5", 5)]:
            b = boton(t, font_size="14sp")
            b.bind(on_release=lambda _b, d=d: self._cambiar_enm_nivel(d))
            fila_em.add_widget(b)
        caja_em.add_widget(fila_em)
        enm.add_widget(caja_em)
        der.add_widget(enm)
        ctrl.add_widget(der)
        self.add_widget(ctrl)

        # ----- botones principales
        acciones = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        self.btn = boton("PRESENTAR TONO", VERDE, font_size="22sp", bold=True, size_hint_x=0.40)
        self.btn.bind(on_release=self._presentar)
        b_umbral = boton("GUARDAR UMBRAL", (0.10, 0.45, 0.70, 1), font_size="17sp", bold=True, size_hint_x=0.25)
        b_umbral.bind(on_release=lambda *_: self._guardar_umbral(nr=False))
        b_nr = boton("Sin respuesta", GRIS_BTN, font_size="15sp", size_hint_x=0.18)
        b_nr.bind(on_release=lambda *_: self._guardar_umbral(nr=True))
        b_borrar = boton("Borrar punto", GRIS_BTN, font_size="15sp", size_hint_x=0.17)
        b_borrar.bind(on_release=self._borrar_umbral)
        for w in (self.btn, b_umbral, b_nr, b_borrar):
            acciones.add_widget(w)
        self.add_widget(acciones)

        self.lbl_estado = texto("Conecta los audífonos y sube el volumen de la tableta al 100 %.", "13sp",
                                size_hint_y=None, height=dp(18))
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
            self.estado(f"Sonando: {self.est.frecuencia} Hz · {self.est.dbhl:.0f} dB HL · oído {self.est.oido}"
                        + (f" · enmasc. {self.enm.dbem:.0f} dB EM" if self.enm.activo else ""))
        except NivelFueraDeRango as e:
            self.estado(f"[!] {e}")
        except Exception as e:
            self.estado(f"[ERROR de audio] {type(e).__name__}: {e}")
        self._refrescar()

    def _vigilar(self, _dt):
        sonando = self.motor.sonando()
        if self.modo == "continuo":
            self.btn.text = "DETENER" if sonando else "INICIAR CONTINUO"
            self.btn.background_color = ROJO if sonando else VERDE
        else:
            self.btn.text = "SONANDO..." if sonando else "PRESENTAR TONO"
            self.btn.background_color = AMBAR if sonando else VERDE

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
                self.grupo_f.elegir(f)
                return

    def resultado(self):
        return C.evaluar(self.umbrales["D"], self.umbrales["I"], self.paciente.get("edad"),
                         self.paciente.get("antecedentes", []))

    def _guardar_resultados(self, *_):
        if not self.codigo:
            self.estado("[!] Primero registra un paciente.")
            return
        r = self.resultado()
        datos = dict(r, umbrales={o: C.a_json(u) for o, u in self.umbrales.items()},
                     estimulo=self.est.tipo, calibracion=self.motor.calibracion.nombre,
                     fecha=datetime.now().isoformat(timespec="minutes"))
        ok = self.al_guardar(self.codigo, datos) if self.al_guardar else False
        self.estado(f"Resultados guardados en {self.codigo}: {r['veredicto']}" if ok else "[!] No se pudo guardar.")

    # ------------------------------------------------------- pantalla
    def estado(self, t):
        self.lbl_estado.text = t

    def _refrescar(self):
        if not self._listo:
            return
        maximo = self.motor.maximo(self.est.frecuencia, self.est.oido)
        col = {"D": "ff6b6b", "I": "6ba4ff", "DI": "b39ddb"}[self.est.oido]
        self.lbl_nivel.text = f"[color={col}]{self.est.dbhl:.0f}[/color] [size=20sp]dB HL[/size]"
        self.lbl_max.text = f"Máximo a {self.est.frecuencia} Hz: {maximo:.0f} dB HL"
        self.lbl_enm.text = f"{self.enm.dbem:.0f} dB EM" if self.enm.activo else "apagado"
        for o in ("D", "I"):
            cursor = (self.est.frecuencia, self.est.dbhl) if self.est.oido in (o, "DI") else None
            self.audiogramas[o].actualizar(self.umbrales[o], cursor, self.est.tipo)
        r = self.resultado()
        for o in ("D", "I"):
            p = r["pta"][o]
            nombre, color = C.grado(p)
            faltan = [f for f in C.FRECUENCIAS_PTA if f not in self.umbrales[o]]
            detalle = (f"PTA {p:.0f} dB HL  ·  {nombre}" if p is not None else
                       "PTA: faltan " + ", ".join(str(f) for f in faltan) + " Hz")
            self.lbl_pta[o].text = f"[b]{'OÍDO DERECHO' if o == 'D' else 'OÍDO IZQUIERDO'}[/b]   ·   {detalle}"
            self.lbl_pta[o].fondo.rgba = color if p is not None else (ROJO if o == "D" else AZUL)
        texto_v = f"[b]{r['veredicto']}[/b]  ·  " + "  ·  ".join(r["motivos"])
        if r["avisos"]:
            texto_v += "   [color=ffe08a]⚠ " + "; ".join(r["avisos"]) + "[/color]"
        self.lbl_veredicto.text = texto_v
        self.fondo_veredicto.rgba = COLOR_VEREDICTO[r["veredicto"]]

    def mostrar_paciente(self, p, codigo):
        self.paciente, self.codigo = p, codigo
        self.umbrales = {"D": {}, "I": {}}
        nombre = f"{p['nombres']} {p.get('ap_paterno', '')} {p.get('ap_materno', '')}".split()
        self.lbl_paciente.text = (f"[b]{' '.join(nombre)}[/b]  ·  {p.get('edad', '')} años  ·  "
                                  f"{'Femenino' if p.get('sexo') == 'F' else 'Masculino'}\n"
                                  f"[color=8fa0b0]C.I. {p['ci']} {p.get('ci_ext', '')}  ·  {codigo}  ·  "
                                  f"Audio: {self.motor.reproductor.nombre_backend}[/color]")
        self.grupo_f.elegir(1000)
        self.estado("Empieza en 1000 Hz, oído derecho. Cuando el paciente responda, presiona GUARDAR UMBRAL.")
        self._refrescar()

    def _volver(self, *_):
        self.motor.detener()
        if self.al_volver:
            self.al_volver()


class PantallaAudio(Screen):
    def __init__(self, motor, al_volver, al_guardar=None, **kw):
        super().__init__(**kw)
        self.banco = BancoAudio(motor, al_volver, al_guardar)
        self.add_widget(self.banco)

    def on_leave(self, *_):
        self.banco.motor.detener()