from functools import wraps
from flask import session, abort, redirect, url_for

def login_required(f):
    """Decorador para rutas que requieren usuario logueado (sin verificar menú específico)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def menu_required(menu_url):
    """Decorador para rutas que requieren un menú específico"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            # Verificar si la URL está en los menús del usuario
            menus = session.get('menus', [])
            if not any(m['url'] == menu_url for m in menus):
                abort(403)  # Prohibido
            return f(*args, **kwargs)
        return decorated_function
    return decorator