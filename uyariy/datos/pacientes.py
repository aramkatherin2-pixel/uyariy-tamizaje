"""
Base de datos local de pacientes (SQLite, incluido en Python: funciona sin internet).

Guarda en la tableta los datos de identificación, procedencia, antecedentes y
consentimiento de cada paciente. Cada evaluación nueva de un mismo C.I. reutiliza
el registro del paciente (no se duplica).
"""
import json
import os
import sqlite3
from datetime import date, datetime

DEPARTAMENTOS = ["La Paz", "Cochabamba", "Santa Cruz", "Oruro", "Potosí",
                 "Chuquisaca", "Tarija", "Beni", "Pando"]
EXTENSIONES_CI = ["LP", "CB", "SC", "OR", "PT", "CH", "TJ", "BE", "PD"]
IDIOMAS = ["Castellano", "Aymara", "Quechua", "Guaraní", "Otro"]
ESCOLARIDAD = ["No refiere", "Ninguna", "Alfabetización adultos", "Primaria incompleta",
               "Primaria completa", "Secundaria incompleta", "Secundaria completa",
               "Técnico", "Universitario", "Posgrado"]
MOTIVOS = ["Tamizaje comunitario", "Control / seguimiento", "Queja auditiva", "Zumbido (acúfeno)",
           "Adulto mayor", "Escolar", "Laboral / exposición a ruido", "Preocupacional",
           "Control por medicamentos ototóxicos", "Referido por médico", "Otro"]
ANTECEDENTES = ["Dificultad para oír", "Zumbido (acúfeno)", "Dolor de oído (otalgia)",
                "Supuración (otorrea)", "Mareo o vértigo", "Exposición a ruido",
                "Infecciones de oído previas", "Medicamentos ototóxicos",
                "Familiares con sordera", "Usa audífono", "Cerumen visible",
                "Diabetes / hipertensión", "Traumatismo craneal", "Cirugía de oído"]
OIDO_DIFICULTAD = ["Derecho", "Izquierdo", "Ambos", "Ninguno"]

CAMPOS = ["ci", "ci_ext", "nombres", "ap_paterno", "ap_materno", "fecha_nac", "sexo",
          "telefono", "idioma", "ocupacion", "escolaridad", "tutor",
          "departamento", "provincia", "municipio", "comunidad"]


# ------------------------------------------------------------------ utilidades
def leer_fecha(texto):
    """Convierte 'dd/mm/aaaa' en date. Lanza ValueError si no es válida."""
    texto = (texto or "").strip()
    return datetime.strptime(texto, "%d/%m/%Y").date()


def calcular_edad(nacimiento, hoy=None):
    hoy = hoy or date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def validar(datos, hoy=None):
    """Devuelve una lista de mensajes de error (vacía si todo está bien)."""
    hoy = hoy or date.today()
    errores = []
    if not datos.get("nombres", "").strip():
        errores.append("Falta el nombre")
    if not datos.get("ap_paterno", "").strip() and not datos.get("ap_materno", "").strip():
        errores.append("Falta al menos un apellido")
    ci = datos.get("ci", "").strip()
    if not ci.isdigit() or not 5 <= len(ci) <= 10:
        errores.append("C.I. inválido (solo números, 5 a 10 dígitos)")
    try:
        nac = leer_fecha(datos.get("fecha_nac"))
        if nac > hoy:
            errores.append("La fecha de nacimiento está en el futuro")
        elif calcular_edad(nac, hoy) > 120:
            errores.append("Fecha de nacimiento no válida")
        elif calcular_edad(nac, hoy) < 18 and not datos.get("tutor", "").strip():
            errores.append("Paciente menor de edad: registra el nombre y C.I. del tutor")
    except ValueError:
        errores.append("Fecha de nacimiento: usa el formato dd/mm/aaaa")
    if datos.get("sexo") not in ("F", "M"):
        errores.append("Elige el sexo")
    tel = datos.get("telefono", "").strip()
    if tel and (not tel.isdigit() or len(tel) not in (7, 8)):
        errores.append("Teléfono: 7 u 8 dígitos")
    if not datos.get("consentimiento"):
        errores.append("Falta el consentimiento informado")
    return errores


