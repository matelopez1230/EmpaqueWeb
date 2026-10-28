# routes/especificaciones.py
from flask import Blueprint, render_template, session, redirect, url_for, flash

especificaciones_bp = Blueprint(
    'especificaciones',
    __name__,
    url_prefix='/especificaciones'
)


@especificaciones_bp.before_request
def require_login():
    """Todas las rutas del módulo requieren login."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))


def _menus_modulo():
    """Menús de este módulo que el usuario tiene permiso de ver."""
    return [m for m in session.get('menus', []) if m.get('grupo') == 'ESPECIFICACIONES']


def _usuario_tiene_acceso_modulo():
    """True si el usuario tiene AL MENOS un menú del módulo."""
    return len(_menus_modulo()) > 0


@especificaciones_bp.route('/')
def index():
    if not _usuario_tiene_acceso_modulo():
        flash('No tenés acceso al módulo de Especificaciones')
        return redirect(url_for('index'))
    return render_template('especificaciones/index.html',
                           menus_modulo=_menus_modulo())


@especificaciones_bp.route('/borradores')
def borradores():
    if not _usuario_tiene_acceso_modulo():
        flash('No tenés acceso al módulo de Especificaciones')
        return redirect(url_for('index'))
    return render_template('especificaciones/borradores.html')


@especificaciones_bp.route('/generadas')
def generadas():
    if not _usuario_tiene_acceso_modulo():
        flash('No tenés acceso al módulo de Especificaciones')
        return redirect(url_for('index'))
    return render_template('especificaciones/generadas.html')


@especificaciones_bp.route('/envios')
def envios():
    if not _usuario_tiene_acceso_modulo():
        flash('No tenés acceso al módulo de Especificaciones')
        return redirect(url_for('index'))
    return render_template('especificaciones/envios.html')


@especificaciones_bp.route('/contactos')
def contactos():
    if not _usuario_tiene_acceso_modulo():
        flash('No tenés acceso al módulo de Especificaciones')
        return redirect(url_for('index'))
    return render_template('especificaciones/contactos.html')