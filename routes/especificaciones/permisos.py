# routes/especificaciones/permisos.py
"""
Decoradores y helpers de permisos para el módulo Especificaciones.

- login_required: exige sesión iniciada (usa la sesión de EmpaqueWeb).
- usuario_tiene_permiso: chequeo opcional de acceso al módulo.
"""
from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """
    Exige que el usuario tenga sesión iniciada.

    Si no hay sesión, redirige a /login con un flash de advertencia.
    El redirect respeta el parámetro `next` para volver a la página
    original después de loguearse.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Debés iniciar sesión", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def usuario_tiene_permiso(id_usuario=None):
    """
    Devuelve True si el usuario tiene al menos un menú del grupo
    ESPECIFICACIONES en la sesión.

    Se usa como guard adicional cuando se quiere verificar
    acceso al módulo antes de ejecutar una acción puntual.
    """
    menus = session.get("menus", [])
    return any(m.get("grupo") == "ESPECIFICACIONES" for m in menus)