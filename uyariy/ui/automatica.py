"""
Pantalla 4: Audiometría automática (Hughson-Westlake "2 de 3"), como el AC40 (pág. 29).

El paciente toca el botón grande cada vez que escucha un tono. La tablet decide sola
el siguiente nivel, recorre las frecuencias de ambos oídos y dibuja el audiograma.
Controles de calidad:
  - Pruebas trampa: algunas presentaciones son en silencio (detecta respuestas falsas).
  - Toques fuera de tiempo: se cuentan como falsas alarmas.
  - Re-test a 1 kHz al final de cada oído (consistencia test-retest).
El botón NO cambia de color mientras suena el tono, para no dar pistas visuales.
"""
import random

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen

from ..audio.calibracion import NivelFueraDeRango
from ..audio.motor import Enmascaramiento, Estimulo
from ..clinica import clasificacion as C
from ..clinica import seguridad as S
from ..clinica.hughson import HughsonWestlake, fiabilidad
from .audiograma import Audiograma
from .banco_audio import GrupoOpciones, boton, fondo, texto
from .estilo import AZUL, FONDO, GRIS_BTN, PANEL, ROJO, VERDE

PROTOCOLOS = {
    "rapido": [1000, 2000, 4000, 500],
    "completo": [1000, 2000, 3000, 4000, 6000, 8000, 500, 250],
}
DURACION_TONO = 1.0           # s (pulso con rampas de 25 ms)
VENTANA_RESPUESTA = 1.5       # s después de terminar el tono
PAUSA_MIN, PAUSA_MAX = 1.2, 2.8   # pausa aleatoria entre presentaciones (AC40: 2 a 3,6 s)
PROB_TRAMPA = 0.12            # 12 % de presentaciones en silencio


