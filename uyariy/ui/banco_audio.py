"""
Pantalla 3: Audiometría (consola del audiómetro + audiograma en vivo).

Arriba: frecuencias. Centro: audiogramas derecho e izquierdo que se dibujan en vivo,
con su promedio tonal (PTA) y grado OMS. Abajo: nivel, oído, estímulo, presentación,
enmascaramiento y los botones PRESENTAR / GUARDAR UMBRAL / SIN RESPUESTA / BORRAR.
"""
import time
from datetime import datetime

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
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
    def __init__(self, motor, al_volver=None, al_guardar=None, al_auto=None, **kw):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), **kw)
        fondo(self, FONDO)
        self.motor = motor
        self.al_volver = al_volver
        self.al_guardar = al_guardar            # función(codigo, resultados) -> bool
        self.al_auto = al_auto                  # abre la audiometría automática
        self.metodo, self.fiabilidad = "manual", None
        self.alto_confirmado = False            # el evaluador aceptó pasar de 80 dB HL
        self.expo = S.Exposicion()              # registro de exposición sonora
        self._inicio_continuo, self._ev_continuo = None, None
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
        self.btn_auto = boton("AUTOMÁTICO", (0.45, 0.35, 0.70, 1), bold=True, size_hint_x=None, width=dp(150))
        self.btn_auto.bind(on_release=self._abrir_auto)
        self.btn_guardar_todo = boton("Guardar resultados", AZUL, bold=True, size_hint_x=None, width=dp(200))
        self.btn_guardar_todo.bind(on_release=self._guardar_resultados)
        for w in (volver, self.lbl_paciente, self.btn_auto, self.btn_guardar_todo):
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
        self.btn = boton("PRESENTAR TONO", VERDE, font_size="22sp", bold=True, size_hint_x=0.34)
        self.btn.bind(on_release=self._presentar)
        b_umbral = boton("GUARDAR UMBRAL", (0.10, 0.45, 0.70, 1), font_size="17sp", bold=True, size_hint_x=0.22)
        b_umbral.bind(on_release=lambda *_: self._guardar_umbral(nr=False))
        b_nr = boton("Sin respuesta", GRIS_BTN, font_size="15sp", size_hint_x=0.16)
        b_nr.bind(on_release=lambda *_: self._guardar_umbral(nr=True))
        b_borrar = boton("Borrar punto", GRIS_BTN, font_size="15sp", size_hint_x=0.14)
        b_borrar.bind(on_release=self._borrar_umbral)
        b_parar = boton("PARAR", (0.75, 0.12, 0.15, 1), font_size="18sp", bold=True, size_hint_x=0.14)
        b_parar.bind(on_release=lambda *_: self._parar())          # botón de pánico: corta todo el sonido
        for w in (self.btn, b_umbral, b_nr, b_borrar, b_parar):
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
        self._inicio_seguro()
        self._limitar()

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
        self.motor.detener()
        self.modo = m
        self._refrescar()

    def _cambiar_enm(self, v):
        self.enm.activo = bool(v)
        if v:
            self.enm.tipo = v
        self._refrescar()

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
        col = {"D": "ff6b6b", "I": "6ba4ff", "DI": "b39ddb"}[self.est.oido]
        riesgo = "%02x%02x%02x" % tuple(int(c * 255) for c in S.color_nivel(self.est.dbhl)[:3])
        self.lbl_nivel.text = f"[color={col}]{self.est.dbhl:.0f}[/color] [size=20sp]dB HL[/size]"
        etiqueta = ("NIVEL ALTO" if self.est.dbhl >= S.NIVEL_PELIGRO else
                    "PRECAUCIÓN" if self.est.dbhl >= S.NIVEL_AVISO else "SEGURO")
        self.lbl_max.text = (f"[b][color={riesgo}]{etiqueta}[/color][/b]  ·  límite {S.LIMITE_SEGURO}  ·  "
                             f"máx. equipo {maximo:.0f} dB HL")
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
                                  f"Audio: {self.motor.reproductor.nombre_backend}[/color]")
        self.grupo_f.elegir(1000)
        self.estado("Empieza en 1000 Hz, oído derecho. Cuando el paciente responda, presiona GUARDAR UMBRAL.")
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