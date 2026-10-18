"""Pantalla: historial de pacientes evaluados (búsqueda por nombre o C.I.)."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from . import estilo as E
from .registro import BarraPasos

COLUMNAS = [("Código", 0.15), ("Fecha", 0.15), ("Paciente", 0.24), ("C.I.", 0.11),
            ("Edad", 0.06), ("Sexo", 0.05), ("Comunidad", 0.13), ("", 0.11)]


class PantallaHistorial(Screen):
    def __init__(self, bd, al_volver, al_elegir, **kw):
        super().__init__(**kw)
        self.bd = bd
        self.al_volver = al_volver
        self.al_elegir = al_elegir          # función(paciente_dict): nueva evaluación (control)
        raiz = BoxLayout(orientation="vertical")
        E.fondo(raiz, E.CLARO)
        raiz.add_widget(BarraPasos("Historial de pacientes", -1))

        barra = BoxLayout(size_hint_y=None, height=dp(60), padding=(dp(14), dp(10)), spacing=dp(10))
        volver = E.boton("<  Volver al registro", E.BOTON_CLARO, E.TINTA, size_hint_x=None, width=dp(200))
        volver.bind(on_release=lambda *_: self.al_volver())
        self.buscar = E.campo(pista="Buscar por nombre, apellido o C.I.")
        self.buscar.bind(text=lambda *_: self.refrescar())
        self.total = E.etiqueta("", "14sp", E.GRIS, alto=dp(40), size_hint_x=None, width=dp(200))
        for w in (volver, self.buscar, self.total):
            barra.add_widget(w)
        raiz.add_widget(barra)

        cab = BoxLayout(size_hint_y=None, height=dp(36), padding=(dp(14), 0))
        E.fondo(cab, (0.20, 0.24, 0.30, 1))
        for t, w in COLUMNAS:
            cab.add_widget(E.etiqueta(t, "14sp", E.BLANCO, True, dp(36), size_hint_x=w))
        raiz.add_widget(cab)

        scroll = ScrollView(do_scroll_x=False)
        self.lista = GridLayout(cols=1, size_hint_y=None, spacing=dp(2), padding=(dp(14), dp(4)))
        self.lista.bind(minimum_height=self.lista.setter("height"))
        scroll.add_widget(self.lista)
        raiz.add_widget(scroll)
        self.add_widget(raiz)

    def refrescar(self):
        self.lista.clear_widgets()
        filas = self.bd.historial(self.buscar.text)
        self.total.text = f"{len(filas)} evaluaciones · {self.bd.total_pacientes()} pacientes"
        if not filas:
            self.lista.add_widget(E.etiqueta("Todavía no hay evaluaciones registradas.", "15sp", E.GRIS, alto=dp(50)))
        for i, f in enumerate(filas):
            fila = BoxLayout(size_hint_y=None, height=dp(40))
            E.fondo(fila, E.BLANCO if i % 2 == 0 else (0.96, 0.97, 0.98, 1))
            nombre = f"{f['nombres']} {f['ap_paterno'] or ''} {f['ap_materno'] or ''}".strip()
            valores = [f["codigo"], f["fecha"].replace("T", "  "), nombre, f"{f['ci']} {f['ci_ext'] or ''}",
                       str(f["edad"]), f["sexo"], f["comunidad"] or "—"]
            for (_, w), v in zip(COLUMNAS[:-1], valores):
                fila.add_widget(E.etiqueta(v, "14sp", E.TINTA, alto=dp(40), size_hint_x=w))
            b = E.boton("Control  >", E.VERDE, font_size="14sp", bold=True, size_hint_x=COLUMNAS[-1][1])
            b.bind(on_release=lambda _b, ci=f["ci"], ext=f["ci_ext"]: self._elegir(ci, ext))
            fila.add_widget(b)
            self.lista.add_widget(fila)

    def _elegir(self, ci, ext):
        p = self.bd.buscar_ci(ci, ext) or self.bd.buscar_ci(ci)
        if p:
            self.al_elegir(p)

    def on_pre_enter(self, *_):
        self.refrescar()