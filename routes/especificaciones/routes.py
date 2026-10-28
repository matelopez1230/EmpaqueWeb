# routes/especificaciones/routes.py
from flask import (
    render_template, request, session,
    abort, send_file, redirect, url_for, flash,
    send_from_directory, jsonify,
)
from datetime import datetime, date
from pathlib import Path
import hashlib
import io
import json
import uuid as uuid_lib

from werkzeug.utils import secure_filename

from db import get_db_connection
from . import especificaciones_bp as bp
from .permisos import login_required
from .pdf_utils import generar_pdf, verificar_imagen, UPLOADS_DIR
from . import storage
from .envios_queue import encolar


# Asegurar que exista la carpeta de uploads
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

EXTENSIONES_PERMITIDAS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
HASHES_FILE = UPLOADS_DIR / "_hashes.json"

MAX_BORRADORES_POR_USUARIO = 10


TIPOS = {
    "diseno_grafico":   {"nombre": "Diseño Gráfico",      "icono": "fas fa-drafting-compass", "color": "primary"},
    "material_empaque": {"nombre": "Material de Empaque", "icono": "fas fa-box",              "color": "success"},
    "etiqueta":         {"nombre": "Etiqueta",            "icono": "fas fa-tag",              "color": "warning"},
    "etiqueta_zebra":   {"nombre": "Etiqueta Zebra",      "icono": "fas fa-barcode",          "color": "danger"},
}

TIPOS_CON_IMAGEN_OBLIGATORIA = {"etiqueta_zebra"}


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _template_formulario(tipo: str) -> str:
    templates = {
        'material_empaque': 'especificaciones/formulario_material_empaque.html',
        'etiqueta':         'especificaciones/formulario_etiqueta.html',
        'etiqueta_zebra':   'especificaciones/formulario_etiqueta_zebra.html',
    }
    return templates.get(tipo, 'especificaciones/formulario.html')

def _nombre_completo_actual():
    """Devuelve 'Nombre Apellido' del usuario logueado, con fallback a username."""
    user_id = session.get("user_id")
    if not user_id:
        return session.get("username", "")
    u = storage.obtener_usuario(user_id)
    if not u:
        return session.get("username", "")
    return u.get("nombre_completo") or u.get("nombre") or session.get("username", "")

def _contexto_base():
    return {
        "tipos":    TIPOS,
        "usuario":  _nombre_completo_actual(),          # ← ahora es nombre completo
        "es_admin": session.get("es_admin", False),
        "user_id":  session.get("user_id"),
        "usuarios_aprobadores": storage.listar_usuarios_aprobadores(),  # ← nuevo
    }


def _cargar_hashes() -> dict:
    if HASHES_FILE.exists():
        try:
            return json.loads(HASHES_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _guardar_hashes(d: dict) -> None:
    try:
        HASHES_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"⚠️  No se pudo guardar {HASHES_FILE}: {e}")


def _armar_filas_dinamicas(datos: dict) -> dict:
    TABLAS = {
        'p1':       ['param', 'valor', 'metodo'],
        'barrera':  ['param', 'valor', 'metodo'],
        'ps':       ['param', 'valor'],
        'quim':     ['param', 'valor', 'metodo'],
        'fis':      ['param', 'valor'],
        'elemento': ['num', 'nombre', 'items', 'criterios'],
        'dim':      ['param', 'medida', 'metodo'],
        'embalaje': ['titulo', 'texto'],
    }
    for prefijo, columnas in TABLAS.items():
        filas = []
        i = 1
        while True:
            fila = {}
            hay = False
            for col in columnas:
                k = f'{prefijo}_fila{i}_{col}'
                v = datos.get(k, '')
                if v:
                    hay = True
                fila[col] = v
            if not hay:
                break
            if not fila.get('num'):
                fila['num'] = str(i - 1)
            filas.append(fila)
            i += 1
            if i > 30:
                break
        datos[f'{prefijo}_filas'] = filas
    return datos


def _aplicar_fecha_default(datos: dict) -> dict:
    if not (datos.get("fecha_revision") or "").strip():
        datos["fecha_revision"] = date.today().strftime("%Y-%m-%d")
    return datos


def _completar_datos_autogenerados(datos, tipo, codigo_base, variante, revision):
    datos.update({
        "codigo_base":      codigo_base,
        "variante":         variante,
        "revision_str":     f"{revision:02d}",
        "codigo_completo":  storage.codigo_completo(codigo_base, variante),
        "usuario":          _nombre_completo_actual(),
        "fecha_generacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo_nombre":      TIPOS[tipo]["nombre"],
        "es_preliminar":    "1" if datos.get("es_preliminar") == "1" else "",
    })
    return datos


