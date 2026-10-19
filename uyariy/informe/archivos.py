"""
Dónde se guardan los informes PDF y cómo abrirlos o compartirlos.

- PC (Windows): Documentos\\Uyariy\\Informes  (se abre con el lector de PDF).
- Android 10 o más: carpeta pública Documentos/Uyariy (MediaStore, no pide permisos);
  se puede abrir con el lector de PDF o compartir por WhatsApp, correo, Drive, etc.
- Android 9 o menos: carpeta de la app (Android/data/.../files/Informes).
Siempre queda además una copia interna en la carpeta de datos de la app.
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime

ES_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ


def nombre_pdf(codigo, ahora=None):
    ahora = ahora or datetime.now()
    return f"Informe_{codigo}_{ahora:%Y%m%d_%H%M}.pdf"


def carpeta_interna(base):
    ruta = os.path.join(base, "informes")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def carpeta_pc():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    ruta = os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "Uyariy", "Informes")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def publicar(ruta_local):
    """Copia el PDF a una carpeta visible. Devuelve (texto_para_el_usuario, destino)."""
    if ES_ANDROID:
        return _publicar_android(ruta_local)
    destino = os.path.join(carpeta_pc(), os.path.basename(ruta_local))
    shutil.copy2(ruta_local, destino)
    return destino, destino


def abrir(destino):
    """Abre el PDF con el programa del sistema."""
    if ES_ANDROID:
        _intent_android(destino, compartir=False)
    elif sys.platform.startswith("win"):
        os.startfile(destino)                                   # noqa: S606 (solo Windows)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", destino])


def compartir(destino):
    """Android: menú Compartir (WhatsApp, correo...). PC: abre la carpeta del informe."""
    if ES_ANDROID:
        _intent_android(destino, compartir=True)
    else:
        abrir(os.path.dirname(destino))


# ------------------------------------------------------------------ Android
def _publicar_android(ruta_local):
    from jnius import autoclass

    actividad = autoclass("org.kivy.android.PythonActivity").mActivity
    nombre = os.path.basename(ruta_local)
    if autoclass("android.os.Build$VERSION").SDK_INT >= 29:
        valores = autoclass("android.content.ContentValues")()
        valores.put("_display_name", nombre)
        valores.put("mime_type", "application/pdf")
        valores.put("relative_path", "Documents/Uyariy")
        resolver = actividad.getContentResolver()
        uri = resolver.insert(autoclass("android.provider.MediaStore$Files").getContentUri("external"), valores)
        salida = resolver.openOutputStream(uri)
        with open(ruta_local, "rb") as f:
            salida.write(f.read())
        salida.close()
        return f"Documentos/Uyariy/{nombre}", uri
    carpeta = os.path.join(actividad.getExternalFilesDir(None).getAbsolutePath(), "Informes")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, nombre)
    shutil.copy2(ruta_local, destino)
    return destino, None                                        # sin uri: no se puede abrir desde la app


def _intent_android(uri, compartir):
    if uri is None:
        raise RuntimeError("En esta versión de Android abre el PDF desde el administrador de archivos.")
    from jnius import autoclass, cast

    Intent = autoclass("android.content.Intent")
    String = autoclass("java.lang.String")
    actividad = autoclass("org.kivy.android.PythonActivity").mActivity
    if compartir:
        intent = Intent(Intent.ACTION_SEND)
        intent.setType("application/pdf")
        intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", uri))
        titulo = "Compartir informe"
    else:
        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(uri, "application/pdf")
        titulo = "Abrir informe"
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    elegir = Intent.createChooser(intent, cast("java.lang.CharSequence", String(titulo)))
    actividad.startActivity(elegir)