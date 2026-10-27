# maintenance/pdf_generator/storage.py
"""
Persistencia de especificaciones generadas:
- PDFs en disco (storage/<codigo_base>/...)
- Metadatos en SQLite (generated.db)
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR     = Path(__file__).resolve().parent
STORAGE_DIR  = BASE_DIR / "storage"
DB_PATH      = BASE_DIR / "generated.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS especificaciones_generadas (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario        INTEGER NOT NULL,
                usuario_nombre    TEXT NOT NULL,
                tipo              TEXT NOT NULL,
                codigo_base       TEXT NOT NULL,
                variante          TEXT NOT NULL DEFAULT '',
                revision          INTEGER NOT NULL DEFAULT 0,
                codigo_completo   TEXT NOT NULL,
                titulo            TEXT,
                cliente           TEXT,
                producto          TEXT,
                archivo_pdf       TEXT NOT NULL,
                datos_json        TEXT NOT NULL,
                fecha_generacion  TEXT NOT NULL,
                tamano_bytes      INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_codigo_base
                ON especificaciones_generadas(codigo_base);
            CREATE INDEX IF NOT EXISTS idx_usuario
                ON especificaciones_generadas(id_usuario);
        """)


_SANITIZE = re.compile(r"[^A-Za-z0-9_\-]")


def _sanitizar(texto: str) -> str:
    return _SANITIZE.sub("_", texto or "").strip("_") or "SIN_CODIGO"


def codigo_completo(codigo_base: str, variante: str) -> str:
    return f"{codigo_base.strip().upper()}{variante.strip().upper()}"


def siguiente_revision(codigo_base: str, variante: str) -> int:
    with _conn() as conn:
        row = conn.execute("""
            SELECT MAX(revision) AS max_rev
            FROM especificaciones_generadas
            WHERE codigo_base = ? AND variante = ?
        """, (codigo_base.upper(), variante.upper())).fetchone()
    max_rev = row["max_rev"] if row and row["max_rev"] is not None else -1
    return max_rev + 1


def guardar_especificacion(*, id_usuario, usuario_nombre, tipo,
                           codigo_base, variante, revision,
                           titulo, cliente, producto,
                           datos: dict, pdf_bytes: bytes) -> int:
    codigo_base = codigo_base.strip().upper()
    variante    = variante.strip().upper()
    base_san    = _sanitizar(codigo_base)
    carpeta     = STORAGE_DIR / base_san
    carpeta.mkdir(parents=True, exist_ok=True)

    nombre_archivo = f"{base_san}{variante}_rev{revision:02d}.pdf"
    ruta_abs       = carpeta / nombre_archivo
    ruta_rel       = f"{base_san}/{nombre_archivo}"

    ruta_abs.write_bytes(pdf_bytes)

    cod_completo = codigo_completo(codigo_base, variante)

    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO especificaciones_generadas
                (id_usuario, usuario_nombre, tipo,
                 codigo_base, variante, revision, codigo_completo,
                 titulo, cliente, producto,
                 archivo_pdf, datos_json, fecha_generacion, tamano_bytes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            id_usuario, usuario_nombre, tipo,
            codigo_base, variante, revision, cod_completo,
            titulo, cliente, producto,
            ruta_rel,
            json.dumps(datos, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            len(pdf_bytes),
        ))
        return cur.lastrowid


def obtener(id_esp: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM especificaciones_generadas WHERE id = ?",
            (id_esp,)
        ).fetchone()
    return dict(row) if row else None


def ruta_absoluta(esp: dict) -> Path:
    return STORAGE_DIR / esp["archivo_pdf"]


def versiones_de_familia(codigo_base: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT * FROM especificaciones_generadas
            WHERE codigo_base = ?
            ORDER BY variante ASC, revision DESC
        """, (codigo_base.upper(),)).fetchall()
    return [dict(r) for r in rows]


def ultimas_generadas(limite: int = 15, id_usuario: int | None = None) -> list[dict]:
    with _conn() as conn:
        if id_usuario is not None:
            rows = conn.execute("""
                SELECT * FROM especificaciones_generadas
                WHERE id_usuario = ?
                ORDER BY id DESC LIMIT ?
            """, (id_usuario, limite)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM especificaciones_generadas
                ORDER BY id DESC LIMIT ?
            """, (limite,)).fetchall()
    return [dict(r) for r in rows]


init_db()