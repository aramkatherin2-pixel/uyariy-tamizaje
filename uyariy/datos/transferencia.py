"""
Mover respaldos entre equipos (tablet <-> laptop) sin internet.

- publicar():  copia el archivo exportado a una carpeta visible.
    * PC (Windows): Documentos\\Uyariy\\Respaldos
    * Android 10 o más: Documentos/Uyariy/Respaldos (MediaStore, no pide permisos)
    * Android 9 o menos: carpeta de la app (Android/data/.../files/Respaldos)
- compartir(): Android abre el menú Compartir (WhatsApp, Drive, correo, Bluetooth...);
               en la PC abre la carpeta.
- elegir_android(): abre el selector de archivos de Android para importar un respaldo
               (en la PC el selector es una ventana de Kivy, ver ui/historial.py).
"""
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime

ES_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ
MIME = {".json": "application/json", ".csv": "text/csv"}
CODIGO_ABRIR = 7301          # identifica la respuesta del selector de archivos de Android
RESULT_OK = -1


def nombre_archivo(tipo, ahora=None):
    """tipo: 'respaldo' (.json) o 'tabla' (.csv para Excel)."""
    ahora = ahora or datetime.now()
    if tipo == "respaldo":
        return f"Uyariy_respaldo_{ahora:%Y%m%d_%H%M}.json"
    return f"Uyariy_tabla_{ahora:%Y%m%d_%H%M}.csv"


def nombre_equipo():
    """Nombre del equipo que exporta (va dentro del respaldo)."""
    if ES_ANDROID:
        try:
            from jnius import autoclass
            b = autoclass("android.os.Build")
            return f"{b.MANUFACTURER} {b.MODEL}"
        except Exception:                                    # noqa: BLE001
            return "Tableta Android"
    return socket.gethostname()


def carpeta_temporal(base):
    ruta = os.path.join(base, "respaldos")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def carpeta_pc():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    ruta = os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "Uyariy", "Respaldos")
    os.makedirs(ruta, exist_ok=True)
    return ruta


# ------------------------------------------------------------------ exportar
def publicar(ruta_local):
    """Copia el archivo a una carpeta visible. Devuelve (texto_para_el_usuario, destino)."""
    if ES_ANDROID:
        return _publicar_android(ruta_local)
    destino = os.path.join(carpeta_pc(), os.path.basename(ruta_local))
    shutil.copy2(ruta_local, destino)
    return destino, destino


def compartir(destino):
    if ES_ANDROID:
        _compartir_android(destino)
    elif sys.platform.startswith("win"):
        os.startfile(os.path.dirname(destino))               # noqa: S606 (solo Windows)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", os.path.dirname(destino)])


def _actividad():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def _publicar_android(ruta_local):
    from jnius import autoclass

    actividad = _actividad()
    nombre = os.path.basename(ruta_local)
    mime = MIME.get(os.path.splitext(nombre)[1].lower(), "application/octet-stream")
    if autoclass("android.os.Build$VERSION").SDK_INT >= 29:
        valores = autoclass("android.content.ContentValues")()
        valores.put("_display_name", nombre)
        valores.put("mime_type", mime)
        valores.put("relative_path", "Documents/Uyariy/Respaldos")
        resolver = actividad.getContentResolver()
        uri = resolver.insert(autoclass("android.provider.MediaStore$Files").getContentUri("external"), valores)
        salida = resolver.openOutputStream(uri)
        with open(ruta_local, "rb") as f:
            salida.write(f.read())
        salida.close()
        return f"Documentos/Uyariy/Respaldos/{nombre}", uri
    carpeta = os.path.join(actividad.getExternalFilesDir(None).getAbsolutePath(), "Respaldos")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, nombre)
    shutil.copy2(ruta_local, destino)
    return destino, None


def _compartir_android(uri):
    if uri is None or isinstance(uri, str):
        raise RuntimeError("En esta versión de Android comparta el archivo desde el administrador de archivos.")
    from jnius import autoclass, cast

    Intent = autoclass("android.content.Intent")
    String = autoclass("java.lang.String")
    intent = Intent(Intent.ACTION_SEND)
    intent.setType("*/*")
    intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", uri))
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    elegir = Intent.createChooser(intent, cast("java.lang.CharSequence", String("Compartir respaldo")))
    _actividad().startActivity(elegir)


# ------------------------------------------------------------------ importar (Android)
def elegir_android(carpeta_destino, al_terminar):
    """
    Abre el selector de archivos de Android. Cuando el usuario elige uno, lo copia a
    carpeta_destino y llama al_terminar(ruta_local, error) en el hilo de Kivy.
    """
    from android import activity                             # módulo de python-for-android
    from jnius import autoclass
    from kivy.clock import Clock

    Intent = autoclass("android.content.Intent")

    def avisar(ruta, error):
        Clock.schedule_once(lambda _dt: al_terminar(ruta, error), 0)

    def respuesta(codigo, resultado, datos):
        if codigo != CODIGO_ABRIR:
            return
        activity.unbind(on_activity_result=respuesta)
        if resultado != RESULT_OK or datos is None or datos.getData() is None:
            avisar(None, None)                               # el usuario canceló
            return
        try:
            pfd = _actividad().getContentResolver().openFileDescriptor(datos.getData(), "r")
            destino = os.path.join(carpeta_destino, "importado.json")
            with os.fdopen(pfd.detachFd(), "rb") as origen, open(destino, "wb") as f:
                f.write(origen.read())
            avisar(destino, None)
        except Exception as e:                               # noqa: BLE001
            avisar(None, f"No se pudo leer el archivo: {e}")

    activity.bind(on_activity_result=respuesta)
    intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    intent.setType("*/*")                                    # algunos administradores no reconocen .json
    _actividad().startActivityForResult(intent, CODIGO_ABRIR)
