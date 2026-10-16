"""
Compila el APK de Uyariy con Buildozer (usado por GitHub Actions).
Si python-for-android intenta instalar la rueda Android de charset_normalizer
(incompatible), aplica un parche para usar charset-normalizer 3.3.2 (Python puro)
y reintenta automáticamente.
"""
import glob
import os
import shutil
import subprocess
import sys

P4A = ".buildozer/android/platform/python-for-android/pythonforandroid/build.py"
VENV = ".buildozer/android/platform/build-arm64-v8a/build/venv"


def parchar():
    if not os.path.exists(P4A):
        return False
    codigo = open(P4A).read()
    if "# UYARIY" in codigo:
        return True
    ancla = "with open('requirements.txt', 'w') as fileh:"
    i = codigo.index(ancla)
    sangria = codigo[codigo.rindex("\n", 0, i) + 1:i]
    linea = ("modules = ['charset-normalizer==3.3.2' if 'charset_normalizer' in m or 'charset-normalizer' in m "
             "else m for m in modules]  # UYARIY\n")
    open(P4A, "w").write(codigo[:i] + linea + sangria + codigo[i:])
    print("Parche charset_normalizer aplicado", flush=True)
    return True


def compilar(n):
    log = f"build_{n}.log"
    with open(log, "w") as fh:
        proc = subprocess.Popen("yes | buildozer -v android debug", shell=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="ignore")
        for linea in proc.stdout:
            fh.write(linea)
            if not linea.lstrip().startswith("[DEBUG]"):
                print(linea.rstrip()[:200], flush=True)
        proc.wait()
    return log


parchar()
log = compilar(1)
if not glob.glob("bin/*.apk") and "charset_normalizer" in open(log, errors="ignore").read():
    parchar()
    shutil.rmtree(VENV, ignore_errors=True)
    log = compilar(2)

apks = glob.glob("bin/*.apk")
print("APK:", apks, flush=True)
sys.exit(0 if apks else 1)