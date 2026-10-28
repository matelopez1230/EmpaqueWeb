# routes/especificaciones/__init__.py
"""
Módulo Especificaciones — integrado en EmpaqueWeb.

Declara el Blueprint y registra las rutas de routes.py.
"""
from flask import Blueprint

especificaciones_bp = Blueprint(
    "especificaciones",
    __name__,
    url_prefix="/especificaciones",
)

# Importar las rutas para que se registren en el blueprint.
# Este import tiene que ir AL FINAL, después de crear especificaciones_bp,
# porque routes.py hace `from . import especificaciones_bp as bp`.
from . import routes   # noqa: E402,F401