def _armar_anexo(datos, codigo_base, tipo, revision):
    if datos.get("incluir_anexo"):
        anteriores = storage.versiones_con_anexo(codigo_base, tipo)
        actual = {
            'fecha_revision': datos.get("fecha_revision", "") or "—",
            'revision':       f"{revision:02d}",
            'anexo':          datos.get("anexo_detalle_cambios", "") or "—",
        }
        datos["versiones_anteriores"] = anteriores + [actual]
    else:
        datos["versiones_anteriores"] = []
    return datos


def _validar_y_completar_datos(tipo):
    if tipo not in TIPOS:
        return None, {"error": "tipo_invalido", "msg": f"Tipo inválido: {tipo}"}

    datos = request.form.to_dict()
    codigo_base = datos.get("codigo_base", "").strip().upper()
    variante    = datos.get("variante", "").strip().upper()

    if not codigo_base:
        return None, {"error": "sin_codigo", "msg": "El código base es obligatorio"}

    datos = _aplicar_fecha_default(datos)

    if tipo in TIPOS_CON_IMAGEN_OBLIGATORIA:
        imagen = (datos.get("imagen") or "").strip()
        if not imagen:
            return None, {
                "error": "sin_imagen",
                "msg":   "La imagen de diseño es obligatoria para este tipo de documento",
            }

    try:
        revision = int(datos.get("revision_str", "0"))
    except ValueError:
        revision = 0

    datos = _completar_datos_autogenerados(datos, tipo, codigo_base, variante, revision)
    datos = _armar_filas_dinamicas(datos)
    datos = _armar_anexo(datos, codigo_base, tipo, revision)
    return datos, None


def _generar_pdf_bytes(tipo, datos):
    try:
        return generar_pdf(tipo, datos)
    except Exception as e:
        print(f"⚠️  Error generando PDF: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# PANEL PRINCIPAL
# ═══════════════════════════════════════════════════════════

@bp.route("/")
@login_required
def panel():
    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    publicadas  = storage.ultimas_publicadas(limite=20)
    mis_borr    = storage.listar_borradores_usuario(user_id)
    compartidos = storage.borradores_compartidos_conmigo(user_id, es_admin=es_admin)

    return render_template(
        "especificaciones/panel.html",
        ultimas=publicadas,
        borradores=mis_borr,
        compartidos=compartidos,
        max_borradores=MAX_BORRADORES_POR_USUARIO,
        **_contexto_base(),
    )


# ── Redirects de menú ─────────────────────────────────────
# El menú de la BD tiene entradas para /borradores, /generadas, etc.
# El panel ya muestra todo, así que redirigimos para no dar 404.
@bp.route("/tipo/<tipo>/panel")
@login_required
def tipo_panel(tipo):
    """Panel específico de cada tipo (Diseño Gráfico, Material Empaque, etc.)."""
    if tipo not in TIPOS:
        abort(404)

    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    borradores  = storage.listar_borradores_usuario_por_tipo(user_id, tipo)
    publicadas  = storage.ultimas_publicadas_por_tipo(tipo, limite=20)
    compartidos = storage.borradores_compartidos_por_tipo(user_id, tipo, es_admin)

    return render_template(
        "especificaciones/tipo_panel.html",
        tipo=tipo,
        tipo_info=TIPOS[tipo],
        borradores=borradores,
        publicadas=publicadas,
        compartidos=compartidos,
        **_contexto_base(),
    )

@bp.route("/contactos")
@login_required
def contactos():
    contactos_list = storage.listar_contactos()
    return render_template(
        "especificaciones/contactos.html",
        contactos=contactos_list,
        **_contexto_base(),
    )

# ═══════════════════════════════════════════════════════════
# FORMULARIOS
# ═══════════════════════════════════════════════════════════

@bp.route("/tipo/<tipo>")
@login_required
def formulario(tipo):
    if tipo not in TIPOS:
        abort(404)
    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=None, original=None, origen_id=None,
        borrador_id=None, borrador=None, permisos=None, otro_editando=None,
        **_contexto_base(),
    )


@bp.route("/borrador/<int:id_b>")
@login_required
def formulario_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        abort(404)

    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
    if not permisos or not permisos["puede_ver"]:
        abort(403)

    tipo = b["tipo"]
    if tipo not in TIPOS:
        abort(404)

    try:
        datos = json.loads(b["datos_json"] or "{}")
    except Exception:
        datos = {}

    storage.marcar_edicion_activa(id_b, user_id)
    otro_editando = storage.quien_esta_editando(id_b, id_usuario_actual=user_id)

    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=datos, original=None, origen_id=None,
        borrador_id=id_b, borrador=b,
        permisos=permisos, otro_editando=otro_editando,
        **_contexto_base(),
    )


