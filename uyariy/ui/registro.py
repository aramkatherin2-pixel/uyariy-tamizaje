"""
Pantalla 1: Registro del paciente.

Datos personales, procedencia, datos de la evaluación, antecedentes y
consentimiento. Valida, guarda en SQLite y pasa a la audiometría.
"""
from datetime import datetime

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.anchorlayout import AnchorLayout

from ..datos import pacientes as P
from . import estilo as E


class BarraPasos(BoxLayout):
    """Barra superior negra con el título y los 4 pasos del flujo."""

    PASOS = ["Paciente", "Ambiente", "Audiometría", "Resultados"]

    def __init__(self, titulo, paso_activo=0, **kw):
        super().__init__(size_hint_y=None, height=dp(66), padding=(dp(20), dp(10), dp(20), dp(14)),
                         spacing=dp(8), **kw)
        self.bind(pos=self._dibujar, size=self._dibujar)
        lb = Label(text=f"[b]UYARIY[/b]  [color=8fa0b0]·  {titulo}[/color]", markup=True, font_size="22sp",
                   halign="left", valign="middle")
        lb.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(lb)
        for i, nombre in enumerate(self.PASOS):
            activo = i == paso_activo
            paso = Label(text=f"[b]{i + 1}[/b]  {nombre}", markup=True, font_size="14sp",
                         size_hint_x=None, width=dp(130),
                         color=E.BLANCO if activo else E.TEXTO_SUAVE)
            E.fondo(paso, E.AZUL if activo else (0.18, 0.20, 0.23, 1), radio=dp(16))
            self.add_widget(paso)

    def _dibujar(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.06, 0.07, 0.08, 1)
            Rectangle(pos=self.pos, size=self.size)
            for i, c in enumerate([E.ROJO, E.AMBAR, E.VERDE, E.AZUL]):
                Color(*c)
                Rectangle(pos=(self.x + i * self.width / 4, self.y), size=(self.width / 4, dp(4)))


