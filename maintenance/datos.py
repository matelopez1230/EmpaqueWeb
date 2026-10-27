# datos.py
"""
Datos crudos del sistema como estructuras Python puras.
Sin archivos .sql, sin scripts externos.

Tablas lógicas:
    - PERMISOS       -> (id, descripcion)
    - PERSONAS       -> (id, nombre, apellido)
    - ASIGNACIONES   -> (id_persona, id_permiso, numero_validacion)
    - MENU           -> (id, etiqueta, ruta, id_padre, orden, id_permiso, activo)
"""

# ─────────────────────────────────────────────
# Constantes de permisos (para evitar "números mágicos" en el código)
# ─────────────────────────────────────────────
PERMISO_ADMIN            = 1
PERMISO_LECTURA          = 2
PERMISO_ESCRITURA        = 3
PERMISO_EDICION          = 4
PERMISO_ELIMINAR         = 5
PERMISO_REPORTES         = 6
PERMISO_USUARIOS         = 7
PERMISO_BACKUP           = 8
PERMISO_EXPORTAR         = 9
PERMISO_IMPORTAR         = 10
PERMISO_ESPECIFICACIONES = 11   # ← permiso especial

# ─────────────────────────────────────────────
# Catálogo de permisos
# ─────────────────────────────────────────────
PERMISOS: list[tuple[int, str]] = [
    (PERMISO_ADMIN,            "ADMIN"),
    (PERMISO_LECTURA,          "LECTURA"),
    (PERMISO_ESCRITURA,        "ESCRITURA"),
    (PERMISO_EDICION,          "EDICION"),
    (PERMISO_ELIMINAR,         "ELIMINAR"),
    (PERMISO_REPORTES,         "REPORTES"),
    (PERMISO_USUARIOS,         "USUARIOS"),
    (PERMISO_BACKUP,           "BACKUP"),
    (PERMISO_EXPORTAR,         "EXPORTAR"),
    (PERMISO_IMPORTAR,         "IMPORTAR"),
    (PERMISO_ESPECIFICACIONES, "Especificaciones"),
]

# ─────────────────────────────────────────────
# Personas
# ─────────────────────────────────────────────
PERSONAS: list[tuple[int, str, str]] = [
    (1,  "Ana",     "García"),
    (2,  "Luis",    "Martínez"),
    (3,  "María",   "López"),
    (4,  "Carlos",  "Rodríguez"),
    (5,  "Lucía",   "Fernández"),
    (6,  "Javier",  "Pérez"),
    (7,  "Elena",   "Sánchez"),
    (8,  "Diego",   "Ramírez"),
    (9,  "Sofía",   "Torres"),
    (10, "Andrés",  "Flores"),
    (11, "Valeria", "Gómez"),
    (12, "Miguel",  "Díaz"),
    (13, "Carmen",  "Vargas"),
    (14, "Pablo",   "Castro"),
    (15, "Isabel",  "Romero"),
    (16, "Raúl",    "Herrera"),
    (17, "Paula",   "Jiménez"),
    (18, "Hugo",    "Moreno"),
    (19, "Natalia", "Ortiz"),
    (20, "Sergio",  "Navarro"),
]