# ---------------------------------------------------------------- base de datos
class BaseDatos:
    def __init__(self, ruta):
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        self.ruta = ruta
        self.con = sqlite3.connect(ruta)
        self.con.row_factory = sqlite3.Row
        self._crear()

    def _crear(self):
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ci TEXT NOT NULL, ci_ext TEXT,
            nombres TEXT NOT NULL, ap_paterno TEXT, ap_materno TEXT,
            fecha_nac TEXT NOT NULL, sexo TEXT NOT NULL,
            telefono TEXT, idioma TEXT, ocupacion TEXT, escolaridad TEXT, tutor TEXT,
            departamento TEXT, provincia TEXT, municipio TEXT, comunidad TEXT,
            creado TEXT NOT NULL,
            UNIQUE (ci, ci_ext)
        );
        CREATE TABLE IF NOT EXISTS evaluaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
            fecha TEXT NOT NULL,
            edad INTEGER,
            motivo TEXT, establecimiento TEXT, evaluador TEXT,
            antecedentes TEXT, oido_dificultad TEXT, observaciones TEXT,
            consentimiento INTEGER NOT NULL,
            resultados TEXT
        );
        """)
        self.con.commit()

    def cerrar(self):
        self.con.close()

    # ---------------------------------------------------------------- pacientes
    def buscar_ci(self, ci, ext=None):
        if ext:
            fila = self.con.execute("SELECT * FROM pacientes WHERE ci=? AND ci_ext=?", (ci, ext)).fetchone()
        else:
            fila = self.con.execute("SELECT * FROM pacientes WHERE ci=? ORDER BY id DESC", (ci,)).fetchone()
        return dict(fila) if fila else None

    def guardar_paciente(self, datos):
        """Crea o actualiza el paciente (identificado por C.I. + extensión). Devuelve su id."""
        valores = {c: (datos.get(c) or "").strip() for c in CAMPOS}
        existente = self.buscar_ci(valores["ci"], valores["ci_ext"])
        if existente:
            sets = ", ".join(f"{c}=?" for c in CAMPOS)
            self.con.execute(f"UPDATE pacientes SET {sets} WHERE id=?",
                             [valores[c] for c in CAMPOS] + [existente["id"]])
            self.con.commit()
            return existente["id"]
        cols = ", ".join(CAMPOS + ["creado"])
        marcas = ", ".join("?" * (len(CAMPOS) + 1))
        cur = self.con.execute(f"INSERT INTO pacientes ({cols}) VALUES ({marcas})",
                               [valores[c] for c in CAMPOS] + [datetime.now().isoformat(timespec="seconds")])
        self.con.commit()
        return cur.lastrowid

    # ------------------------------------------------------------- evaluaciones
    def nuevo_codigo(self, hoy=None):
        hoy = hoy or date.today()
        n = self.con.execute("SELECT COUNT(*) FROM evaluaciones WHERE codigo LIKE ?",
                             (f"UY-{hoy.year}-%",)).fetchone()[0]
        return f"UY-{hoy.year}-{n + 1:06d}"

    def registrar(self, datos, ahora=None):
        """Valida, guarda el paciente y abre una evaluación. Devuelve (paciente_id, codigo)."""
        ahora = ahora or datetime.now()
        errores = validar(datos, ahora.date())
        if errores:
            raise ValueError("; ".join(errores))
        pid = self.guardar_paciente(datos)
        codigo = datos.get("codigo") or self.nuevo_codigo(ahora.date())
        edad = calcular_edad(leer_fecha(datos["fecha_nac"]), ahora.date())
        self.con.execute(
            """INSERT INTO evaluaciones (codigo, paciente_id, fecha, edad, motivo, establecimiento,
               evaluador, antecedentes, oido_dificultad, observaciones, consentimiento)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (codigo, pid, ahora.isoformat(timespec="minutes"), edad, datos.get("motivo", ""),
             datos.get("establecimiento", ""), datos.get("evaluador", ""),
             json.dumps(datos.get("antecedentes", []), ensure_ascii=False),
             datos.get("oido_dificultad", ""), datos.get("observaciones", ""), 1))
        self.con.commit()
        return pid, codigo

    def historial(self, texto=""):
        """Últimas evaluaciones (más recientes primero), filtrando por nombre o C.I."""
        filtro = f"%{texto.strip()}%"
        filas = self.con.execute(
            """SELECT e.codigo, e.fecha, e.edad, e.motivo, p.ci, p.ci_ext, p.nombres,
                      p.ap_paterno, p.ap_materno, p.sexo, p.comunidad
               FROM evaluaciones e JOIN pacientes p ON p.id = e.paciente_id
               WHERE p.ci LIKE ? OR p.nombres LIKE ? OR p.ap_paterno LIKE ? OR p.ap_materno LIKE ?
               ORDER BY e.id DESC LIMIT 200""", (filtro,) * 4).fetchall()
        return [dict(f) for f in filas]

    def total_pacientes(self):
        return self.con.execute("SELECT COUNT(*) FROM pacientes").fetchone()[0]