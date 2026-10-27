# main.py
"""
Demo: inicializa la DB, imprime personas, permisos,
y la tabla de quiénes tienen el permiso especial 'Especificaciones'.
"""
import db
import consultas
import datos


# ─────────────────────────────────────────────
# Utilidades de impresión
# ─────────────────────────────────────────────
def imprimir_tabla(filas: list[dict], columnas: list[tuple[str, str]]) -> None:
    """
    filas:    lista de dicts
    columnas: lista de (clave, título)
    """
    if not filas:
        print("  (sin resultados)")
        return

    anchos = []
    for clave, titulo in columnas:
        ancho = max(len(titulo), *(len(str(f[clave])) for f in filas))
        anchos.append(ancho)

    encabezado = " | ".join(t.ljust(a) for (_, t), a in zip(columnas, anchos))
    separador  = "-+-".join("-" * a for a in anchos)
    print("  " + encabezado)
    print("  " + separador)
    for f in filas:
        linea = " | ".join(
            str(f[clave]).ljust(a) for (clave, _), a in zip(columnas, anchos)
        )
        print("  " + linea)


def imprimir_menu(items: list[dict], nivel: int = 0) -> None:
    for it in items:
        print("  " * (nivel + 1) + f"• {it['etiqueta']}  ({it['ruta']})")
        imprimir_menu(it["hijos"], nivel + 1)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
if __name__ == "__main__":
    db.inicializar(reset=True)

    # ── 1) Personas ──
    print("\n══ Personas ══")
    imprimir_tabla(
        consultas.listar_personas(),
        columnas=[("id", "ID"), ("nombre", "Nombre"), ("apellido", "Apellido")],
    )

    # ── 2) Permisos ──
    print("\n══ Permisos ══")
    imprimir_tabla(
        consultas.listar_permisos(),
        columnas=[("id", "ID"), ("descripcion", "Descripción")],
    )

    # ── 3) Personas con permiso 'Especificaciones' ──
    print(f"\n══ Personas con permiso 'Especificaciones' "
          f"(id={datos.PERMISO_ESPECIFICACIONES}) ══")
    imprimir_tabla(
        consultas.personas_con_permiso(datos.PERMISO_ESPECIFICACIONES),
        columnas=[
            ("id", "ID"),
            ("nombre", "Nombre"),
            ("apellido", "Apellido"),
            ("permiso", "Permiso"),
            ("numero_validacion", "Validación"),
        ],
    )

    # ── 4) Mismo permiso, filtrando validación >= 70 ──
    print("\n══ Especificaciones con validación >= 70 ══")
    imprimir_tabla(
        consultas.personas_con_permiso(datos.PERMISO_ESPECIFICACIONES, min_validacion=70),
        columnas=[
            ("id", "ID"),
            ("nombre", "Nombre"),
            ("apellido", "Apellido"),
            ("numero_validacion", "Validación"),
        ],
    )

    # ── 5) Permisos de Ana ──
    print("\n══ Permisos de Ana (id=1) ══")
    imprimir_tabla(
        consultas.permisos_de_persona(1),
        columnas=[
            ("id", "ID"),
            ("descripcion", "Permiso"),
            ("numero_validacion", "Validación"),
        ],
    )

    # ── 6) Menú jerárquico de Ana (debe incluir Especificaciones) ──
    print("\n══ Menú de Ana (id=1) ══")
    imprimir_menu(consultas.menu_jerarquico(1))

    # ── 7) Menú de Sergio (NO debe incluir Especificaciones) ──
    print("\n══ Menú de Sergio (id=20) ══")
    imprimir_menu(consultas.menu_jerarquico(20))

    # ── 8) Menú de Paula con filtro de validación (pierde Especificaciones) ──
    print("\n══ Menú de Paula (id=17) con validación >= 50 ══")
    imprimir_menu(consultas.menu_jerarquico(17, min_validacion=50))

        # ── 9) Especificaciones de una persona (con permiso + depto) ──
    print("\n══ Especificaciones visibles para Ana (id=1, I+D) ══")
    imprimir_tabla(
        consultas.especificaciones_de_persona(1),
        columnas=[
            ("id", "ID"),
            ("departamento", "Depto"),
            ("titulo", "Título"),
            ("contenido", "Contenido"),
        ],
    )

    print("\n══ Especificaciones visibles para Pablo (id=14, CALIDAD) ══")
    imprimir_tabla(
        consultas.especificaciones_de_persona(14),
        columnas=[
            ("id", "ID"),
            ("departamento", "Depto"),
            ("titulo", "Título"),
            ("contenido", "Contenido"),
        ],
    )

    print("\n══ Especificaciones para Sergio (id=20, sin permiso 11) ══")
    imprimir_tabla(
        consultas.especificaciones_de_persona(20),
        columnas=[("id", "ID"), ("titulo", "Título")],
    )

    print("\n══ Especificaciones para Paula (id=17) con validación >= 50 ══")
    imprimir_tabla(
        consultas.especificaciones_de_persona(17, min_validacion=50),
        columnas=[("id", "ID"), ("titulo", "Título")],
    )

    # ── 10) Resumen general ──
    print("\n══ Personas con acceso a Especificaciones (por depto) ══")
    imprimir_tabla(
        consultas.personas_con_acceso_a_especificaciones(),
        columnas=[
            ("id", "ID"),
            ("nombre", "Nombre"),
            ("apellido", "Apellido"),
            ("departamento", "Departamento"),
            ("numero_validacion", "Validación"),
            ("total_especificaciones", "Especs"),
        ],
    )