class PantallaRegistro(Screen):
    def __init__(self, bd, al_guardar, al_historial, **kw):
        super().__init__(**kw)
        self.bd = bd
        self.al_guardar = al_guardar          # función(paciente_dict, codigo)
        self.al_historial = al_historial
        raiz = BoxLayout(orientation="vertical")
        E.fondo(raiz, E.CLARO)
        raiz.add_widget(BarraPasos("Registro del paciente", 0))

        # --------- contenido desplazable (2 columnas)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(6))
        cuerpo = BoxLayout(orientation="horizontal", spacing=dp(14), padding=dp(14), size_hint_y=None)
        izq = BoxLayout(orientation="vertical", spacing=dp(14), size_hint_y=None, size_hint_x=0.58)
        der = BoxLayout(orientation="vertical", spacing=dp(14), size_hint_y=None, size_hint_x=0.42)
        for col in (izq, der):
            col.bind(minimum_height=col.setter("height"))
        ajustar = lambda *_: setattr(cuerpo, "height", max(izq.height, der.height) + dp(28))
        izq.bind(height=ajustar)
        der.bind(height=ajustar)

        izq.add_widget(self._tarjeta_personal())
        izq.add_widget(self._tarjeta_procedencia())
        izq.add_widget(self._tarjeta_evaluacion())
        der.add_widget(self._tarjeta_antecedentes())
        der.add_widget(self._tarjeta_consentimiento())
        for col, ancho in ((izq, 0.58), (der, 0.42)):
            caja = AnchorLayout(anchor_y="top", size_hint_x=ancho)   # columnas pegadas arriba
            col.size_hint_x = 1
            caja.add_widget(col)
            cuerpo.add_widget(caja)
        scroll.add_widget(cuerpo)
        raiz.add_widget(scroll)

        # --------- barra de acciones
        acciones = BoxLayout(size_hint_y=None, height=dp(62), padding=(dp(14), dp(8)), spacing=dp(10))
        b_hist = E.boton("Historial de pacientes", E.BOTON_CLARO, E.TINTA, size_hint_x=None, width=dp(210))
        b_hist.bind(on_release=lambda *_: self.al_historial())
        b_buscar = E.boton("Buscar por C.I.", E.BOTON_CLARO, E.TINTA, size_hint_x=None, width=dp(160))
        b_buscar.bind(on_release=self.buscar_ci)
        self.mensaje = Label(text="[color=c9353b]*[/color] Campos obligatorios", markup=True, font_size="14sp",
                             color=E.GRIS, halign="center", valign="middle")
        self.mensaje.bind(size=lambda w, s: setattr(w, "text_size", s))
        b_limpiar = E.boton("Nuevo / limpiar", E.BOTON_CLARO, E.TINTA, size_hint_x=None, width=dp(150))
        b_limpiar.bind(on_release=lambda *_: self.limpiar())
        b_guardar = E.boton("Guardar y continuar  >", E.VERDE, bold=True, size_hint_x=None, width=dp(250))
        b_guardar.bind(on_release=self.guardar)
        for w in (b_hist, b_buscar, self.mensaje, b_limpiar, b_guardar):
            acciones.add_widget(w)
        raiz.add_widget(acciones)
        self.add_widget(raiz)
        self.limpiar()
        Clock.schedule_interval(self._actualizar_hora, 1)   # reloj en vivo

    def _actualizar_hora(self, *_):
        self.fecha_eval.text = datetime.now().strftime("%d/%m/%Y  %H:%M")

    # ------------------------------------------------------------------ tarjetas
    def _tarjeta_personal(self):
        t = E.Tarjeta("1. Datos personales", E.ROJO)
        g = GridLayout(cols=3, spacing=(dp(12), dp(4)), size_hint_y=None)
        g.bind(minimum_height=g.setter("height"))
        self.nombres = E.campo(pista="Nombre(s)")
        self.ap_paterno = E.campo(pista="Apellido paterno")
        self.ap_materno = E.campo(pista="Apellido materno")
        ci = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(40))
        self.ci = E.campo(pista="Solo números", input_filter="int")
        self.ci_ext = E.selector("LP", P.EXTENSIONES_CI, size_hint_x=None, width=dp(70))
        ci.add_widget(self.ci)
        ci.add_widget(self.ci_ext)
        self.fecha_nac = E.campo(pista="dd/mm/aaaa")
        self.fecha_nac.bind(text=self._actualizar_edad)
        self.edad = E.campo(readonly=True)
        self.edad.background_color = (0.90, 0.95, 0.91, 1)
        self.sexo = E.GrupoBotones([("F", "Femenino"), ("M", "Masculino")], "sexo")
        self.telefono = E.campo(pista="7 u 8 dígitos", input_filter="int")
        self.idioma = E.selector("Castellano", P.IDIOMAS)
        self.ocupacion = E.campo(pista="Ej.: agricultor(a)")
        self.escolaridad = E.selector("No refiere", P.ESCOLARIDAD)
        self.tutor = E.campo(pista="Solo si es menor de 18 años")
        for titulo, w, obl in [("Nombre(s)", self.nombres, True), ("Apellido paterno", self.ap_paterno, True),
                               ("Apellido materno", self.ap_materno, False), ("C.I. / extensión", ci, True),
                               ("Fecha de nacimiento", self.fecha_nac, True), ("Edad", self.edad, False),
                               ("Sexo", self.sexo, True), ("Teléfono / celular", self.telefono, False),
                               ("Idioma materno", self.idioma, False), ("Ocupación", self.ocupacion, False),
                               ("Escolaridad", self.escolaridad, False), ("Tutor (nombre y C.I.)", self.tutor, False)]:
            g.add_widget(E.bloque(titulo, w, obl))
        t.add_widget(g)
        return t

    def _tarjeta_procedencia(self):
        t = E.Tarjeta("2. Procedencia", E.AMBAR)
        g = GridLayout(cols=4, spacing=(dp(12), dp(4)), size_hint_y=None, height=dp(64))
        self.departamento = E.selector("La Paz", P.DEPARTAMENTOS)
        self.provincia = E.campo(pista="Provincia")
        self.municipio = E.campo(pista="Municipio")
        self.comunidad = E.campo(pista="Comunidad")
        for titulo, w in [("Departamento", self.departamento), ("Provincia", self.provincia),
                          ("Municipio", self.municipio), ("Comunidad", self.comunidad)]:
            g.add_widget(E.bloque(titulo, w))
        t.add_widget(g)
        return t

    def _tarjeta_evaluacion(self):
        t = E.Tarjeta("3. Datos de la evaluación", E.AZUL)
        g = GridLayout(cols=3, spacing=(dp(12), dp(4)), size_hint_y=None, height=dp(132))
        self.fecha_eval = E.campo(readonly=True)
        self.fecha_eval.background_color = (0.90, 0.95, 0.91, 1)
        self.codigo = E.campo(readonly=True)
        self.motivo = E.selector(P.MOTIVOS[0], P.MOTIVOS)
        self.establecimiento = E.campo(pista="Ej.: C.S. Warisata")
        self.evaluador = E.campo(pista="Nombre del evaluador")
        self.audifonos = E.campo("Mis audífonos", readonly=True)
        for titulo, w in [("Fecha y hora", self.fecha_eval), ("Código de registro", self.codigo),
                          ("Motivo", self.motivo), ("Establecimiento de salud", self.establecimiento),
                          ("Evaluador", self.evaluador), ("Audífonos / calibración", self.audifonos)]:
            g.add_widget(E.bloque(titulo, w))
        t.add_widget(g)
        return t

    def _tarjeta_antecedentes(self):
        t = E.Tarjeta("4. Antecedentes y síntomas", E.VERDE)
        g = GridLayout(cols=2, spacing=(dp(6), 0), size_hint_y=None)
        g.bind(minimum_height=g.setter("height"))
        self.casillas = [E.Casilla(a) for a in P.ANTECEDENTES]
        for c in self.casillas:
            g.add_widget(c)
        t.add_widget(g)
        t.add_widget(E.etiqueta("Oído con más dificultad"))
        self.oido = E.GrupoBotones([(o, o) for o in P.OIDO_DIFICULTAD], "oido",
                                   colores={"Derecho": E.ROJO, "Izquierdo": E.AZUL})
        t.add_widget(self.oido)
        self.observaciones = E.campo(pista="Observaciones (opcional)")
        t.add_widget(E.bloque("Observaciones", self.observaciones))
        return t

    def _tarjeta_consentimiento(self):
        t = E.Tarjeta("5. Consentimiento informado", (0.40, 0.42, 0.46, 1))
        self.consent1 = E.Casilla("El paciente (o tutor) acepta la evaluación y el registro de sus datos")
        self.consent2 = E.Casilla("Se explicó que es un tamizaje y no reemplaza el diagnóstico médico")
        t.add_widget(self.consent1)
        t.add_widget(self.consent2)
        return t

    # ------------------------------------------------------------------ lógica
    def _actualizar_edad(self, *_):
        try:
            nac = P.leer_fecha(self.fecha_nac.text)
            edad = P.calcular_edad(nac)
            self.edad.text = f"{edad} años (automático)" if 0 <= edad <= 120 else "—"
        except ValueError:
            self.edad.text = ""

    def datos(self):
        return {
            "nombres": self.nombres.text, "ap_paterno": self.ap_paterno.text, "ap_materno": self.ap_materno.text,
            "ci": self.ci.text, "ci_ext": self.ci_ext.text, "fecha_nac": self.fecha_nac.text,
            "sexo": self.sexo.valor, "telefono": self.telefono.text, "idioma": self.idioma.text,
            "ocupacion": self.ocupacion.text, "escolaridad": self.escolaridad.text, "tutor": self.tutor.text,
            "departamento": self.departamento.text, "provincia": self.provincia.text,
            "municipio": self.municipio.text, "comunidad": self.comunidad.text,
            "codigo": self.codigo.text, "motivo": self.motivo.text, "establecimiento": self.establecimiento.text,
            "evaluador": self.evaluador.text,
            "antecedentes": [c.texto for c in self.casillas if c.activo],
            "oido_dificultad": self.oido.valor or "", "observaciones": self.observaciones.text,
            "consentimiento": self.consent1.activo and self.consent2.activo,
        }

    def limpiar(self):
        for w in (self.nombres, self.ap_paterno, self.ap_materno, self.ci, self.fecha_nac, self.telefono,
                  self.ocupacion, self.tutor, self.provincia, self.municipio, self.comunidad, self.observaciones):
            w.text = ""
        self.sexo.elegir(None)
        self.oido.elegir(None)
        for c in self.casillas + [self.consent1, self.consent2]:
            c.cb.active = False
        self.fecha_eval.text = datetime.now().strftime("%d/%m/%Y  %H:%M")
        self.codigo.text = self.bd.nuevo_codigo()
        self.aviso("[color=c9353b]*[/color] Campos obligatorios", E.GRIS)

    def cargar_paciente(self, p):
        """Rellena el formulario con un paciente ya registrado."""
        for c in ("nombres", "ap_paterno", "ap_materno", "ci", "fecha_nac", "telefono", "ocupacion", "tutor",
                  "provincia", "municipio", "comunidad"):
            getattr(self, c).text = p.get(c) or ""
        for c in ("ci_ext", "idioma", "escolaridad", "departamento"):
            if p.get(c):
                getattr(self, c).text = p[c]
        self.sexo.elegir(p.get("sexo"))

    def preparar_control(self, p):
        """Nueva evaluación (control) de un paciente ya registrado, elegido en el historial."""
        self.limpiar()
        self.cargar_paciente(p)
        self.motivo.text = "Control / seguimiento"
        self.aviso("Control de [b]" + p["nombres"] + "[/b]: revisa, marca el consentimiento y presiona Guardar",
                   E.AZUL)

    def buscar_ci(self, *_):
        ci = self.ci.text.strip()
        if not ci:
            self.aviso("Escribe el C.I. y luego presiona «Buscar por C.I.»", E.AMBAR)
            return
        p = self.bd.buscar_ci(ci, self.ci_ext.text) or self.bd.buscar_ci(ci)
        if p:
            self.cargar_paciente(p)
            self.aviso(f"Paciente encontrado: {p['nombres']} {p['ap_paterno']}. Revisa y continúa.", E.VERDE)
        else:
            self.aviso("No hay registros con ese C.I. Llena los datos para registrarlo.", E.AMBAR)

    def guardar(self, *_):
        datos = self.datos()
        errores = P.validar(datos)
        if errores:
            self.aviso("[b]Revisa:[/b] " + " · ".join(errores[:3]), E.ROJO)
            return
        try:
            _pid, codigo = self.bd.registrar(datos)
        except Exception as e:
            self.aviso(f"No se pudo guardar: {e}", E.ROJO)
            return
        datos["edad"] = P.calcular_edad(P.leer_fecha(datos["fecha_nac"]))
        self.aviso(f"Guardado: {codigo}", E.VERDE)
        Clock.schedule_once(lambda dt: self.al_guardar(datos, codigo), 0.2)

    def aviso(self, texto, color):
        self.mensaje.text = texto
        self.mensaje.color = color

    def on_pre_enter(self, *_):
        self.fecha_eval.text = datetime.now().strftime("%d/%m/%Y  %H:%M")
        self.codigo.text = self.bd.nuevo_codigo()