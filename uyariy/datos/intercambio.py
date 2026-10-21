"""
Exportar e importar datos entre equipos (tablet <-> laptop), SIN internet.

- Respaldo .json: todos los pacientes y evaluaciones con sus resultados. Se pasa por cable,
  WhatsApp, Drive, etc., y se importa en otro equipo.
- Tabla .csv (separador ";", se abre directo en Excel): una fila por evaluación, para análisis.

Reglas al importar (no se pierde ni se duplica nada):
  - Paciente: se reconoce por C.I. + extensión. Si ya existe, se conservan los datos locales.
  - Evaluación: se reconoce por código. Si el código ya existe y es del mismo paciente y misma
    fecha, es la MISMA evaluación (repetida): solo se completan los resultados si faltaban.
    Si el código existe pero es de otro paciente (dos tablets generaron el mismo número),
    se importa con un código nuevo: UY-2026-000001-B, -C, ...
"""
import csv
import json
from datetime import datetime

from .. import __version__
from ..clinica import clasificacion as C
from ..clinica import interpretacion as I
from .pacientes import CAMPOS

FORMATO = "uyariy-respaldo"
VERSION_FORMATO = 1
COLUMNAS_EVAL = ["codigo", "fecha", "edad", "motivo", "establecimiento", "evaluador", "antecedentes",
                 "oido_dificultad", "observaciones", "consentimiento", "resultados"]
FRECS_CSV = (250, 500, 1000, 2000, 3000, 4000, 6000, 8000)


def _json(texto, defecto):
    try:
        return json.loads(texto) if texto else defecto
    except (TypeError, ValueError):
        return defecto


def _clave(ci, ext):
    return f"{(ci or '').strip()}|{(ext or '').strip()}"


# ------------------------------------------------------------------ exportar
def datos_respaldo(bd, equipo=""):
    pacientes = [dict(f) for f in bd.con.execute("SELECT * FROM pacientes ORDER BY id")]
    clave_de = {p["id"]: _clave(p["ci"], p["ci_ext"]) for p in pacientes}
    evaluaciones = []
    for f in bd.con.execute("SELECT * FROM evaluaciones ORDER BY id"):
        e = {c: f[c] for c in COLUMNAS_EVAL}
        e["paciente"] = clave_de.get(f["paciente_id"], "")
        e["antecedentes"] = _json(e["antecedentes"], [])
        e["resultados"] = _json(e["resultados"], None)
        evaluaciones.append(e)
    return {"formato": FORMATO, "version": VERSION_FORMATO, "app": __version__, "equipo": equipo,
            "exportado": datetime.now().isoformat(timespec="seconds"),
            "pacientes": [{**{c: p[c] for c in CAMPOS}, "creado": p["creado"]} for p in pacientes],
            "evaluaciones": evaluaciones}


def exportar(bd, ruta, equipo=""):
    """Crea el archivo de respaldo .json. Devuelve (n_pacientes, n_evaluaciones)."""
    d = datos_respaldo(bd, equipo)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return len(d["pacientes"]), len(d["evaluaciones"])


def exportar_csv(bd, ruta):
    """Una fila por evaluación (para Excel). Devuelve el número de filas."""
    filas = bd.con.execute(
        """SELECT e.*, p.ci, p.ci_ext, p.nombres, p.ap_paterno, p.ap_materno, p.sexo, p.fecha_nac,
                  p.departamento, p.provincia, p.municipio, p.comunidad, p.ocupacion, p.idioma
           FROM evaluaciones e JOIN pacientes p ON p.id = e.paciente_id ORDER BY e.id""").fetchall()
    cab = (["codigo", "fecha", "ci", "nombres", "apellidos", "sexo", "edad", "departamento", "provincia",
            "municipio", "comunidad", "ocupacion", "idioma", "motivo", "establecimiento", "evaluador", "metodo",
            "veredicto", "pta_derecho", "pta_izquierdo", "grado_derecho", "grado_izquierdo", "ama_binaural_pct"]
           + [f"D_{f}" for f in FRECS_CSV] + [f"I_{f}" for f in FRECS_CSV]
           + ["antecedentes", "observaciones_evaluador", "verificacion"])
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:     # utf-8-sig: Excel lee bien las tildes
        w = csv.writer(fh, delimiter=";")
        w.writerow(cab)
        for f in filas:
            res = _json(f["resultados"], None) or {}
            umb = {o: C.desde_json((res.get("umbrales") or {}).get(o)) for o in ("D", "I")}
            r = I.interpretar(umb["D"], umb["I"], f["edad"], _json(f["antecedentes"], [])) if res else None
            ev = r["evaluacion"] if r else {"veredicto": "", "pta": {}, "grado": {}}

            def num(v):
                return "" if v is None else str(v).replace(".", ",")      # coma decimal para Excel en español

            def umbral(o, fr):
                u = umb[o].get(fr)
                return "" if u is None else (f">{u.db:.0f}" if u.nr else f"{u.db:.0f}")

            w.writerow([f["codigo"], f["fecha"], f"{f['ci']} {f['ci_ext'] or ''}".strip(), f["nombres"],
                        f"{f['ap_paterno'] or ''} {f['ap_materno'] or ''}".strip(), f["sexo"], f["edad"],
                        f["departamento"], f["provincia"], f["municipio"], f["comunidad"], f["ocupacion"],
                        f["idioma"], f["motivo"], f["establecimiento"], f["evaluador"], res.get("metodo", ""),
                        ev["veredicto"], num(ev["pta"].get("D")), num(ev["pta"].get("I")),
                        ev["grado"].get("D", ""), ev["grado"].get("I", ""),
                        num(r["ama"]["binaural"]) if r else ""]
                       + [umbral("D", fr) for fr in FRECS_CSV] + [umbral("I", fr) for fr in FRECS_CSV]
                       + [", ".join(_json(f["antecedentes"], [])), ", ".join(res.get("observaciones_evaluador", [])),
                          res.get("verificacion", "")])
    return len(filas)


