import sqlite3

from smb_client import SMBClient


def crear_base():

    conn = sqlite3.connect("pdf_index.db")

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdfs(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            nombre TEXT,
            ruta TEXT UNIQUE,
            carpeta TEXT
        )
    """)

    conn.commit()

    return conn


conn = crear_base()

cur = conn.cursor()

# Vaciamos el índice
cur.execute("DELETE FROM pdfs")

smb = SMBClient()

print("Conectando...")

smb.conectar()

print("Leyendo servidor...")

pdfs = smb.listar_todos_los_pdfs(
    smb.config["path"]
)

print(f"Encontrados: {len(pdfs)} PDFs")

for pdf in pdfs:

    carpeta = pdf["ruta"].rsplit("\\", 1)[0]

    cur.execute("""
        INSERT INTO pdfs
        (
            nombre,
            ruta,
            carpeta
        )
        VALUES
        (
            ?,?,?
        )
    """,
    (
        pdf["nombre"],
        pdf["ruta"],
        carpeta
    ))

conn.commit()

conn.close()

smb.desconectar()

print("Índice generado correctamente.")