# ─────────────────────────────────────────────
# Asignaciones (persona ↔ permiso)
# ─────────────────────────────────────────────
ASIGNACIONES: list[tuple[int, int, int]] = [
    # ── Permisos "generales" ──
    (1,  PERMISO_ADMIN,       100),
    (1,  PERMISO_LECTURA,     100),
    (1,  PERMISO_ESCRITURA,   100),
    (1,  PERMISO_ELIMINAR,    100),
    (1,  PERMISO_REPORTES,    100),

    (2,  PERMISO_LECTURA,      80),
    (2,  PERMISO_REPORTES,     80),

    (3,  PERMISO_LECTURA,      75),
    (3,  PERMISO_ESCRITURA,    75),
    (3,  PERMISO_EDICION,      75),

    (4,  PERMISO_LECTURA,      60),

    (5,  PERMISO_LECTURA,      70),
    (5,  PERMISO_ESCRITURA,    70),
    (5,  PERMISO_EXPORTAR,     70),

    (6,  PERMISO_BACKUP,       90),
    (6,  PERMISO_IMPORTAR,     90),

    (7,  PERMISO_USUARIOS,     95),
    (7,  PERMISO_LECTURA,      95),

    (8,  PERMISO_LECTURA,      65),
    (8,  PERMISO_REPORTES,     65),
    (8,  PERMISO_EXPORTAR,     65),

    (9,  PERMISO_ESCRITURA,    50),

    (10, PERMISO_LECTURA,      55),
    (10, PERMISO_EDICION,      55),

    (11, PERMISO_ADMIN,        85),
    (11, PERMISO_LECTURA,      85),
    (11, PERMISO_REPORTES,     85),

    (12, PERMISO_LECTURA,      60),
    (12, PERMISO_EXPORTAR,     60),
    (12, PERMISO_IMPORTAR,     60),

    (13, PERMISO_REPORTES,     45),

    (14, PERMISO_LECTURA,      72),
    (14, PERMISO_ESCRITURA,    72),
    (14, PERMISO_ELIMINAR,     72),

    (15, PERMISO_BACKUP,       88),

    (16, PERMISO_LECTURA,      40),

    (17, PERMISO_EDICION,      77),
    (17, PERMISO_USUARIOS,     77),

    (18, PERMISO_LECTURA,      52),
    (18, PERMISO_REPORTES,     52),

    (19, PERMISO_EXPORTAR,     68),
    (19, PERMISO_IMPORTAR,     68),
    (19, PERMISO_BACKUP,       68),

    (20, PERMISO_LECTURA,      30),

    # ── Permiso especial: Especificaciones (11) ──
    (1,  PERMISO_ESPECIFICACIONES, 100),   # Ana      — admin total
    (3,  PERMISO_ESPECIFICACIONES,  75),   # María
    (5,  PERMISO_ESPECIFICACIONES,  70),   # Lucía
    (7,  PERMISO_ESPECIFICACIONES,  95),   # Elena    — gestión usuarios
    (11, PERMISO_ESPECIFICACIONES,  85),   # Valeria  — admin parcial
    (14, PERMISO_ESPECIFICACIONES,  72),   # Pablo
    (17, PERMISO_ESPECIFICACIONES,  40),   # Paula    — validación baja (test filtros)
    (19, PERMISO_ESPECIFICACIONES,  68),   # Natalia
]

# ─────────────────────────────────────────────
# Menú
# ─────────────────────────────────────────────
MENU: list[tuple[int, str, str, int | None, int, int, int]] = [
    # ── Raíz ──
    (1, "Inicio",         "/",         None, 1, PERMISO_LECTURA,   1),
    (2, "Administración", "/admin",    None, 2, PERMISO_ADMIN,     1),
    (3, "Datos",          "/datos",    None, 3, PERMISO_LECTURA,   1),
    (4, "Reportes",       "/reportes", None, 4, PERMISO_REPORTES,  1),
    (5, "Sistema",        "/sistema",  None, 5, PERMISO_BACKUP,    1),

    # ── Submenú Administración (padre=2) ──
    (10, "Usuarios", "/admin/usuarios", 2, 1, PERMISO_USUARIOS, 1),
    (11, "Permisos", "/admin/permisos", 2, 2, PERMISO_ADMIN,    1),
    (12, "Editar",   "/admin/editar",   2, 3, PERMISO_EDICION,  1),
    (13, "Eliminar", "/admin/eliminar", 2, 4, PERMISO_ELIMINAR, 1),

    # ── Submenú Datos (padre=3) ──
    (20, "Ver",              "/datos/ver",              3, 1, PERMISO_LECTURA,          1),
    (21, "Crear",            "/datos/crear",            3, 2, PERMISO_ESCRITURA,        1),
    (22, "Editar",           "/datos/editar",           3, 3, PERMISO_EDICION,          1),
    (23, "Exportar",         "/datos/exportar",         3, 4, PERMISO_EXPORTAR,         1),
    (24, "Importar",         "/datos/importar",         3, 5, PERMISO_IMPORTAR,         1),
    (25, "Especificaciones", "/datos/especificaciones", 3, 6, PERMISO_ESPECIFICACIONES, 1),  # ← nuevo

    # ── Submenú Sistema (padre=5) ──
    (30, "Backup", "/sistema/backup", 5, 1, PERMISO_BACKUP, 1),
]
# ─────────────────────────────────────────────
# Constantes de departamentos
# ─────────────────────────────────────────────
DEPTO_ID         = 1
DEPTO_MARKETING  = 2
DEPTO_INGENIERIA = 3
DEPTO_CALIDAD    = 4
DEPTO_OPERACIONES= 5
DEPTO_RRHH       = 6
DEPTO_FINANZAS   = 7

