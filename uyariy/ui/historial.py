"""Pantalla: historial de pacientes evaluados (búsqueda, exportar e importar respaldos)."""
import os

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from ..datos import intercambio as X
from ..datos import transferencia as T
from . import estilo as E
from .registro import BarraPasos

COLUMNAS = [("Código", 0.15), ("Fecha", 0.15), ("Paciente", 0.24), ("C.I.", 0.11),
            ("Edad", 0.06), ("Sexo", 0.05), ("Comunidad", 0.13), ("", 0.11)]


class PantallaHistorial(Screen):
    def __init__(self, bd, carpeta_datos, al_volver, al_elegir, **kw):
        super().__init__(**kw)
        self.bd = bd
        self.carpeta = T.carpeta_temporal(carpeta_datos)
        self.al_volver = al_volver
        self.al_elegir = al_elegir          # función(paciente_dict): nueva evaluación (control)
        self._popup = None
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

        # ---- barra de respaldos
        datos = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(14), 0, dp(14), dp(8)), spacing=dp(10))
        b_resp = E.boton("Exportar respaldo (.json)", E.AZUL, font_size="15sp", bold=True)
        b_csv = E.boton("Exportar a Excel (.csv)", E.VERDE, font_size="15sp", bold=True)
        b_imp = E.boton("Importar respaldo", E.AMBAR, E.TINTA, font_size="15sp", bold=True)
        b_resp.bind(on_release=lambda *_: self._exportar("respaldo"))
        b_csv.bind(on_release=lambda *_: self._exportar("tabla"))
        b_imp.bind(on_release=lambda *_: self._elegir_archivo())
        for w in (b_resp, b_csv, b_imp):
            datos.add_widget(w)
        raiz.add_widget(datos)
        self.estado = E.etiqueta("", "13sp", E.GRIS, alto=dp(24), padding=(dp(16), 0))
        raiz.add_widget(self.estado)

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

    # ------------------------------------------------------------------ lista
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
        self.estado.text = ""
        self.refrescar()

    # ------------------------------------------------------------------ ventanas
    def _ventana(self, titulo, texto, botones, alto=dp(260)):
        """botones: [(texto, color, funcion)]; cada botón cierra la ventana y luego llama a su función."""
        self._cerrar()
        caja = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
        caja.add_widget(E.etiqueta(texto, "15sp", E.BLANCO, alto=alto - dp(150)))
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        for t, color, fn in botones:
            b = E.boton(t, color, bold=True)
            b.bind(on_release=lambda _b, fn=fn: (self._cerrar(), fn and fn()))
            fila.add_widget(b)
        caja.add_widget(fila)
        self._popup = Popup(title=titulo, content=caja, size_hint=(None, None), size=(dp(620), alto),
                            auto_dismiss=False, title_size="17sp")
        self._popup.open()

    def _cerrar(self):
        if self._popup:
            self._popup.dismiss()
            self._popup = None

    def _error(self, texto):
        self.estado.text = f"[color=c9353b]{texto}[/color]"
        self._ventana("No se pudo completar", texto, [("Cerrar", E.GRIS_BTN, None)])

    # ------------------------------------------------------------------ exportar
    def _exportar(self, tipo):
        if not self.bd.total_pacientes():
            self._error("No hay pacientes para exportar.")
            return
        ruta = os.path.join(self.carpeta, T.nombre_archivo(tipo))
        try:
            if tipo == "respaldo":
                n_p, n_e = X.exportar(self.bd, ruta, T.nombre_equipo())
                que = f"Respaldo con {n_p} pacientes y {n_e} evaluaciones."
            else:
                n_e = X.exportar_csv(self.bd, ruta)
                que = f"Tabla para Excel con {n_e} evaluaciones."
            texto, destino = T.publicar(ruta)
        except Exception as e:                               # noqa: BLE001
            self._error(f"Error al exportar: {e}")
            return
        self.estado.text = f"[color=2e9959]Guardado: {texto}[/color]"
        pista = ("Use «Compartir» para enviarlo por WhatsApp, Drive, correo o Bluetooth, o cópielo por cable."
                 if T.ES_ANDROID else "Copie este archivo a la tablet (cable USB, Drive o WhatsApp).")
        self._ventana("Archivo exportado", f"{que}\n\nGuardado en:\n[b]{texto}[/b]\n\n{pista}",
                      [("Compartir" if T.ES_ANDROID else "Abrir carpeta", E.AZUL, lambda: self._compartir(destino)),
                       ("Cerrar", E.GRIS_BTN, None)], alto=dp(330))

    def _compartir(self, destino):
        try:
            T.compartir(destino)
        except Exception as e:                               # noqa: BLE001
            self._error(str(e))

    # ------------------------------------------------------------------ importar
    def _elegir_archivo(self):
        if T.ES_ANDROID:
            try:
                T.elegir_android(self.carpeta, self._archivo_elegido)
            except Exception as e:                           # noqa: BLE001
                self._error(f"No se pudo abrir el selector de archivos: {e}")
            return
        self._cerrar()
        caja = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        selector = FileChooserListView(path=T.carpeta_pc(), filters=["*.json"])
        caja.add_widget(selector)
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        ok = E.boton("Usar este archivo", E.AZUL, bold=True)
        no = E.boton("Cancelar", E.GRIS_BTN)
        ok.bind(on_release=lambda *_: selector.selection and (self._cerrar(),
                                                               self._archivo_elegido(selector.selection[0], None)))
        no.bind(on_release=lambda *_: self._cerrar())
        fila.add_widget(ok)
        fila.add_widget(no)
        caja.add_widget(fila)
        self._popup = Popup(title="Elija el respaldo de Uyariy (.json)", content=caja, size_hint=(0.8, 0.85),
                            auto_dismiss=False)
        self._popup.open()

    def _archivo_elegido(self, ruta, error):
        if error:
            self._error(error)
            return
        if not ruta:
            return                                           # canceló
        try:
            d = X.leer_respaldo(ruta)
        except ValueError as e:
            self._error(str(e))
            return
        origen = d.get("equipo") or "otro equipo"
        fecha = (d.get("exportado") or "").replace("T", " ")
        self._ventana("Confirmar importación",
                      f"El respaldo es de [b]{origen}[/b] ({fecha}) y contiene "
                      f"[b]{len(d.get('pacientes', []))} pacientes[/b] y "
                      f"[b]{len(d.get('evaluaciones', []))} evaluaciones[/b].\n\n"
                      "Se agregarán a esta tableta. No se borra ni se duplica nada.",
                      [("Importar", E.VERDE, lambda: self._importar(ruta)), ("Cancelar", E.GRIS_BTN, None)],
                      alto=dp(300))

    def _importar(self, ruta):
        try:
            r = X.importar(self.bd, ruta)
        except Exception as e:                               # noqa: BLE001
            self._error(f"Error al importar: {e}")
            return
        self.refrescar()
        texto = X.resumen_texto(r)
        self.estado.text = f"[color=2e9959]Importado: {texto}[/color]"
        self._ventana("Importación terminada", texto + ".", [("Aceptar", E.VERDE, None)])
