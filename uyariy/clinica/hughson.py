"""
Búsqueda automática de umbral por el método de Hughson-Westlake modificado
(ASHA 2005; AC40 "Automático - Hughson Westlake", manual pág. 29 y 42).

Regla "baja 10 / sube 5":
  1. Familiarización: se empieza en 30 dB HL. Si no responde, se sube de 20 en 20.
  2. Cada vez que el paciente RESPONDE, se baja 10 dB.
  3. Cada vez que NO responde, se sube 5 dB (presentaciones "ascendentes").
  4. Umbral = nivel más bajo con 2 respuestas de 3 presentaciones ascendentes
     (o 3 de 5, como el AC40).

Esta clase no hace sonar nada: solo decide el próximo nivel. Así se puede probar
con un "paciente simulado" y la pantalla se encarga del audio y los tiempos.
"""
from collections import defaultdict

INICIO = 30
SUBIDA_FAMILIARIZACION = 20
BAJADA = 10
SUBIDA = 5
MAX_PRESENTACIONES = 40           # seguridad: evita una prueba infinita


class HughsonWestlake:
    def __init__(self, maximo, minimo=-10, inicio=INICIO):
        self.maximo = int(maximo // 5 * 5)
        self.minimo = minimo
        self.nivel = min(inicio, self.maximo)
        self.fase = "familiarizacion"      # familiarizacion -> descenso -> ascenso
        self.intentos = defaultdict(int)   # presentaciones ascendentes por nivel
        self.aciertos = defaultdict(int)   # respuestas en presentaciones ascendentes
        self.historial = []                # [(nivel, respondió, fase)]
        self.umbral = None
        self.sin_respuesta = False

    @property
    def terminado(self):
        return self.umbral is not None or self.sin_respuesta

    def responder(self, oyo):
        """Registra la respuesta al nivel actual y calcula el siguiente nivel."""
        if self.terminado:
            return
        self.historial.append((self.nivel, bool(oyo), self.fase))
        if len(self.historial) >= MAX_PRESENTACIONES:
            self._cerrar_por_limite()
            return

        if self.fase == "familiarizacion":
            if oyo:
                self.fase = "descenso"
                self._bajar()
            elif self.nivel >= self.maximo:
                self.sin_respuesta = True
            else:
                self.nivel = min(self.nivel + SUBIDA_FAMILIARIZACION, self.maximo)
            return

        if self.fase == "ascenso":                       # presentación ascendente
            self.intentos[self.nivel] += 1
            if oyo:
                self.aciertos[self.nivel] += 1
                if self._criterio(self.nivel):
                    self.umbral = self.nivel
                    return

        if oyo:
            self.fase = "descenso"
            self._bajar()
        else:
            self.fase = "ascenso"
            if self.nivel >= self.maximo:
                self.sin_respuesta = True
            else:
                self.nivel += SUBIDA

    def _bajar(self):
        if self.nivel <= self.minimo:                    # oye incluso en el mínimo
            self.umbral = self.minimo
            return
        self.nivel = max(self.nivel - BAJADA, self.minimo)

    def _criterio(self, nivel):
        a, i = self.aciertos[nivel], self.intentos[nivel]
        return (a >= 2 and i <= 3) or (a >= 3 and i <= 5)

    def _cerrar_por_limite(self):
        """Si se agotan las presentaciones, usa el nivel ascendente con más aciertos."""
        candidatos = [n for n, a in self.aciertos.items() if a >= 1]
        if candidatos:
            self.umbral = min(candidatos, key=lambda n: (-self.aciertos[n], n))
        else:
            self.sin_respuesta = True


def fiabilidad(trampas, falsos_trampa, falsos_fuera, retest=()):
    """
    Evalúa la confiabilidad de las respuestas.
    trampas: presentaciones en silencio; falsos_trampa: respondió a una trampa;
    falsos_fuera: tocó el botón sin que hubiera estímulo; retest: [(primer, segundo)] umbral a 1 kHz.
    Devuelve (confiable: bool, mensajes: list).
    """
    mensajes = []
    if trampas and falsos_trampa / trampas > 0.25:
        mensajes.append(f"Respondió a {falsos_trampa} de {trampas} presentaciones en silencio")
    if falsos_fuera >= 5:
        mensajes.append(f"Tocó el botón {falsos_fuera} veces sin estímulo")
    for a, b in retest:
        if a is not None and b is not None and abs(a - b) > 10:
            mensajes.append(f"Re-test a 1 kHz no coincide ({a:.0f} vs {b:.0f} dB)")
    return (not mensajes), mensajes