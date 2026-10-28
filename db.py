# db.py — conexión a SQL Server con fallback
import pyodbc

# ═══════════════════════════════════════════════════════════
# Configuración: ajustá acá si tu entorno cambia
# ═══════════════════════════════════════════════════════════
SERVER   = r"192.168.8.5\TSSQL"
DATABASE = "GestionWeb"
USER     = "sa"
PASSWORD = ""          # completá si tu 'sa' tiene clave real
TRUSTED  = False       # True → Windows Auth (ignora USER/PASSWORD)


def _drivers_candidatos():
    """Devuelve los drivers ODBC instalados, en orden de preferencia."""
    disponibles = pyodbc.drivers()
    for d in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server",
    ):
        if d in disponibles:
            yield d


def _construir_cadenas():
    """Genera varias cadenas de conexión, de la más moderna a la más básica."""
    for driver in _drivers_candidatos():
        base = (
            f"DRIVER={{{driver}}};"
            f"SERVER={SERVER};"
            f"DATABASE={DATABASE};"
            "TrustServerCertificate=yes;"
            "Encrypt=no;"
            "Connection Timeout=10;"
        )
        if TRUSTED:
            yield base + "Trusted_Connection=yes;"
        else:
            yield base + f"UID={USER};PWD={PASSWORD};"


def get_db_connection():
    """
    Devuelve una conexión a SQL Server.
    Prueba todos los drivers disponibles hasta que uno funcione.
    """
    errores = []
    for cadena in _construir_cadenas():
        try:
            return pyodbc.connect(cadena, timeout=15)
        except pyodbc.Error as e:
            errores.append((cadena.split(";")[0], str(e)[:150]))
            continue

    print("[DB ERROR] No se pudo conectar con ninguna config:")
    for drv, err in errores:
        print(f"  {drv}: {err}")
    return None


# ─── Helper para convertir rows a dicts ───────────────────────
def row_to_dict(cursor, row):
    """Convierte una fila de pyodbc a dict usando los nombres de columna."""
    if row is None:
        return None
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def rows_to_dicts(cursor, rows):
    return [row_to_dict(cursor, r) for r in rows]