@bp.route("/nueva-version/<int:id_esp>")
@login_required
def nueva_version(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    tipo = esp["tipo"]
    if tipo not in TIPOS:
        abort(404)

    b_existente = storage.obtener_borrador_de_familia(esp["codigo_base"], esp["variante"], tipo)
    if b_existente:
        flash(
            f"Ya tenés un borrador activo para {esp['codigo_base']}{esp['variante']} "
            f"(rev {b_existente['revision']:02d}). Te llevamos ahí.",
            "warning",
        )
        return redirect(url_for("especificaciones.formulario_borrador", id_b=b_existente["id"]))

    try:
        datos = json.loads(esp["datos_json"] or "{}")
    except Exception:
        datos = {}

    excluir = {"logo_base64", "tipo_nombre", "fecha_generacion",
               "usuario", "revision_str", "codigo_completo"}
    datos_limpios = {k: v for k, v in datos.items() if k not in excluir}

    siguiente = storage.siguiente_revision(esp["codigo_base"], esp["variante"], tipo)
    prefill = {
        **datos_limpios,
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision_str": f"{siguiente:02d}",
    }
    original = {
        **datos_limpios,
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision":     esp["revision"],
        "revision_str": f"{esp['revision']:02d}",
        "es_para_crear_a_partir_de": False,
    }

    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=prefill, original=original, origen_id=id_esp,
        borrador_id=None, borrador=None, permisos=None, otro_editando=None,
        **_contexto_base(),
    )


@bp.route("/crear-a-partir-de/<int:id_esp>")
@login_required
def crear_a_partir_de(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    tipo = esp["tipo"]
    if tipo not in TIPOS:
        abort(404)

    try:
        datos = json.loads(esp["datos_json"] or "{}")
    except Exception:
        datos = {}

    excluir = {"logo_base64", "tipo_nombre", "fecha_generacion",
               "usuario", "revision_str", "codigo_completo",
               "nombre_descarga", "versiones_anteriores"}
    datos_limpios = {k: v for k, v in datos.items() if k not in excluir}

    siguiente = storage.siguiente_revision(esp["codigo_base"], esp["variante"], tipo)

    prefill = {
        **datos_limpios,
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision_str": f"{siguiente:02d}",
    }
    original = {
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision_str": f"{siguiente:02d}",
        "es_para_crear_a_partir_de": True,
    }

    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=prefill, original=original, origen_id=None,
        crear_a_partir_de_id=id_esp,
        borrador_id=None, borrador=None, permisos=None, otro_editando=None,
        **_contexto_base(),
    )


# ═══════════════════════════════════════════════════════════
# GUARDAR BORRADOR / ELIMINAR / PUBLICAR
# ═══════════════════════════════════════════════════════════

