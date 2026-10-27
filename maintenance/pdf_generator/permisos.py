# maintenance/pdf_generator/permisos.py
"""
Verificación de permisos contra la SQLite de maintenance (test.db).
Se usa mientras no exista el menú en SQL Server.

Cuando se registre el menú en EmpWebMenus / EmpWebPermisosUsuario,
esta capa se puede reemplazar por la versión SQL Server sin tocar el resto.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "test.db"
PERMISO_ESPECIFICACIONES = 11


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def usuario_tiene_permiso(id_usuario: int,
                          id_permiso: int = PERMISO_ESPECIFICACIONES,
                          min_validacion: int = 0) -> bool:
    """True si el usuario tiene el permiso de Especificaciones en SQLite."""
    if not id_usuario:
        return False
    with _conn() as conn:
        row = conn.execute("""
            SELECT 1 FROM personas_permisos
            WHERE id_persona = ? AND id_permiso = ?
              AND numero_validacion >= ?
            LIMIT 1
        """, (id_usuario, id_permiso, min_validacion)).fetchone()
    return row is not None


def info_usuario(id_usuario: int) -> dict | None:
    """Datos básicos del usuario desde SQLite (para el encabezado del panel)."""
    if not id_usuario:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, nombre, apellido FROM personas WHERE id = ?",
            (id_usuario,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "nombre": f"{row['nombre']} {row['apellido']}".strip(),
    }