# routes/especificaciones/db_helpers.py
"""
Helpers para simplificar el acceso a SQL Server desde el módulo Especificaciones.

Uso típico en routes.py:

    from .db_helpers import fetch_all, fetch_one, execute, insert_returning_id

    # Listar
    filas = fetch_all("SELECT * FROM EspWebBorradores WHERE IdUsuario = ?", (uid,))

    # Buscar uno
    fila = fetch_one("SELECT * FROM EspWebBorradores WHERE IdBorrador = ?", (id_b,))

    # Insertar y obtener el ID
    nuevo_id = insert_returning_id(
        "INSERT INTO EspWebBorradores (...) VALUES (?, ?, ...)",
        (a, b, ...)
    )

    # Update / Delete
    filas_afectadas = execute(
        "UPDATE EspWebBorradores SET Titulo = ? WHERE IdBorrador = ?",
        (nuevo_titulo, id_b)
    )
"""
from contextlib import contextmanager
from db import get_db_connection


@contextmanager
def db_cursor():
    """
    Context manager que abre una conexión, entrega un cursor y:
      - hace commit si no hubo error
      - hace rollback si hubo excepción
      - cierra la conexión SIEMPRE

    Uso:
        with db_cursor() as cur:
            cur.execute("...", (...))
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError(
            "No se pudo conectar a la base de datos. "
            "Revisá la config en db.py (SERVER, DATABASE, USER, PASSWORD, TRUSTED)."
        )
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def fetch_all(query, params=()):
    """
    Ejecuta un SELECT y devuelve una lista de dicts.

    Devuelve [] si no hay filas.
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(query, params=()):
    """
    Ejecuta un SELECT y devuelve el primer resultado como dict.

    Devuelve None si no hay filas.
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def execute(query, params=()):
    """
    Ejecuta un INSERT/UPDATE/DELETE y devuelve el número de filas afectadas.
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        return cur.rowcount


def insert_returning_id(query, params=()):
    """
    Ejecuta un INSERT y devuelve el ID autogenerado (SCOPE_IDENTITY).

    Uso:
        nuevo_id = insert_returning_id(
            "INSERT INTO EspWebBorradores (IdUsuario, Titulo) VALUES (?, ?)",
            (uid, "Mi título")
        )

    Devuelve None si el INSERT no generó ID (por ejemplo, si la tabla
    no tiene columna IDENTITY).
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        cur.execute("SELECT SCOPE_IDENTITY()")
        row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])