@bp.route("/tipo/<tipo>/borrador", methods=["POST"])
@login_required
def guardar_borrador(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos, err = _validar_y_completar_datos(tipo)
    if err:
        flash(err["msg"], "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    id_b_str = datos.pop("borrador_id", "").strip()
    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    codigo_base = datos["codigo_base"]
    variante    = datos["variante"]
    revision    = int(datos["revision_str"])

    if id_b_str:
        try:
            id_b = int(id_b_str)
        except ValueError:
            id_b = None
        b = storage.obtener_borrador(id_b) if id_b else None
        if not b:
            flash("Borrador no encontrado", "danger")
            return redirect(url_for("especificaciones.panel"))

        permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
        if not permisos or not permisos["puede_editar"]:
            flash("No tenés permiso para editar este borrador.", "danger")
            return redirect(url_for("especificaciones.panel"))

        fecha_orig = datos.pop("fecha_actualizacion_original", "").strip()
        if storage.borrador_cambio_desde(id_b, fecha_orig):
            flash(
                "Este borrador fue modificado por otro usuario mientras lo editabas. "
                "Tus cambios NO se guardaron.",
                "warning",
            )
            return redirect(url_for("especificaciones.formulario_borrador", id_b=id_b))

        storage.actualizar_borrador(
            id_b,
            titulo=datos.get("titulo", ""),
            cliente=datos.get("cliente", ""),
            producto=datos.get("producto", ""),
            datos=datos,
        )
        storage.marcar_edicion_activa(id_b, user_id)
        flash("Borrador actualizado", "success")
        return redirect(url_for("especificaciones.formulario_borrador", id_b=id_b))

    if storage.contar_borradores(user_id) >= MAX_BORRADORES_POR_USUARIO:
        flash(f"Llegaste al máximo de {MAX_BORRADORES_POR_USUARIO} borradores.", "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    existente = storage.obtener_borrador_de_familia(codigo_base, variante, tipo)
    if existente:
        flash(
            f"Ya existe un borrador para {codigo_base}{variante} "
            f"(rev {existente['revision']:02d}).",
            "warning",
        )
        return redirect(url_for("especificaciones.formulario_borrador", id_b=existente["id"]))

    if storage.existe_publicado(codigo_base, variante, revision, tipo):
        flash(f"La revisión {revision:02d} ya fue publicada.", "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    id_b = storage.crear_borrador(
        id_usuario=user_id,
        usuario_nombre=session.get("username", ""),
        tipo=tipo,
        codigo_base=codigo_base,
        variante=variante,
        revision=revision,
        titulo=datos.get("titulo", ""),
        cliente=datos.get("cliente", ""),
        producto=datos.get("producto", ""),
        datos=datos,
    )
    flash(f"Borrador guardado: {codigo_base}{variante} rev {revision:02d}", "success")
    return redirect(url_for("especificaciones.formulario_borrador", id_b=id_b))


@bp.route("/borrador/<int:id_b>/eliminar", methods=["POST"])
@login_required
def eliminar_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        flash("Borrador no encontrado", "danger")
        return redirect(url_for("especificaciones.panel"))

    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
    if not permisos or not permisos["puede_eliminar"]:
        flash("No tenés permiso para eliminar este borrador.", "danger")
        return redirect(url_for("especificaciones.panel"))

    storage.eliminar_borrador(id_b)
    flash(f"Borrador {b['codigo_completo']} rev {b['revision']:02d} eliminado", "success")
    return redirect(url_for("especificaciones.panel"))


@bp.route("/tipo/<tipo>/publicar", methods=["POST"])
@login_required
def publicar(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos, err = _validar_y_completar_datos(tipo)
    if err:
        flash(err["msg"], "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    id_b_str = datos.pop("borrador_id", "").strip()
    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    codigo_base = datos["codigo_base"]
    variante    = datos["variante"]
    revision    = int(datos["revision_str"])

    if storage.existe_publicado(codigo_base, variante, revision, tipo):
        flash(f"Ya existe {codigo_base}{variante} rev {revision:02d}.", "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    pdf_bytes = _generar_pdf_bytes(tipo, datos)
    if pdf_bytes is None:
        flash("Error generando el PDF. Revisá la plantilla o los datos.", "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    fecha_rev = (datos.get("fecha_revision") or "").strip()
    nombre_descarga = storage.nombre_pdf_visible(tipo, codigo_base, variante, fecha_rev)

    id_publicado = None
    if id_b_str:
        try:
            id_b = int(id_b_str)
        except ValueError:
            id_b = None
        if id_b:
            b = storage.obtener_borrador(id_b)
            if not b:
                flash("Borrador no encontrado.", "danger")
                return redirect(url_for("especificaciones.panel"))

            permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
            if not permisos or not permisos["puede_publicar"]:
                flash("No tenés permiso para publicar este borrador.", "danger")
                return redirect(url_for("especificaciones.panel"))

            fecha_orig = datos.pop("fecha_actualizacion_original", "").strip()
            if storage.borrador_cambio_desde(id_b, fecha_orig):
                flash(
                    "Este borrador fue modificado por otro usuario mientras lo editabas. "
                    "Revisá la última versión antes de publicar.",
                    "warning",
                )
                return redirect(url_for("especificaciones.formulario_borrador", id_b=id_b))

            storage.actualizar_borrador(
                id_b,
                titulo=datos.get("titulo", ""),
                cliente=datos.get("cliente", ""),
                producto=datos.get("producto", ""),
                datos=datos,
            )
            id_publicado = storage.publicar_borrador(id_b, nombre_descarga=nombre_descarga)
            storage.limpiar_edicion_activa(id_b, user_id)

            if b["id_usuario"] != user_id:
                storage.crear_notificacion(
                    b["id_usuario"],
                    f"{b['codigo_completo']} fue publicado por {session.get('username')}",
                    url=url_for("especificaciones.ver", id_esp=id_publicado),
                )

    if id_publicado is None:
        id_publicado = storage.guardar_publicado(
            id_usuario=user_id,
            usuario_nombre=session.get("username", ""),
            tipo=tipo,
            codigo_base=codigo_base,
            variante=variante,
            revision=revision,
            titulo=datos.get("titulo", ""),
            cliente=datos.get("cliente", ""),
            producto=datos.get("producto", ""),
            nombre_descarga=nombre_descarga,
            datos=datos,
        )

    storage.bump_drafts_after_publish(codigo_base, variante, tipo, revision)

    flash(f"Publicado: {codigo_base}{variante} rev {revision:02d}", "success")
    return redirect(url_for("especificaciones.ver", id_esp=id_publicado))


# ═══════════════════════════════════════════════════════════
# GENERAR TEMPORAL / VISOR / DESCARGA
# ═══════════════════════════════════════════════════════════

@bp.route("/tipo/<tipo>/temporal", methods=["POST"])
@login_required
def generar_temporal(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos, err = _validar_y_completar_datos(tipo)
    if err:
        flash(err["msg"], "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    datos.pop("borrador_id", None)
    datos.pop("fecha_actualizacion_original", None)

    pdf_bytes = _generar_pdf_bytes(tipo, datos)
    if pdf_bytes is None:
        flash("Error generando el PDF.", "danger")
        return redirect(url_for("especificaciones.formulario", tipo=tipo))

    nombre = storage.nombre_pdf_visible(
        tipo, datos["codigo_base"], datos["variante"],
        (datos.get("fecha_revision") or "").strip(),
    )
    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nombre,
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route("/ver/<int:id_esp>")
@login_required
def ver(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    familia = storage.versiones_de_familia(esp["codigo_base"], tipo=esp["tipo"])
    return render_template(
        "especificaciones/visor.html",
        esp=esp, familia=familia, **_contexto_base(),
    )


def _pdf_de_publicado(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        return None, None
    datos = storage.obtener_datos(id_esp)
    if not datos:
        return None, esp
    pdf_bytes = _generar_pdf_bytes(esp["tipo"], datos)
    return pdf_bytes, esp


def _nombre_descarga_de(esp):
    nombre = esp.get("nombre_descarga")
    if nombre:
        return nombre
    try:
        datos = json.loads(esp["datos_json"] or "{}")
    except Exception:
        datos = {}
    return storage.nombre_pdf_visible(
        esp["tipo"], esp["codigo_base"], esp["variante"],
        datos.get("fecha_revision", ""),
    )


@bp.route("/descargar/<int:id_esp>")
@login_required
def descargar(id_esp):
    pdf_bytes, esp = _pdf_de_publicado(id_esp)
    if not esp:
        abort(404)
    if pdf_bytes is None:
        abort(500, "Error generando PDF")

    nombre = _nombre_descarga_de(esp)
    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nombre,
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route("/raw/<int:id_esp>")
@login_required
def raw(id_esp):
    pdf_bytes, esp = _pdf_de_publicado(id_esp)
    if not esp:
        abort(404)
    if pdf_bytes is None:
        abort(500, "Error generando PDF")

    nombre = _nombre_descarga_de(esp)
    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre,
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route("/eliminar/<int:id_esp>", methods=["POST"])
@login_required
def eliminar(id_esp):
    esp = storage.eliminar_publicado(id_esp)
    if not esp:
        flash("Especificación no encontrada", "danger")
        return redirect(url_for("especificaciones.panel"))

    flash(f"Eliminado: {esp['codigo_completo']} rev {esp['revision']:02d}", "success")
    return redirect(url_for("especificaciones.panel"))


# ═══════════════════════════════════════════════════════════
# BUSCADOR
# ═══════════════════════════════════════════════════════════

@bp.route("/tipo/<tipo>/buscar")
@login_required
def buscar_tipo(tipo):
    if tipo not in TIPOS:
        abort(404)
    return render_template(
        "especificaciones/buscar.html",
        tipo=tipo, tipo_info=TIPOS[tipo],
        **_contexto_base(),
    )


@bp.route("/buscar")
@login_required
def api_buscar():
    tipo = request.args.get("tipo", "").strip() or None
    q    = request.args.get("q", "").strip()
    if tipo and tipo not in TIPOS:
        tipo = None
    resultados = storage.buscar_publicadas(tipo=tipo, q=q)
    return {"success": True, "resultados": resultados}


@bp.route("/buscar-global")
@login_required
def api_buscar_global():
    q        = request.args.get("q", "").strip().upper()
    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    resultados = []

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql_base = """
            SELECT e.IdEspecificacion AS id, e.CodigoBase AS codigo_base,
                   e.CodigoCompleto AS codigo_completo, e.Variante AS variante,
                   e.Revision AS revision, e.Tipo AS tipo,
                   e.FechaGeneracion AS fecha_generacion,
                   e.NombreDescarga AS nombre_descarga,
                   u.NombreUsuario AS usuario_nombre
              FROM EspWebEspecificaciones e
              JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
              INNER JOIN (
                SELECT CodigoBase, Variante, Tipo, MAX(Revision) AS max_rev
                  FROM EspWebEspecificaciones
              GROUP BY CodigoBase, Variante, Tipo
              ) ult ON e.CodigoBase = ult.CodigoBase
                   AND e.Variante    = ult.Variante
                   AND e.Tipo        = ult.Tipo
                   AND e.Revision    = ult.max_rev
        """
        if q:
            like = f"%{q}%"
            cur.execute(sql_base + """
                WHERE UPPER(e.CodigoCompleto) LIKE ?
                   OR UPPER(e.CodigoBase)     LIKE ?
                   OR UPPER(COALESCE(e.NombreDescarga, '')) LIKE ?
                ORDER BY e.FechaGeneracion DESC
            """, (like, like, like))
        else:
            cur.execute(sql_base + " ORDER BY e.FechaGeneracion DESC")

        cols = [d[0] for d in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["_origen"] = "publicado"
            resultados.append(d)
        conn.close()
    except Exception as e:
        print(f"[buscar-global] publicados: {e}")

    try:
        for b in (storage.listar_borradores_usuario(user_id) or []):
            txt = " ".join(
                str(b.get(k, "") or "")
                for k in ("codigo_completo", "codigo_base", "variante", "tipo")
            ).upper()
            if q and q not in txt:
                continue
            resultados.append({
                "_origen":          "borrador",
                "id":               b.get("id"),
                "codigo_base":      b.get("codigo_base"),
                "codigo_completo":  b.get("codigo_completo"),
                "variante":         b.get("variante"),
                "revision":         b.get("revision"),
                "tipo":             b.get("tipo"),
                "fecha_generacion": b.get("fecha_actualizacion"),
                "usuario_nombre":   session.get("username", ""),
                "es_ultima":        b.get("es_ultima"),
            })
    except Exception as e:
        print(f"[buscar-global] borradores: {e}")

    try:
        for c in (storage.borradores_compartidos_conmigo(user_id, es_admin=es_admin) or []):
            txt = " ".join(
                str(c.get(k, "") or "")
                for k in ("codigo_completo", "codigo_base", "variante", "tipo")
            ).upper()
            if q and q not in txt:
                continue
            resultados.append({
                "_origen":          "compartido",
                "id":               c.get("id"),
                "codigo_base":      c.get("codigo_base"),
                "codigo_completo":  c.get("codigo_completo"),
                "variante":         c.get("variante"),
                "revision":         c.get("revision"),
                "tipo":             c.get("tipo"),
                "fecha_generacion": c.get("fecha_actualizacion"),
                "usuario_nombre":   c.get("dueno_nombre") or "",
                "es_ultima":        c.get("es_ultima"),
            })
    except Exception as e:
        print(f"[buscar-global] compartidos: {e}")

    return {"success": True, "resultados": resultados, "total": len(resultados)}


# ═══════════════════════════════════════════════════════════
# APIs para el frontend (versiones, borrador-familia)
# ═══════════════════════════════════════════════════════════

@bp.route("/api/versiones/<codigo_base>")
@login_required
def api_versiones(codigo_base):
    codigo_base = codigo_base.strip().upper()
    if not codigo_base:
        return {"existe": False, "total": 0, "versiones": []}

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.IdEspecificacion AS id, e.CodigoCompleto AS codigo_completo,
               e.Variante AS variante, e.Revision AS revision, e.Tipo AS tipo,
               e.FechaGeneracion AS fecha_generacion,
               u.NombreUsuario AS usuario_nombre
          FROM EspWebEspecificaciones e
          JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
         WHERE e.CodigoBase = ?
      ORDER BY e.Variante, e.Revision
    """, (codigo_base,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return {"existe": len(rows) > 0, "total": len(rows), "versiones": rows}


@bp.route("/api/borrador-familia/<codigo_base>/<tipo>")
@login_required
def api_borrador_familia(codigo_base, tipo):
    codigo_base = codigo_base.strip().upper()
    variante = request.args.get("variante", "").strip().upper()
    b = storage.obtener_borrador_de_familia(codigo_base, variante, tipo)
    if not b:
        return {"existe": False}
    return {"existe": True, "id": b["id"], "revision": b["revision"]}


# ═══════════════════════════════════════════════════════════
# COMPARTIR / PERMISOS
# ═══════════════════════════════════════════════════════════

@bp.route("/api/usuarios-compartir")
@login_required
def api_usuarios_compartir():
    user_id = session.get("user_id")
    usuarios = storage.usuarios_con_acceso_seccion("especificaciones")
    usuarios = [u for u in usuarios if u["id"] != user_id]
    return {"success": True, "usuarios": usuarios}


@bp.route("/api/permisos-globales")
@login_required
def api_permisos_globales():
    id_dueno = request.args.get("id_dueno", type=int) or session.get("user_id")
    if id_dueno != session.get("user_id") and not session.get("es_admin"):
        abort(403)
    return {"success": True, "permisos": storage.obtener_permisos_globales(id_dueno)}


@bp.route("/api/permisos-globales", methods=["POST"])
@login_required
def api_set_permisos_globales():
    data = request.get_json() or {}
    id_dueno = data.get("id_dueno") or session.get("user_id")

    if id_dueno != session.get("user_id") and not session.get("es_admin"):
        abort(403)

    anteriores = storage.obtener_permisos_globales(id_dueno)
    ids_antes = {p["id_usuario"] for p in anteriores}

    permisos = data.get("permisos", [])
    storage.set_permisos_globales(id_dueno, permisos)

    ids_ahora = {int(p["id_usuario"]) for p in permisos}
    for uid in (ids_antes - ids_ahora):
        storage.crear_notificacion(
            uid,
            f"{session.get('username')} te revocó el acceso a su banco de borradores.",
            url=url_for("especificaciones.panel"),
        )
    return {"success": True}


@bp.route("/api/permisos-borrador/<int:id_b>")
@login_required
def api_permisos_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        abort(404)
    if b["id_usuario"] != session.get("user_id") and not session.get("es_admin"):
        abort(403)
    return {
        "success": True,
        "permisos": storage.obtener_permisos_especificos(id_b),
        "id_dueno": b["id_usuario"],
    }


@bp.route("/api/permisos-borrador/<int:id_b>", methods=["POST"])
@login_required
def api_set_permisos_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        abort(404)
    if b["id_usuario"] != session.get("user_id") and not session.get("es_admin"):
        abort(403)

    anteriores = storage.obtener_permisos_especificos(id_b)
    ids_antes = {p["id_usuario"] for p in anteriores}

    data = request.get_json() or {}
    permisos = data.get("permisos", [])
    storage.set_permisos_especificos(id_b, permisos)

    ids_ahora = {int(p["id_usuario"]) for p in permisos}
    for uid in (ids_antes - ids_ahora):
        storage.crear_notificacion(
            uid,
            f"{session.get('username')} te revocó el acceso al borrador "
            f"{b['codigo_completo']} rev {b['revision']:02d}.",
            url=url_for("especificaciones.panel"),
        )
    return {"success": True}


# ═══════════════════════════════════════════════════════════
# NOTIFICACIONES
# ═══════════════════════════════════════════════════════════

@bp.route("/api/notificaciones")
@login_required
def api_notificaciones():
    user_id = session.get("user_id")
    no_leidas = storage.notificaciones_no_leidas(user_id)
    return {"success": True, "notificaciones": no_leidas}


@bp.route("/api/notificaciones/leer", methods=["POST"])
@login_required
def api_notif_marcar_leidas():
    data = request.get_json() or {}
    storage.marcar_notificaciones_leidas(session.get("user_id"), data.get("ids"))
    return {"success": True}


# ═══════════════════════════════════════════════════════════
# UPLOADS
# ═══════════════════════════════════════════════════════════

@bp.route("/subir-imagen", methods=["POST"])
@login_required
def subir_imagen():
    if 'archivo' not in request.files:
        return {"ok": False, "error": "No se envió archivo"}, 400
    archivo = request.files['archivo']
    if not archivo.filename:
        return {"ok": False, "error": "Nombre vacío"}, 400
    ext = Path(archivo.filename).suffix.lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        return {"ok": False, "error": f"Extensión no permitida: {ext}"}, 400

    contenido = archivo.read()
    if not contenido:
        return {"ok": False, "error": "Archivo vacío"}, 400

    hash_hex = hashlib.sha256(contenido).hexdigest()
    hashes   = _cargar_hashes()

    if hash_hex in hashes:
        nombre_existente = hashes[hash_hex]
        if (UPLOADS_DIR / nombre_existente).exists():
            return {
                "ok": True, "ruta": nombre_existente, "reutilizada": True,
                "url_preview": url_for(
                    "especificaciones.servir_upload", nombre=nombre_existente,
                ),
            }
        del hashes[hash_hex]

    nombre_seguro = secure_filename(archivo.filename)
    nombre_final  = f"{uuid_lib.uuid4().hex}_{nombre_seguro}"
    (UPLOADS_DIR / nombre_final).write_bytes(contenido)

    hashes[hash_hex] = nombre_final
    _guardar_hashes(hashes)

    return {
        "ok": True, "ruta": nombre_final, "reutilizada": False,
        "url_preview": url_for(
            "especificaciones.servir_upload", nombre=nombre_final,
        ),
    }


@bp.route("/uploads/<path:nombre>")
@login_required
def servir_upload(nombre):
    return send_from_directory(UPLOADS_DIR, nombre)


@bp.route("/verificar-imagen")
@login_required
def verificar_imagen_route():
    url = request.args.get("url", "").strip()
    valida, mensaje = verificar_imagen(url)
    return {"valida": valida, "mensaje": mensaje}


@bp.route("/borrador/<int:id_b>/heartbeat", methods=["POST"])
@login_required
def borrador_heartbeat(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        return {"success": False, "error": "no_existe"}, 404

    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
    if not permisos or not permisos["puede_ver"]:
        return {"success": False, "error": "sin_permiso"}, 403

    storage.marcar_edicion_activa(id_b, user_id)
    return {"success": True}


# ═══════════════════════════════════════════════════════════
# CORREO
# ═══════════════════════════════════════════════════════════

@bp.route("/api/mi-remitente")
@login_required
def api_mi_remitente():
    u = storage.obtener_usuario(session.get("user_id"))
    if not u:
        return {"success": False, "error": "Usuario no encontrado"}, 404
    return {"success": True, "email": u.get("email") or "", "nombre": u.get("nombre") or ""}


@bp.route("/api/mi-remitente", methods=["POST"])
@login_required
def api_set_mi_remitente():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"success": False, "error": "Email inválido"}, 400
    storage.actualizar_email_usuario(session.get("user_id"), email)
    return {"success": True, "email": email}


@bp.route("/api/contactos")
@login_required
def api_contactos():
    q = request.args.get("q", "").strip()
    return {"success": True, "contactos": storage.buscar_contactos(q)}

# ─── CRUD de contactos (para la página /contactos) ───

@bp.route("/api/contactos/crear", methods=["POST"])
@login_required
def api_crear_contacto():
    data   = request.get_json(silent=True) or {}
    email  = (data.get("email") or "").strip().lower()
    nombre = (data.get("nombre") or "").strip()

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"success": False, "error": "El email no es válido"}, 400

    id_contacto = storage.crear_contacto(email, nombre)
    if not id_contacto:
        return {"success": False, "error": "Ya existe un contacto con ese email"}, 400

    return {"success": True, "id": id_contacto}


@bp.route("/api/contactos/<int:id_contacto>/editar", methods=["POST"])
@login_required
def api_editar_contacto(id_contacto):
    if not storage.obtener_contacto(id_contacto):
        return {"success": False, "error": "Contacto no encontrado"}, 404

    data   = request.get_json(silent=True) or {}
    email  = (data.get("email") or "").strip().lower()
    nombre = (data.get("nombre") or "").strip()

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"success": False, "error": "El email no es válido"}, 400

    ok = storage.actualizar_contacto(id_contacto, email, nombre)
    if not ok:
        return {"success": False, "error": "Ese email ya está usado por otro contacto"}, 400

    return {"success": True}


@bp.route("/api/contactos/<int:id_contacto>/eliminar", methods=["POST"])
@login_required
def api_eliminar_contacto(id_contacto):
    if not storage.obtener_contacto(id_contacto):
        return {"success": False, "error": "Contacto no encontrado"}, 404

    storage.eliminar_contacto(id_contacto)
    return {"success": True}


@bp.route("/enviar/<int:id_esp>", methods=["POST"])
@login_required
def enviar_por_correo(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        return {"success": False, "error": "Documento no encontrado"}, 404

    data = request.get_json(silent=True) or {}
    destinatario = (data.get("destinatario") or "").strip().lower()
    mensaje      = (data.get("mensaje") or "").strip()

    if not destinatario or "@" not in destinatario:
        return {"success": False, "error": "Destinatario inválido"}, 400

    usuario = storage.obtener_usuario(session.get("user_id"))
    if not usuario or not (usuario.get("email") or "").strip():
        return {
            "success": False,
            "error": "Tu perfil no tiene email de envío configurado",
        }, 400

    asunto = f"{esp['codigo_completo']} rev {esp['revision']:02d} — Especificación"
    id_envio = storage.crear_envio(
        id_esp=id_esp,
        id_usuario=session.get("user_id"),
        destinatario=destinatario,
        remitente=usuario["email"].strip(),
        asunto=asunto,
        cuerpo=mensaje or "Adjunto encontrará la especificación solicitada.",
    )
    encolar(id_envio)
    return {"success": True, "id_envio": id_envio, "mensaje": "Envío en cola"}


@bp.route("/api/envio/<int:id_envio>/estado")
@login_required
def api_estado_envio(id_envio):
    e = storage.obtener_envio(id_envio)
    if not e:
        return {"success": False, "error": "Envío no encontrado"}, 404
    if e["id_usuario"] != session.get("user_id") and not session.get("es_admin"):
        return {"success": False, "error": "No autorizado"}, 403
    return {
        "success": True,
        "estado": e["estado"],
        "error": e.get("error"),
        "destinatario": e["destinatario"],
    }
# ═══════════════════════════════════════════════════════════
# [LEGACY] Abrir Outlook en el servidor
# El visor.html tiene un botón que llama a este endpoint.
# Nota: abre Outlook en la máquina donde corre Flask, no en la
# del usuario. Solo útil si Flask corre en la misma PC del usuario.
# ═══════════════════════════════════════════════════════════

@bp.route("/abrir-outlook", methods=["POST"])
@login_required
def abrir_outlook():
    import subprocess
    try:
        subprocess.Popen(["cmd", "/c", "start", "outlook"], shell=False)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500