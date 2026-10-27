# consultas.py
"""
Funciones de lectura sobre la base de datos.
Todas devuelven listas de dicts (más cómodas de consumir desde el resto del código).
"""
from typing import Any

import db
import datos  

# ─────────────────────────────────────────────
# Personas
# ─────────────────────────────────────────────
def listar_personas() -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nombre, apellido FROM personas ORDER BY apellido, nombre"
        ).fetchall()
    return [dict(r) for r in rows]


def buscar_persona(id_persona: int) -> dict | None:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id, nombre, apellido FROM personas WHERE id = ?",
            (id_persona,),
        ).fetchone()
    return dict(row) if row else None


# ─────────────────────────────────────────────
# Permisos
# ─────────────────────────────────────────────
def listar_permisos() -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, descripcion FROM permisos ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def permisos_de_persona(id_persona: int) -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT pe.id, pe.descripcion, pp.numero_validacion
            FROM personas_permisos pp
            JOIN permisos pe ON pe.id = pp.id_permiso
            WHERE pp.id_persona = ?
            ORDER BY pe.id
        """, (id_persona,)).fetchall()
    return [dict(r) for r in rows]


def personas_con_permiso(id_permiso: int, min_validacion: int = 0) -> list[dict]:
    """
    Devuelve las personas que tienen el permiso indicado,
    opcionalmente filtrando por un numero_validacion mínimo.
    """
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT p.id           AS id,
                   p.nombre       AS nombre,
                   p.apellido     AS apellido,
                   pe.descripcion AS permiso,
                   pp.numero_validacion AS numero_validacion
            FROM personas p
            JOIN personas_permisos pp ON pp.id_persona = p.id
            JOIN permisos pe          ON pe.id = pp.id_permiso
            WHERE pp.id_permiso = ?
              AND pp.numero_validacion >= ?
            ORDER BY pp.numero_validacion DESC, p.apellido, p.nombre
        """, (id_permiso, min_validacion)).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# Menú
# ─────────────────────────────────────────────
def menu_de_persona(id_persona: int, min_validacion: int = 0) -> list[dict]:
    """Ítems de menú planos (sin jerarquía) a los que la persona tiene acceso."""
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT m.id, m.etiqueta, m.ruta, m.id_padre, m.orden
            FROM menu m
            JOIN personas_permisos pp ON pp.id_permiso = m.id_permiso
            WHERE pp.id_persona = ?
              AND m.activo = 1
              AND pp.numero_validacion >= ?
            ORDER BY m.id_padre, m.orden
        """, (id_persona, min_validacion)).fetchall()
    return [dict(r) for r in rows]


def menu_jerarquico(id_persona: int, min_validacion: int = 0) -> list[dict[str, Any]]:
    """Mismo resultado que menu_de_persona, pero armado como árbol."""
    items = menu_de_persona(id_persona, min_validacion)
    por_id = {it["id"]: {**it, "hijos": []} for it in items}
    raiz: list[dict[str, Any]] = []

    for it in por_id.values():
        padre = it["id_padre"]
        if padre and padre in por_id:
            por_id[padre]["hijos"].append(it)
        else:
            raiz.append(it)
    return raiz

# ─────────────────────────────────────────────
# Departamentos
# ─────────────────────────────────────────────
def listar_departamentos() -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nombre FROM departamentos ORDER BY nombre"
        ).fetchall()
    return [dict(r) for r in rows]


def departamento_de_persona(id_persona: int) -> dict | None:
    with db.get_conn() as conn:
        row = conn.execute("""
            SELECT d.id, d.nombre
            FROM personas_departamento pd
            JOIN departamentos d ON d.id = pd.id_departamento
            WHERE pd.id_persona = ?
        """, (id_persona,)).fetchone()
    return dict(row) if row else None


# ─────────────────────────────────────────────
# Especificaciones (filtradas por permiso + departamento)
# ─────────────────────────────────────────────
def especificaciones_de_persona(
    id_persona: int,
    min_validacion: int = 0,
) -> list[dict]:
    """
    Devuelve las especificaciones visibles para una persona, dado que:
      - tiene el permiso ESPECIFICACIONES (con validación >= min_validacion)
      - pertenece al departamento dueño de la especificación
      - la especificación está activa
    Si no cumple el permiso, devuelve [].
    """
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT e.id,
                   e.titulo,
                   e.contenido,
                   d.nombre AS departamento
            FROM personas p
            JOIN personas_permisos    pp ON pp.id_persona = p.id
            JOIN personas_departamento pd ON pd.id_persona = p.id
            JOIN departamentos         d  ON d.id = pd.id_departamento
            JOIN especificaciones      e  ON e.id_departamento = d.id
            WHERE p.id = ?
              AND pp.id_permiso = ?
              AND pp.numero_validacion >= ?
              AND e.activo = 1
            ORDER BY e.id
        """, (id_persona, datos.PERMISO_ESPECIFICACIONES, min_validacion)).fetchall()
    return [dict(r) for r in rows]


def personas_con_acceso_a_especificaciones(min_validacion: int = 0) -> list[dict]:
    """
    Tabla-resumen: quién tiene el permiso, de qué departamento es,
    y cuántas especificaciones puede ver.
    """
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT p.id,
                   p.nombre,
                   p.apellido,
                   d.nombre AS departamento,
                   pp.numero_validacion,
                   COUNT(e.id) AS total_especificaciones
            FROM personas p
            JOIN personas_permisos     pp ON pp.id_persona = p.id
            JOIN personas_departamento pd ON pd.id_persona = p.id
            JOIN departamentos          d ON d.id = pd.id_departamento
            LEFT JOIN especificaciones  e
                   ON e.id_departamento = d.id AND e.activo = 1
            WHERE pp.id_permiso = ?
              AND pp.numero_validacion >= ?
            GROUP BY p.id, p.nombre, p.apellido, d.nombre, pp.numero_validacion
            ORDER BY pp.numero_validacion DESC, p.apellido
        """, (datos.PERMISO_ESPECIFICACIONES, min_validacion)).fetchall()
    return [dict(r) for r in rows]