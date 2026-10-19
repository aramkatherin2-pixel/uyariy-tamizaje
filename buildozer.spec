[app]
title = Uyariy
package.name = uyariy
package.domain = bo.univalle
source.dir = .
source.include_exts = py,png,jpg,kv,json,wav
source.exclude_dirs = .venv,tests,bin,.buildozer,__pycache__,.pytest_cache
version = 0.6.0
requirements = python3,kivy==2.3.1,numpy,pyjnius,sqlite3
orientation = landscape
fullscreen = 1
android.permissions = RECORD_AUDIO, MODIFY_AUDIO_SETTINGS, WAKE_LOCK
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 0