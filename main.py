"""
Uyariy - Audiómetro de tamizaje para tableta.

Paso 4: Registro del paciente (SQLite) -> Audiometría (motor de audio).
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
from uyariy.ui.banco_audio import PantallaAudio
from uyariy.ui.historial import PantallaHistorial
from uyariy.ui.registro import PantallaRegistro

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
        self.historial = PantallaHistorial(self.bd, lambda: self.ir("registro"), self.nuevo_control,
                                           name="historial")
        self.audio = PantallaAudio(self.motor, lambda: self.ir("registro"), name="audio")
        for p in (self.registro, self.historial, self.audio):
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

    def on_pause(self):
        self.motor.detener()
        return True

    def on_stop(self):
        self.motor.detener()
        self.bd.cerrar()


if __name__ == "__main__":
    UyariyApp().run()