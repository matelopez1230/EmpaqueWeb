# db.py
"""
Capa de acceso a SQLite3: conexión, creación de tablas e inserción de datos.
El SQL vive como strings acá dentro, sin archivos .sql externos.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import datos

DB_PATH = Path("test.db")

# ─────────────────────────────────────────────
# Schema (DDL)
# ─────────────────────────────────────────────
DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS personas (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre   TEXT NOT NULL,
        apellido TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS permisos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        descripcion TEXT NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS personas_permisos (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        id_persona        INTEGER NOT NULL,
        id_permiso        INTEGER NOT NULL,
        numero_validacion INTEGER NOT NULL,
        UNIQUE (id_persona, id_permiso),
        FOREIGN KEY (id_persona) REFERENCES personas(id) ON DELETE CASCADE,
        FOREIGN KEY (id_permiso) REFERENCES permisos(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS menu (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        etiqueta   TEXT NOT NULL,
        ruta       TEXT NOT NULL UNIQUE,
        id_padre   INTEGER,
        orden      INTEGER NOT NULL DEFAULT 0,
        id_permiso INTEGER NOT NULL,
        activo     INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (id_permiso) REFERENCES permisos(id) ON DELETE CASCADE,
        FOREIGN KEY (id_padre)   REFERENCES menu(id)     ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pp_persona ON personas_permisos(id_persona)",
    "CREATE INDEX IF NOT EXISTS idx_pp_permiso ON personas_permisos(id_permiso)",
    "CREATE INDEX IF NOT EXISTS idx_menu_permiso ON menu(id_permiso)",
    "CREATE INDEX IF NOT EXISTS idx_menu_padre   ON menu(id_padre)",

        """
    CREATE TABLE IF NOT EXISTS departamentos (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS personas_departamento (
        id_persona      INTEGER PRIMARY KEY,
        id_departamento INTEGER NOT NULL,
        FOREIGN KEY (id_persona)      REFERENCES personas(id)      ON DELETE CASCADE,
        FOREIGN KEY (id_departamento) REFERENCES departamentos(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS especificaciones (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        id_departamento INTEGER NOT NULL,
        titulo          TEXT NOT NULL,
        contenido       TEXT NOT NULL,
        activo          INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (id_departamento) REFERENCES departamentos(id) ON DELETE CASCADE,
        UNIQUE (id_departamento, titulo)
    )
    """,
]


# ─────────────────────────────────────────────
# Conexión
# ─────────────────────────────────────────────
@contextmanager
def get_conn(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Inicialización
# ─────────────────────────────────────────────
def crear_tablas() -> None:
    with get_conn() as conn:
        for ddl in DDL:
            conn.execute(ddl)


def cargar_datos() -> None:
    """Inserta todos los datos de datos.py con executemany."""
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO permisos (id, descripcion) VALUES (?, ?)",
            datos.PERMISOS,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO personas (id, nombre, apellido) VALUES (?, ?, ?)",
            datos.PERSONAS,
        )
        conn.executemany(
            """INSERT OR IGNORE INTO personas_permisos
               (id_persona, id_permiso, numero_validacion)
               VALUES (?, ?, ?)""",
            datos.ASIGNACIONES,
        )
        conn.executemany(
            """INSERT OR IGNORE INTO menu
               (id, etiqueta, ruta, id_padre, orden, id_permiso, activo)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            datos.MENU,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO departamentos (id, nombre) VALUES (?, ?)",
            datos.DEPARTAMENTOS,
        )
        conn.executemany(
            """INSERT OR IGNORE INTO personas_departamento
               (id_persona, id_departamento) VALUES (?, ?)""",
            datos.PERSONAS_DEPARTAMENTO,
        )
        conn.executemany(
            """INSERT OR IGNORE INTO especificaciones
               (id, id_departamento, titulo, contenido, activo)
               VALUES (?, ?, ?, ?, ?)""",
            datos.ESPECIFICACIONES,
        )


def inicializar(reset: bool = False) -> None:
    """Crea la DB desde cero (o la reusa) y carga los datos."""
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"🗑  DB eliminada: {DB_PATH}")
    crear_tablas()
    cargar_datos()
    print(f"✅ DB lista en: {DB_PATH.resolve()}")