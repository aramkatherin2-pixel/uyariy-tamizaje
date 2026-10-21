"""
Uyariy - Audiómetro de tamizaje para tableta.

Paso 8: Registro -> Audiometría manual o automática -> Resultados e informe PDF
        + Historial con exportar / importar respaldos (tablet <-> laptop).
Ejecutar:  python main.py
"""
import os

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import NoTransition, ScreenManager
from kivy.utils import platform

from uyariy.audio.calibracion import Calibracion
from uyariy.audio.motor import MotorAudio
from uyariy.datos.pacientes import BaseDatos
from uyariy.ui.automatica import PantallaAutomatica
from uyariy.ui.banco_audio import PantallaAudio
from uyariy.ui.historial import PantallaHistorial
from uyariy.ui.registro import PantallaRegistro
from uyariy.ui.resultados import PantallaResultados

if platform not in ("android", "ios"):
    Window.size = (1280, 800)
Window.softinput_mode = "below_target"   # el teclado no tapa el campo que se escribe


class UyariyApp(App):
    title = "Uyariy"

    def build(self):
        ruta_cal = os.path.join(self.user_data_dir, "calibracion.json")
        self.motor = MotorAudio(Calibracion.cargar(ruta_cal))
        self.bd = BaseDatos(os.path.join(self.user_data_dir, "uyariy.db"))
        self.paciente = None

        self.sm = ScreenManager(transition=NoTransition())
        self.registro = PantallaRegistro(self.bd, self.ir_audio, lambda: self.ir("historial"), name="registro")
        self.historial = PantallaHistorial(self.bd, self.user_data_dir, lambda: self.ir("registro"), self.nuevo_control,
                                           name="historial")
        self.audio = PantallaAudio(self.motor, lambda: self.ir("registro"), self.guardar_y_ver,
                                   self.ir_automatica, name="audio")
        self.auto = PantallaAutomatica(self.motor, self.fin_automatica, lambda: self.ir("audio"), name="auto")
        self.resultados = PantallaResultados(self.bd, self.user_data_dir, lambda: self.ir("audio"),
                                             lambda: self.ir("registro"), name="resultados")
        self.codigo_auto = None
        for p in (self.registro, self.historial, self.audio, self.auto, self.resultados):
            self.sm.add_widget(p)
        return self.sm

    def ir(self, nombre):
        self.sm.current = nombre

    def nuevo_control(self, paciente):
        """Desde el historial: abre el registro ya lleno para una nueva evaluación."""
        self.ir("registro")
        self.registro.preparar_control(paciente)

    def ir_audio(self, paciente, codigo):
        self.paciente = (paciente, codigo)
        self.audio.banco.mostrar_paciente(paciente, codigo)
        self.registro.limpiar()
        self.ir("audio")

    def ir_automatica(self):
        paciente, codigo = self.paciente
        if self.codigo_auto != codigo:          # paciente nuevo: prueba automática desde cero
            self.auto.preparar(paciente)
            self.codigo_auto = codigo
        self.ir("auto")

    def fin_automatica(self, umbrales, info):
        self.audio.banco.cargar_automatico(umbrales, info)
        self.ir("audio")

    def guardar_y_ver(self, codigo, datos):
        """Guarda los resultados y abre la pantalla de resultados e informe."""
        ok = self.bd.guardar_resultados(codigo, datos)
        if ok:
            paciente, _ = self.paciente
            self.resultados.mostrar(paciente, codigo, datos)
            self.ir("resultados")
        return ok

    def on_pause(self):
        self.motor.detener()
        return True

    def on_stop(self):
        self.motor.detener()
        self.bd.cerrar()


if __name__ == "__main__":
    UyariyApp().run()