# ─────────────────────────────────────────────
# Catálogo de departamentos
# ─────────────────────────────────────────────
DEPARTAMENTOS: list[tuple[int, str]] = [
    (DEPTO_ID,          "I+D"),
    (DEPTO_MARKETING,   "MARKETING"),
    (DEPTO_INGENIERIA,  "INGENIERIA"),
    (DEPTO_CALIDAD,     "CALIDAD"),
    (DEPTO_OPERACIONES, "OPERACIONES"),
    (DEPTO_RRHH,        "RRHH"),
    (DEPTO_FINANZAS,    "FINANZAS"),
]

# ─────────────────────────────────────────────
# Personas ↔ Departamento  (id_persona, id_departamento)
# ─────────────────────────────────────────────
PERSONAS_DEPARTAMENTO: list[tuple[int, int]] = [
    (1,  DEPTO_ID),
    (2,  DEPTO_MARKETING),
    (3,  DEPTO_INGENIERIA),
    (4,  DEPTO_CALIDAD),
    (5,  DEPTO_ID),
    (6,  DEPTO_INGENIERIA),
    (7,  DEPTO_RRHH),
    (8,  DEPTO_MARKETING),
    (9,  DEPTO_CALIDAD),
    (10, DEPTO_INGENIERIA),
    (11, DEPTO_ID),
    (12, DEPTO_OPERACIONES),
    (13, DEPTO_MARKETING),
    (14, DEPTO_CALIDAD),
    (15, DEPTO_FINANZAS),
    (16, DEPTO_OPERACIONES),
    (17, DEPTO_RRHH),
    (18, DEPTO_INGENIERIA),
    (19, DEPTO_ID),
    (20, DEPTO_MARKETING),
]

# ─────────────────────────────────────────────
# Especificaciones (el "contenido" real del menú especial)
# (id, id_departamento, titulo, contenido, activo)
# ─────────────────────────────────────────────
ESPECIFICACIONES: list[tuple[int, int, str, str, int]] = [
    # I+D
    (1,  DEPTO_ID,         "Prototipo X1",          "Ficha técnica del prototipo X1 v2.3",       1),
    (2,  DEPTO_ID,         "Investigación IA",      "Roadmap interno de modelos LLM",            1),

    # MARKETING
    (3,  DEPTO_MARKETING,  "Campaña Q4",            "Plan de medios y presupuesto Q4",           1),
    (4,  DEPTO_MARKETING,  "Estudio de mercado",    "Segmentación 2026, informe preliminar",     1),

    # INGENIERIA
    (5,  DEPTO_INGENIERIA, "Plano estructura",      "Plano E-204 rev. B",                        1),
    (6,  DEPTO_INGENIERIA, "Norma ISO 9001",        "Checklist de cumplimiento interno",         1),

    # CALIDAD
    (7,  DEPTO_CALIDAD,    "Auditoría interna",     "Programa de auditorías ciclo 2026-1",       1),
    (8,  DEPTO_CALIDAD,    "Checklist producción",  "Puntos de control línea A y B",             1),

    # OPERACIONES
    (9,  DEPTO_OPERACIONES,"Logística",             "Optimización de rutas zona sur",            1),
    (10, DEPTO_OPERACIONES,"Mantenimiento",         "Cronograma preventivo trimestral",          1),

    # RRHH
    (11, DEPTO_RRHH,       "Onboarding",            "Guía de ingreso nuevos colaboradores",      1),
    (12, DEPTO_RRHH,       "Evaluación desempeño",  "Formulario y criterios 2026",               1),

    # FINANZAS
    (13, DEPTO_FINANZAS,   "Presupuesto anual",     "Consolidado por área y trimestre",          1),
]