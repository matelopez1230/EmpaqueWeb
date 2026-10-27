from flask import Blueprint, render_template, request, jsonify, send_file
from routes.decorators import menu_required

import os
import sqlite3

from smb_client import SMBClient


visor_pdf_bp = Blueprint("visor_pdf", __name__)


# -------------------------------------------------------------------
# Base SQLite
# -------------------------------------------------------------------

def get_db():

    return sqlite3.connect(
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "pdf_index.db"
        )
    )


# -------------------------------------------------------------------
# Página principal
# -------------------------------------------------------------------

@visor_pdf_bp.route("/visor-pdf")
@menu_required("/visor-pdf")
def index():

    return render_template("visor_pdf/index.html")


# -------------------------------------------------------------------
# Buscar PDFs
# -------------------------------------------------------------------

@visor_pdf_bp.route("/visor-pdf/buscar")
@menu_required("/visor-pdf")
def buscar():

    filtro = request.args.get("filtro", "").strip()

    if filtro == "":
        return jsonify({
            "success": True,
            "archivos": []
        })

    conn = get_db()

    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    cur.execute("""
        SELECT
            nombre,
            ruta,
            carpeta
        FROM pdfs
        WHERE lower(nombre) LIKE ?
        ORDER BY nombre
        LIMIT 200
    """, (f"%{filtro.lower()}%",))

    filas = cur.fetchall()

    conn.close()

    archivos = []

    for fila in filas:

        archivos.append({

            "nombre": fila["nombre"],

            "ruta": fila["ruta"],

            "carpeta": fila["carpeta"],

            "es_carpeta": False

        })

    return jsonify({

        "success": True,

        "archivos": archivos

    })


# -------------------------------------------------------------------
# Abrir PDF
# -------------------------------------------------------------------

@visor_pdf_bp.route("/visor-pdf/ver/<path:ruta>")
@menu_required("/visor-pdf")
def ver_pdf(ruta):

    smb = SMBClient()

    try:

        smb.conectar()

        ruta = ruta.replace("/", "\\")

        pdf = smb.leer_archivo(ruta)

        return send_file(
            pdf,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=os.path.basename(ruta)
        )

    finally:

        smb.desconectar()