# maintenance/pdf_generator/routes.py
from flask import (
    Blueprint, render_template, request, session,
    abort, send_file, redirect, url_for, flash,
)
from functools import wraps
from datetime import datetime
import json

from .permisos import usuario_tiene_permiso, info_usuario
from .pdf_utils import generar_pdf, logo_base64
from . import storage


pdf_bp = Blueprint(
    "pdf_generator",
    __name__,
    template_folder="templates",
)


TIPOS = {
    "diseno_grafico":   {"nombre": "Diseño Gráfico",      "icono": "fas fa-drafting-compass", "color": "primary"},
    "material_empaque": {"nombre": "Material de Empaque", "icono": "fas fa-box",              "color": "success"},
    "etiqueta":         {"nombre": "Etiqueta",            "icono": "fas fa-tag",              "color": "warning"},
    "etiqueta_zebra":   {"nombre": "Etiqueta Zebra",      "icono": "fas fa-barcode",          "color": "danger"},
}


def requiere_permiso(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            abort(401)
        if not usuario_tiene_permiso(user_id):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _contexto_base():
    user_id = session.get("user_id")
    persona = info_usuario(user_id) or {
        "id": user_id,
        "nombre": session.get("username", "Usuario"),
    }
    return {
        "persona": persona,
        "tipos": TIPOS,
        "usuario": session.get("username", ""),
    }


@pdf_bp.route("/especificaciones-pdf")
@pdf_bp.route("/especificaciones-pdf/")
@requiere_permiso
def panel():
    ultimas = storage.ultimas_generadas(limite=15)
    return render_template("panel.html", ultimas=ultimas, **_contexto_base())


@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>")
@requiere_permiso
def formulario(tipo):
    if tipo not in TIPOS:
        abort(404)
    return render_template(
        "formulario.html",
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=None, **_contexto_base(),
    )


@pdf_bp.route("/especificaciones-pdf/nueva-version/<int:id_esp>")
@requiere_permiso
def nueva_version(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    tipo = esp["tipo"]
    if tipo not in TIPOS:
        abort(404)

    datos = json.loads(esp["datos_json"])
    prefill = {
        **datos,
        "codigo_base": esp["codigo_base"],
        "variante":    esp["variante"],
        "revision":    storage.siguiente_revision(esp["codigo_base"], esp["variante"]),
    }
    return render_template(
        "formulario.html",
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=prefill, **_contexto_base(),
    )


@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>/pdf", methods=["POST"])
@requiere_permiso
def generar(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos = request.form.to_dict()

    codigo_base = datos.get("codigo_base", "").strip().upper()
    variante    = datos.get("variante", "").strip().upper()

    if not codigo_base:
        flash("El código base es obligatorio", "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    try:
        revision = int(datos.get("revision", "0"))
    except ValueError:
        revision = 0

    datos.update({
        "tipo_nombre":      TIPOS[tipo]["nombre"],
        "codigo_completo":  storage.codigo_completo(codigo_base, variante),
        "revision_str":     f"{revision:02d}",
        "usuario":          session.get("username", ""),
        "fecha_generacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "logo_base64":      logo_base64(),
    })

    html = render_template(f"pdf/{tipo}.html", datos=datos)
    pdf_bytes = generar_pdf(html)

    id_esp = storage.guardar_especificacion(
        id_usuario=session.get("user_id"),
        usuario_nombre=session.get("username", ""),
        tipo=tipo,
        codigo_base=codigo_base,
        variante=variante,
        revision=revision,
        titulo=datos.get("titulo", ""),
        cliente=datos.get("cliente", ""),
        producto=datos.get("producto", ""),
        datos=datos,
        pdf_bytes=pdf_bytes,
    )

    flash(f"Especificación {datos['codigo_completo']} rev {revision:02d} generada", "success")
    return redirect(url_for("pdf_generator.ver", id_esp=id_esp))


@pdf_bp.route("/especificaciones-pdf/ver/<int:id_esp>")
@requiere_permiso
def ver(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    familia = storage.versiones_de_familia(esp["codigo_base"])
    return render_template("visor.html", esp=esp, familia=familia, **_contexto_base())


@pdf_bp.route("/especificaciones-pdf/descargar/<int:id_esp>")
@requiere_permiso
def descargar(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    ruta = storage.ruta_absoluta(esp)
    if not ruta.exists():
        abort(404)
    nombre = f"{esp['codigo_completo']}_rev{esp['revision']:02d}.pdf"
    return send_file(ruta, mimetype="application/pdf",
                     as_attachment=True, download_name=nombre)


@pdf_bp.route("/especificaciones-pdf/raw/<int:id_esp>")
@requiere_permiso
def raw(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    ruta = storage.ruta_absoluta(esp)
    if not ruta.exists():
        abort(404)
    return send_file(ruta, mimetype="application/pdf", as_attachment=False)