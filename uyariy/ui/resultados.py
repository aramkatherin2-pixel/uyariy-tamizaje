"""
Pantalla 5: Resultados e informe.

Izquierda: audiogramas finales. Derecha: veredicto, PTA / grado OMS / % AMA, interpretación
automática y recomendaciones. Abajo: observaciones del evaluador (botones rápidos + nota)
y los botones GENERAR PDF / Abrir / Compartir.
"""
import os

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from ..clinica import clasificacion as C
from ..clinica import interpretacion as I
from ..informe import archivos as A
from ..informe.reporte import generar_informe
from .audiograma import Audiograma
from .banco_audio import COLOR_VEREDICTO, boton, fondo, texto
from .estilo import AMBAR, AZUL, FONDO, GRIS_BTN, PANEL, ROJO, VERDE

OBS_RAPIDAS = ["Cerumen visible", "Ambiente ruidoso", "Paciente poco colaborador",
               "Usa audífono", "Resfriado / oído tapado", "Se repitió la prueba"]
COLOR_HEX = {"D": "ff8a8a", "I": "8ab4ff"}


class PantallaResultados(Screen):
    def __init__(self, bd, carpeta_datos, al_volver, al_nuevo, **kw):
        super().__init__(**kw)
        self.bd = bd
        self.carpeta_datos = carpeta_datos
        self.al_volver = al_volver
        self.al_nuevo = al_nuevo
        self.paciente, self.codigo, self.datos, self.umbrales = {}, None, {}, {"D": {}, "I": {}}
        self.destino = None
        self.incompleto, self.confirmar_incompleto = False, False

        raiz = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        fondo(raiz, FONDO)

        # ----- cabecera
        cab = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        volver = boton("<  Audiometría", size_hint_x=None, width=dp(150))
        volver.bind(on_release=lambda *_: self.al_volver())
        self.lbl_titulo = texto("[b]Resultados[/b]", "17sp", (1, 1, 1, 1))
        nuevo = boton("Nuevo paciente", AZUL, bold=True, size_hint_x=None, width=dp(180))
        nuevo.bind(on_release=lambda *_: self.al_nuevo())
        for w in (volver, self.lbl_titulo, nuevo):
            cab.add_widget(w)
        raiz.add_widget(cab)

        # ----- cuerpo: audiogramas | resumen
        cuerpo = BoxLayout(spacing=dp(10))
        izq = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_x=0.40)
        self.audiogramas = {}
        for o in ("D", "I"):
            a = Audiograma(o)
            self.audiogramas[o] = a
            izq.add_widget(a)
        cuerpo.add_widget(izq)

        der = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_x=0.60)
        self.lbl_veredicto = texto("", "22sp", (1, 1, 1, 1), size_hint_y=None, height=dp(66))
        self.fondo_veredicto = fondo(self.lbl_veredicto, COLOR_VEREDICTO["INCOMPLETO"])
        der.add_widget(self.lbl_veredicto)

        desplazar = ScrollView(do_scroll_x=False, bar_width=dp(6))
        fondo(desplazar, PANEL)
        self.lbl_resumen = Label(text="", markup=True, font_size="15sp", color=(0.92, 0.94, 0.96, 1),
                                 halign="left", valign="top", size_hint_y=None, padding=(dp(12), dp(10)))
        self.lbl_resumen.bind(width=lambda w, ancho: setattr(w, "text_size", (ancho, None)),
                              texture_size=lambda w, t: setattr(w, "height", t[1]))
        desplazar.add_widget(self.lbl_resumen)
        der.add_widget(desplazar)

        # ----- observaciones del evaluador
        der.add_widget(texto("OBSERVACIONES DEL EVALUADOR (toque las que correspondan)", "12sp",
                             size_hint_y=None, height=dp(16)))
        rejilla = GridLayout(cols=3, spacing=dp(5), size_hint_y=None, height=dp(86))
        self.obs = {}
        for t in OBS_RAPIDAS:
            b = ToggleButton(text=t, font_size="14sp", background_normal="", background_down="",
                             background_color=GRIS_BTN)
            b.bind(state=lambda b, s: setattr(b, "background_color", AMBAR if s == "down" else GRIS_BTN))
            self.obs[t] = b
            rejilla.add_widget(b)
        der.add_widget(rejilla)
        self.nota = TextInput(hint_text="Nota opcional (ej.: trabaja en carpintería sin protección)",
                              multiline=True, font_size="15sp", size_hint_y=None, height=dp(62),
                              background_normal="", background_active="", background_color=(0.96, 0.97, 0.98, 1))
        der.add_widget(self.nota)
        cuerpo.add_widget(der)
        raiz.add_widget(cuerpo)

        # ----- acciones
        acciones = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        self.btn_pdf = boton("GENERAR INFORME PDF", VERDE, font_size="20sp", bold=True, size_hint_x=0.46)
        self.btn_pdf.bind(on_release=lambda *_: self._generar())
        self.btn_abrir = boton("Abrir PDF", AZUL, font_size="17sp", size_hint_x=0.27, disabled=True)
        self.btn_abrir.bind(on_release=lambda *_: self._accion(A.abrir))
        self.btn_compartir = boton("Compartir", (0.45, 0.35, 0.70, 1), font_size="17sp", size_hint_x=0.27,
                                   disabled=True)
        self.btn_compartir.bind(on_release=lambda *_: self._accion(A.compartir))
        for w in (self.btn_pdf, self.btn_abrir, self.btn_compartir):
            w.background_disabled_normal = ""
            acciones.add_widget(w)
        raiz.add_widget(acciones)

        self.lbl_estado = texto("", "13sp", size_hint_y=None, height=dp(20))
        raiz.add_widget(self.lbl_estado)
        self.add_widget(raiz)

    # ------------------------------------------------------------ datos
    def mostrar(self, paciente, codigo, datos):
        self.paciente, self.codigo, self.datos = paciente, codigo, dict(datos)
        self.umbrales = {o: C.desde_json(u) for o, u in (datos.get("umbrales") or {}).items()}
        self.umbrales.setdefault("D", {})
        self.umbrales.setdefault("I", {})
        self.destino = None
        self.incompleto, self.confirmar_incompleto = False, False
        self.btn_abrir.disabled = self.btn_compartir.disabled = True
        anteriores = datos.get("observaciones_evaluador", [])
        for t, b in self.obs.items():
            b.state = "down" if t in anteriores else "normal"
        self.nota.text = datos.get("nota_evaluador", "")
        nombre = " ".join(x for x in (paciente.get("nombres"), paciente.get("ap_paterno"),
                                      paciente.get("ap_materno")) if x)
        self.lbl_titulo.text = f"[b]Resultados[/b]  ·  {nombre}  ·  [color=8fa0b0]{codigo}[/color]"
        for o in ("D", "I"):
            self.audiogramas[o].actualizar(self.umbrales[o], None, "tono")
        self._resumen()
        self.lbl_estado.text = "Revise el resultado, marque las observaciones y presione GENERAR INFORME PDF."

    def _resumen(self):
        r = I.interpretar(self.umbrales["D"], self.umbrales["I"], self.paciente.get("edad"),
                          self.paciente.get("antecedentes", []))
        ev, ama = r["evaluacion"], r["ama"]
        motivos = "  ·  ".join(ev["motivos"])
        if len(motivos) > 95:
            motivos = motivos[:92] + "..."
        self.lbl_veredicto.text = f"[b]{ev['veredicto']}[/b]\n[size=14sp]{motivos}[/size]"
        self.incompleto = ev["veredicto"] == "INCOMPLETO"
        self.fondo_veredicto.rgba = COLOR_VEREDICTO[ev["veredicto"]]

        t = []
        for o, nombre in (("D", "OÍDO DERECHO"), ("I", "OÍDO IZQUIERDO")):
            p = ev["pta"][o]
            linea = f"[b][color={COLOR_HEX[o]}]{nombre}[/color][/b]   "
            linea += (f"PTA {p:.0f} dB HL  ·  {ev['grado'][o]}" if p is not None else "PTA incompleto")
            if ama[o] is not None:
                linea += f"  ·  AMA {ama[o]:.1f} %"
            t.append(linea)
        if ama["binaural"] is not None:
            t.append(f"Discapacidad binaural (AMA/AAO-1979): [b]{ama['binaural']:.1f} %[/b]"
                     + ("  [color=8fa0b0](3 kHz estimado)[/color]" if ama["estimado"] else ""))
        t.append("\n[b]INTERPRETACIÓN AUTOMÁTICA[/b]")
        hallazgos = [f"Oído {'derecho' if o == 'D' else 'izquierdo'}: {p}" for o in ("D", "I")
                     for p in r["patrones"][o]]
        fia = self.datos.get("fiabilidad")
        if fia and any(self.umbrales.values()):
            hallazgos.append("Respuestas confiables" if fia.get("confiable") else
                             "[color=ff8a80]Poco confiable: " + "; ".join(fia.get("mensajes", [])) + "[/color]")
        hallazgos += [f"[color=ffe08a]{a}[/color]" for a in ev["avisos"]]
        t += [f"•  {h}" for h in (hallazgos or ["Sin hallazgos adicionales en la forma del audiograma"])]
        t.append("\n[b]RECOMENDACIONES[/b]")
        t += [f"•  {x}" for x in r["recomendaciones"]]
        t.append(f"\n[color=8fa0b0][size=13sp]{r['aviso']}[/size][/color]")
        self.lbl_resumen.text = "\n".join(t)

    # ------------------------------------------------------------ informe
    def _generar(self):
        if not self.codigo:
            return
        if self.incompleto and not self.confirmar_incompleto:
            self.confirmar_incompleto = True
            self._aviso("(!) La prueba está INCOMPLETA (faltan 500, 1000, 2000 o 4000 Hz). Vuelva a la "
                        "audiometría para completarla, o presione otra vez GENERAR para crear el PDF igual.", AMBAR)
            return
        obs = [t for t, b in self.obs.items() if b.state == "down"]
        nota = self.nota.text.strip()
        self.datos["observaciones_evaluador"] = obs
        self.datos["nota_evaluador"] = nota
        try:
            ruta = os.path.join(A.carpeta_interna(self.carpeta_datos), A.nombre_pdf(self.codigo))
            _, verif = generar_informe(ruta, self.paciente, self.codigo, self.umbrales, self.datos, obs, nota)
            self.datos["verificacion"] = verif
            self.bd.guardar_resultados(self.codigo, self.datos)
        except Exception as e:
            self._aviso(f"[!] No se pudo crear el PDF: {type(e).__name__}: {e}", ROJO)
            return
        try:
            donde, self.destino = A.publicar(ruta)
        except Exception as e:
            donde, self.destino = ruta, (None if A.ES_ANDROID else ruta)
            self._aviso(f"PDF creado en la carpeta de la app ({type(e).__name__}). Código {verif}", AMBAR)
        else:
            self._aviso(f"Informe guardado en: {donde}   ·   código de verificación {verif}", VERDE)
        self.btn_abrir.disabled = self.btn_compartir.disabled = self.destino is None

    def _accion(self, funcion):
        try:
            funcion(self.destino)
        except Exception as e:
            self._aviso(f"[!] {type(e).__name__}: {e}", ROJO)

    def _aviso(self, t, color):
        hexa = "%02x%02x%02x" % tuple(int(c * 255) for c in color[:3])
        self.lbl_estado.text = f"[color={hexa}]{t}[/color]"