class PantallaAutomatica(Screen):
    def __init__(self, motor, al_terminar, al_volver, **kw):
        super().__init__(**kw)
        self.motor = motor
        self.al_terminar = al_terminar          # función(umbrales, info_fiabilidad)
        self.al_volver = al_volver
        self.protocolo = "rapido"
        self.azar = random.Random()
        self._reiniciar_datos()

        raiz = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        fondo(raiz, FONDO)

        cab = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        volver = boton("<  Manual", size_hint_x=None, width=dp(120))
        volver.bind(on_release=lambda *_: self._salir())
        self.lbl_titulo = texto("[b]Audiometría automática[/b]  ·  Hughson-Westlake (2 de 3)", "16sp", (1, 1, 1, 1))
        cab.add_widget(volver)
        cab.add_widget(self.lbl_titulo)
        raiz.add_widget(cab)

        graficos = BoxLayout(spacing=dp(10), size_hint_y=0.55)
        self.audiogramas = {}
        for o in ("D", "I"):
            a = Audiograma(o)
            a.limite = lambda f, o=o: self.motor.maximo(f, o)
            self.audiogramas[o] = a
            graficos.add_widget(a)
        raiz.add_widget(graficos)

        self.lbl_estado = texto("", "16sp", (1, 1, 1, 1), size_hint_y=None, height=dp(30))
        self.fondo_estado = fondo(self.lbl_estado, PANEL)
        raiz.add_widget(self.lbl_estado)

        # botón del paciente (grande)
        self.btn_paciente = boton("TOQUE AQUÍ CADA VEZ QUE ESCUCHE UN SONIDO", (0.12, 0.42, 0.62, 1),
                                  font_size="26sp", bold=True, size_hint_y=0.30)
        self.btn_paciente.bind(on_press=self._toque)
        raiz.add_widget(self.btn_paciente)

        ctrl = BoxLayout(size_hint_y=None, height=dp(62), spacing=dp(8))
        self.grupo_prot = GrupoOpciones("PROTOCOLO", [("rapido", "Rápido (4 frec.)"),
                                                      ("completo", "Completo (8 frec.)")],
                                        "rapido", self._cambiar_protocolo, size_hint_x=0.34)
        ctrl.add_widget(self.grupo_prot)
        self.btn_inicio = boton("INICIAR", VERDE, font_size="20sp", bold=True, size_hint_x=0.22)
        self.btn_inicio.bind(on_release=self._iniciar_o_pausar)
        self.btn_terminar = boton("Terminar y revisar  >", AZUL, font_size="17sp", bold=True, size_hint_x=0.26)
        self.btn_terminar.bind(on_release=lambda *_: self._finalizar())
        b_reiniciar = boton("Reiniciar", GRIS_BTN, size_hint_x=0.18)
        b_reiniciar.bind(on_release=lambda *_: self._reiniciar())
        for w in (self.btn_inicio, self.btn_terminar, b_reiniciar):
            ctrl.add_widget(w)
        raiz.add_widget(ctrl)

        self.lbl_calidad = texto("", "13sp", size_hint_y=None, height=dp(20))
        raiz.add_widget(self.lbl_calidad)
        self.add_widget(raiz)
        self._mostrar()

    # ------------------------------------------------------------ datos
    def _reiniciar_datos(self):
        self.umbrales = {"D": {}, "I": {}}
        self.cola = []                 # [(oido, frecuencia, es_retest)]
        self.hw = None
        self.actual = None
        self.estado = "listo"          # listo / corriendo / pausado / fin
        self.ventana_abierta = False
        self.respondio = False
        self.es_trampa = False
        self.presentaciones = 0
        self.trampas = self.falsos_trampa = self.falsos_fuera = 0
        self.retest = {}               # oido -> (primero, segundo)
        self._eventos = []

    def preparar(self, paciente):
        self._reiniciar()
        nombre = f"{paciente.get('nombres', '')} {paciente.get('ap_paterno', '')}".strip()
        self.lbl_titulo.text = (f"[b]Audiometría automática[/b]  ·  Hughson-Westlake (2 de 3)  ·  "
                                f"[color=8fa0b0]{nombre}[/color]")

    def _armar_cola(self):
        frecs = PROTOCOLOS[self.protocolo]
        self.cola = [(o, f, False) for o in ("D", "I") for f in frecs]
        # re-test de 1 kHz al final de cada oído
        self.cola.insert(len(frecs), ("D", 1000, True))
        self.cola.append(("I", 1000, True))

    # ------------------------------------------------------------ control
    def _cambiar_protocolo(self, p):
        if self.estado == "listo":
            self.protocolo = p
            if hasattr(self, "btn_inicio"):      # la pantalla ya está construida
                self._mostrar()

    def _iniciar_o_pausar(self, *_):
        if self.estado == "listo":
            self._armar_cola()
            self.estado = "corriendo"
            self._siguiente_item()
        elif self.estado == "corriendo":
            self.estado = "pausado"
            self._cancelar_eventos()
            self.motor.detener()
            self.ventana_abierta = False
        elif self.estado == "pausado":
            self.estado = "corriendo"
            self._programar(0.5, self._presentar)
        self._mostrar()

    def _reiniciar(self):
        self._cancelar_eventos()
        self.motor.detener()
        self._reiniciar_datos()
        self.grupo_prot.elegir(self.protocolo)    # el botón marcado coincide con el protocolo real
        self._mostrar()

    def _salir(self):
        self._cancelar_eventos()
        self.motor.detener()
        if self.estado == "corriendo":
            self.estado = "pausado"
        self.al_volver()

    def _programar(self, t, funcion):
        self._eventos.append(Clock.schedule_once(lambda dt: funcion(), t))

    def _cancelar_eventos(self):
        for e in self._eventos:
            e.cancel()
        self._eventos = []

    # ------------------------------------------------------------ ciclo de la prueba
    def _siguiente_item(self):
        if not self.cola:
            self._fin_de_prueba()
            return
        self.actual = self.cola.pop(0)
        o, f, _ = self.actual
        # seguridad: la prueba automática nunca pasa del límite seguro (80 dB HL)
        self.hw = HughsonWestlake(min(self.motor.maximo(f, o), S.LIMITE_SEGURO))
        self._programar(1.0, self._presentar)

    def _presentar(self):
        if self.estado != "corriendo":
            return
        o, f, _ = self.actual
        self.presentaciones += 1
        self.respondio = False
        # prueba trampa: silencio (nunca durante la familiarización)
        self.es_trampa = self.hw.fase != "familiarizacion" and self.azar.random() < PROB_TRAMPA
        if self.es_trampa:
            self.trampas += 1
        else:
            try:
                est = Estimulo(frecuencia=f, dbhl=self.hw.nivel, oido=o, tipo="tono", duracion=DURACION_TONO)
                self.motor.presentar(est, Enmascaramiento(activo=False))
            except NivelFueraDeRango:
                self.hw.sin_respuesta = True
        self.ventana_abierta = True
        self._mostrar()
        self._programar(DURACION_TONO + VENTANA_RESPUESTA, self._cerrar_ventana)

    def _toque(self, *_):
        if self.estado != "corriendo":
            return
        if self.ventana_abierta:
            self.respondio = True
        else:
            self.falsos_fuera += 1
        # retroalimentación breve del toque (no indica si hubo tono)
        self.btn_paciente.background_color = (0.20, 0.55, 0.78, 1)
        Clock.schedule_once(lambda dt: setattr(self.btn_paciente, "background_color", (0.12, 0.42, 0.62, 1)), 0.15)

    def _cerrar_ventana(self):
        self.ventana_abierta = False
        if self.estado != "corriendo":
            return
        if self.es_trampa:
            if self.respondio:
                self.falsos_trampa += 1
        else:
            self.hw.responder(self.respondio)
        if self.hw.terminado:
            self._guardar_item()
            self._siguiente_item()
        else:
            self._programar(self.azar.uniform(PAUSA_MIN, PAUSA_MAX), self._presentar)
        self._mostrar()

    def _guardar_item(self):
        o, f, es_retest = self.actual
        valor = None if self.hw.sin_respuesta else self.hw.umbral
        if es_retest:
            primero = self.umbrales[o].get(1000)
            self.retest[o] = (primero.db if primero else None, valor)
            return
        if self.hw.sin_respuesta:
            self.umbrales[o][f] = C.Umbral(db=self.hw.maximo, nr=True)
        else:
            self.umbrales[o][f] = C.Umbral(db=self.hw.umbral)

    def _fin_de_prueba(self):
        self.estado = "fin"
        self.actual = None
        self.motor.detener()
        self._mostrar()

    def info_fiabilidad(self):
        ok, msj = fiabilidad(self.trampas, self.falsos_trampa, self.falsos_fuera, list(self.retest.values()))
        return {"confiable": ok, "mensajes": msj, "trampas": self.trampas, "falsos_trampa": self.falsos_trampa,
                "falsos_fuera": self.falsos_fuera, "retest_1k": self.retest, "presentaciones": self.presentaciones,
                "protocolo": self.protocolo}

    def _finalizar(self):
        self._cancelar_eventos()
        self.motor.detener()
        if self.estado == "corriendo":
            self.estado = "pausado"
        self.al_terminar({o: dict(u) for o, u in self.umbrales.items()}, self.info_fiabilidad())

    # ------------------------------------------------------------ pantalla
    def _mostrar(self):
        for o in ("D", "I"):
            cursor = None
            if self.actual and self.actual[0] == o and self.hw and not self.hw.terminado:
                cursor = (self.actual[1], self.hw.nivel)
            self.audiogramas[o].actualizar(self.umbrales[o], cursor, "tono")

        total = len(PROTOCOLOS[self.protocolo]) * 2 + 2
        hechos = total - len(self.cola) - (1 if self.actual else 0)
        if self.estado == "listo":
            t, c = ("Explique al paciente: «Toque el botón cada vez que escuche un sonido, aunque sea muy suave». "
                    "Luego presione INICIAR."), PANEL
        elif self.estado == "fin":
            t, c = "Prueba terminada. Presione «Terminar y revisar» para ver y guardar el resultado.", VERDE
        else:
            o, f, rt = self.actual if self.actual else ("D", 1000, False)
            fase = {"familiarizacion": "familiarización", "descenso": "buscando", "ascenso": "confirmando"}
            t = (f"{'PAUSADO · ' if self.estado == 'pausado' else ''}Oído {'DERECHO' if o == 'D' else 'IZQUIERDO'}"
                 f"  ·  {f} Hz{' (re-test)' if rt else ''}  ·  {fase.get(self.hw.fase, '') if self.hw else ''}"
                 f"  ·  frecuencia {min(hechos + 1, total)} de {total}")
            c = ROJO if o == "D" else AZUL
        self.lbl_estado.text = t
        self.fondo_estado.rgba = c
        self.btn_inicio.text = {"listo": "INICIAR", "corriendo": "PAUSAR", "pausado": "CONTINUAR",
                                "fin": "TERMINADO"}[self.estado]
        self.btn_inicio.background_color = AZUL if self.estado == "corriendo" else (VERDE if self.estado != "fin"
                                                                                     else GRIS_BTN)
        # el protocolo solo se puede cambiar antes de iniciar
        for b in self.grupo_prot.botones.values():
            b.background_disabled_normal = b.background_disabled_down = ""
            b.disabled = self.estado != "listo"
        ok, msj = fiabilidad(self.trampas, self.falsos_trampa, self.falsos_fuera, list(self.retest.values()))
        self.lbl_calidad.text = (f"Presentaciones: {self.presentaciones}  ·  Trampas: {self.trampas} "
                                 f"(respondió {self.falsos_trampa})  ·  Toques sin estímulo: {self.falsos_fuera}  ·  "
                                 + ("[color=7ddc8f]Respuestas confiables[/color]" if ok else
                                    "[color=ff8a80](!) " + "; ".join(msj) + "[/color]"))

    def on_leave(self, *_):
        self._cancelar_eventos()
        self.motor.detener()