# ------------------------------------------------------------------ importar
def leer_respaldo(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"No se pudo leer el archivo: {e}") from e
    if not isinstance(d, dict) or d.get("formato") != FORMATO:
        raise ValueError("Este archivo no es un respaldo de Uyariy.")
    if d.get("version", 0) > VERSION_FORMATO:
        raise ValueError("El respaldo es de una versión más nueva de Uyariy: actualice la app.")
    return d


def _codigo_libre(bd, codigo):
    for letra in "BCDEFGHIJKLMNOPQRSTUVWXYZ":
        nuevo = f"{codigo}-{letra}"
        if not bd.con.execute("SELECT 1 FROM evaluaciones WHERE codigo=?", (nuevo,)).fetchone():
            return nuevo
    raise ValueError(f"Demasiados códigos repetidos para {codigo}")


def importar(bd, ruta):
    """Suma los datos del respaldo a esta base. Devuelve un resumen con los conteos."""
    d = leer_respaldo(ruta)
    r = {"pacientes_nuevos": 0, "pacientes_existentes": 0, "evaluaciones_nuevas": 0,
         "evaluaciones_repetidas": 0, "codigos_cambiados": [], "omitidas": 0}
    ids = {}
    with bd.con:                                         # todo o nada (transacción)
        for p in d.get("pacientes", []):
            clave = _clave(p.get("ci"), p.get("ci_ext"))
            fila = bd.con.execute("SELECT id FROM pacientes WHERE ci=? AND ci_ext=?",
                                  ((p.get("ci") or "").strip(), (p.get("ci_ext") or "").strip())).fetchone()
            if fila:
                ids[clave] = fila["id"]
                r["pacientes_existentes"] += 1
                continue
            valores = [(p.get(c) or "").strip() for c in CAMPOS]
            if not valores[CAMPOS.index("ci")] or not valores[CAMPOS.index("nombres")]:
                continue
            cur = bd.con.execute(
                f"INSERT INTO pacientes ({', '.join(CAMPOS)}, creado) VALUES ({', '.join('?' * (len(CAMPOS) + 1))})",
                valores + [p.get("creado") or datetime.now().isoformat(timespec="seconds")])
            ids[clave] = cur.lastrowid
            r["pacientes_nuevos"] += 1

        for e in d.get("evaluaciones", []):
            pid = ids.get(e.get("paciente"))
            if not pid or not e.get("codigo") or not e.get("fecha"):
                r["omitidas"] += 1
                continue
            resultados = json.dumps(e["resultados"], ensure_ascii=False) if e.get("resultados") else None
            existe = bd.con.execute("SELECT id, paciente_id, fecha, resultados FROM evaluaciones WHERE codigo=?",
                                    (e["codigo"],)).fetchone()
            codigo = e["codigo"]
            if existe:
                if existe["paciente_id"] == pid and existe["fecha"] == e["fecha"]:
                    if resultados and not existe["resultados"]:
                        bd.con.execute("UPDATE evaluaciones SET resultados=? WHERE id=?", (resultados, existe["id"]))
                    r["evaluaciones_repetidas"] += 1
                    continue
                codigo = _codigo_libre(bd, e["codigo"])
                r["codigos_cambiados"].append((e["codigo"], codigo))
            bd.con.execute(
                """INSERT INTO evaluaciones (codigo, paciente_id, fecha, edad, motivo, establecimiento, evaluador,
                   antecedentes, oido_dificultad, observaciones, consentimiento, resultados)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (codigo, pid, e["fecha"], e.get("edad"), e.get("motivo", ""), e.get("establecimiento", ""),
                 e.get("evaluador", ""), json.dumps(e.get("antecedentes") or [], ensure_ascii=False),
                 e.get("oido_dificultad", ""), e.get("observaciones", ""), 1 if e.get("consentimiento") else 0,
                 resultados))
            r["evaluaciones_nuevas"] += 1
    return r


def resumen_texto(r):
    t = (f"{r['pacientes_nuevos']} pacientes nuevos, {r['evaluaciones_nuevas']} evaluaciones nuevas, "
         f"{r['evaluaciones_repetidas']} ya existían")
    if r["codigos_cambiados"]:
        t += f", {len(r['codigos_cambiados'])} con código cambiado (ej. {r['codigos_cambiados'][0][1]})"
    return t
