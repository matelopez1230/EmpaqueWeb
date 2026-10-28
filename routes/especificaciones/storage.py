# routes/especificaciones/storage.py
"""
Capa de acceso a datos del módulo Especificaciones.

Adaptado a SQL Server + tablas EspWeb*.
Todas las funciones devuelven dicts con claves en snake_case
(como hacía SQLite) para no romper templates existentes.
Las fechas se normalizan a string ISO "YYYY-MM-DD HH:MM:SS".

IMPORTANTE: todos los INSERT que necesitan devolver el ID usan
`OUTPUT INSERTED.IdXxx` (NO `SCOPE_IDENTITY()`, que falla con pyodbc).
"""
import json
import re
from datetime import datetime, date as _date

from db import get_db_connection


TIPOS_ABREV = {
    "diseno_grafico":   "DG",
    "material_empaque": "ME",
    "etiqueta":         "E",
    "etiqueta_zebra":   "ES",
}


# ═══════════════════════════════════════════════════════════
# Helpers internos
# ═══════════════════════════════════════════════════════════

def _pascal_to_snake(name):
    """CodigoBase -> codigo_base | DatosJson -> datos_json"""
    s1 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return s1.lower()


def _normalizar_valor(v):
    """
    Convierte datetime/date a string ISO (SQLite devolvía strings,
    SQL Server devuelve datetime). Así los templates que hacen
    `[:10]` o `[:19]` siguen funcionando sin cambios.
    """
    if isinstance(v, (datetime, _date)):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v


def _row_to_dict(cursor, row):
    if row is None:
        return None
    return {
        _pascal_to_snake(c[0]): _normalizar_valor(v)
        for c, v in zip(cursor.description, row)
    }


def _rows_to_dicts(cursor):
    return [_row_to_dict(cursor, r) for r in cursor.fetchall()]


def _nombre_completo_sql(alias="u"):
    """
    Expresión SQL que devuelve 'Nombre Apellido' (con fallback a NombreUsuario
    si los campos no están cargados). Así los templates que esperan
    `usuario_nombre` siguen funcionando.
    """
    return (
        f"COALESCE(NULLIF(TRIM(ISNULL({alias}.Nombre,'') + ' ' "
        f"+ ISNULL({alias}.Apellido,'')), ''), {alias}.NombreUsuario)"
    )


def codigo_completo(codigo_base, variante):
    return f"{(codigo_base or '').strip().upper()}{(variante or '').strip().upper()}"


def _fmt_fecha_ddmmyyyy(fecha):
    if not fecha:
        return ""
    fecha = fecha.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", fecha)
    if m:
        y, mo, d = m.groups()
        return f"{int(d):02d}-{int(mo):02d}-{y}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", fecha)
    if m:
        d, mo, y = m.groups()
        return f"{int(d):02d}-{int(mo):02d}-{y}"
    return fecha


def nombre_pdf_visible(tipo, codigo_base, variante, fecha_revision):
    abrev = TIPOS_ABREV.get(tipo, (tipo or "").upper()[:3])
    cod   = codigo_completo(codigo_base, variante)
    fecha = _fmt_fecha_ddmmyyyy(fecha_revision) or "SIN-FECHA"
    return f"ET-{abrev}-{cod} (Rev {fecha}).pdf"


# ═══════════════════════════════════════════════════════════
# REVISIÓN
# ═══════════════════════════════════════════════════════════

def siguiente_revision(codigo_base, variante, tipo):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(revision) FROM (
            SELECT Revision AS revision FROM EspWebEspecificaciones
              WHERE CodigoBase = ? AND Variante = ? AND Tipo = ?
            UNION ALL
            SELECT Revision FROM EspWebBorradores
              WHERE CodigoBase = ? AND Variante = ? AND Tipo = ?
        ) t
    """, (cb, va, tipo, cb, va, tipo))
    row = cur.fetchone()
    conn.close()
    max_rev = row[0] if row and row[0] is not None else -1
    return max_rev + 1


# ═══════════════════════════════════════════════════════════
# PUBLICADOS (EspWebEspecificaciones)
# ═══════════════════════════════════════════════════════════

def guardar_publicado(*, id_usuario, usuario_nombre, tipo, codigo_base, variante,
                     revision, titulo, cliente, producto, nombre_descarga, datos):
    """usuario_nombre se ignora — se obtiene por JOIN en las lecturas."""
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    cc = codigo_completo(cb, va)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO EspWebEspecificaciones
            (IdUsuario, Tipo, CodigoBase, Variante, Revision,
             CodigoCompleto, Titulo, Cliente, Producto, NombreDescarga,
             DatosJson, FechaGeneracion)
        OUTPUT INSERTED.IdEspecificacion
        VALUES (?,?,?,?,?,?,?,?,?,?,?, GETDATE())
    """, (id_usuario, tipo, cb, va, revision, cc,
          titulo, cliente, producto, nombre_descarga,
          json.dumps(datos, ensure_ascii=False)))
    _row = cur.fetchone()
    new_id = int(_row[0]) if _row and _row[0] is not None else None
    conn.commit()
    conn.close()
    return new_id


def obtener(id_esp):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT e.IdEspecificacion AS id, e.IdUsuario, e.Tipo,
               e.CodigoBase, e.Variante, e.Revision, e.CodigoCompleto,
               e.Titulo, e.Cliente, e.Producto, e.NombreDescarga,
               e.DatosJson, e.FechaGeneracion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebEspecificaciones e
        JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
        WHERE e.IdEspecificacion = ?
    """, (id_esp,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    conn.close()
    return result


def obtener_datos(id_esp):
    esp = obtener(id_esp)
    if not esp:
        return {}
    try:
        return json.loads(esp.get("datos_json") or "{}")
    except Exception:
        return {}


def existe_publicado(codigo_base, variante, revision, tipo):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT TOP 1 1 FROM EspWebEspecificaciones
        WHERE CodigoBase = ? AND Variante = ? AND Revision = ? AND Tipo = ?
    """, (cb, va, revision, tipo))
    row = cur.fetchone()
    conn.close()
    return row is not None


def versiones_de_familia(codigo_base, tipo=None):
    cb = codigo_base.strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    base_sql = f"""
        SELECT e.IdEspecificacion AS id, e.IdUsuario, e.Tipo,
               e.CodigoBase, e.Variante, e.Revision, e.CodigoCompleto,
               e.Titulo, e.Cliente, e.Producto, e.NombreDescarga,
               e.DatosJson, e.FechaGeneracion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebEspecificaciones e
        JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
        WHERE e.CodigoBase = ?
    """
    if tipo:
        cur.execute(base_sql + " AND e.Tipo = ? ORDER BY e.Variante ASC, e.Revision DESC",
                    (cb, tipo))
    else:
        cur.execute(base_sql + " ORDER BY e.Tipo, e.Variante ASC, e.Revision DESC",
                    (cb,))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def _marcar_ultimas(resultados):
    if not resultados:
        return resultados
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT CodigoBase, Variante, Tipo, MAX(Revision) AS max_rev
        FROM EspWebEspecificaciones
        GROUP BY CodigoBase, Variante, Tipo
    """)
    ultimas = {(r[0], r[1], r[2]): r[3] for r in cur.fetchall()}
    conn.close()
    for r in resultados:
        key = (r["codigo_base"], r["variante"], r["tipo"])
        r["es_ultima"] = (r["revision"] == ultimas.get(key))
    return resultados


def ultimas_publicadas(limite=20):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT e.IdEspecificacion AS id, e.IdUsuario, e.Tipo,
               e.CodigoBase, e.Variante, e.Revision, e.CodigoCompleto,
               e.Titulo, e.Cliente, e.Producto, e.NombreDescarga,
               e.DatosJson, e.FechaGeneracion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebEspecificaciones e
        JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
        ORDER BY e.IdEspecificacion DESC
        OFFSET 0 ROWS FETCH NEXT {int(limite)} ROWS ONLY
    """)
    rows = _rows_to_dicts(cur)
    conn.close()
    return _marcar_ultimas(rows)


def buscar_publicadas(tipo=None, q="", limite=100):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = f"""
        SELECT e.IdEspecificacion AS id, e.IdUsuario, e.Tipo,
               e.CodigoBase, e.Variante, e.Revision, e.CodigoCompleto,
               e.Titulo, e.Cliente, e.Producto, e.NombreDescarga,
               e.DatosJson, e.FechaGeneracion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebEspecificaciones e
        JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
        WHERE 1=1
    """
    params = []
    if tipo:
        sql += " AND e.Tipo = ?"
        params.append(tipo)
    if q:
        sql += """ AND (e.CodigoBase LIKE ? OR e.CodigoCompleto LIKE ?
                       OR e.Cliente LIKE ? OR e.Producto LIKE ? OR e.Titulo LIKE ?)"""
        like = f"%{q}%"
        params.extend([like] * 5)
    sql += f" ORDER BY e.IdEspecificacion DESC OFFSET 0 ROWS FETCH NEXT {int(limite)} ROWS ONLY"
    cur.execute(sql, params)
    rows = _rows_to_dicts(cur)
    conn.close()
    return _marcar_ultimas(rows)


def versiones_con_anexo(codigo_base, tipo):
    if not codigo_base:
        return []
    versiones = versiones_de_familia(codigo_base, tipo=tipo)
    resultado = []
    for v in versiones:
        try:
            datos = json.loads(v.get("datos_json") or "{}")
        except Exception:
            datos = {}
        fecha = datos.get("fecha_revision", "") or "0000-00-00"
        try:
            rev_num = int(v.get("revision") or 0)
        except Exception:
            rev_num = 0
        resultado.append({
            "id":              v["id"],
            "codigo_completo": v["codigo_completo"],
            "variante":        v["variante"],
            "revision":        f"{v['revision']:02d}",
            "revision_num":    rev_num,
            "fecha_revision":  fecha,
            "anexo":           datos.get("anexo_detalle_cambios", "") or "—",
        })
    resultado.sort(key=lambda x: (x["revision_num"], x["fecha_revision"]))
    return resultado


def eliminar_publicado(id_esp):
    esp = obtener(id_esp)
    if not esp:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM EspWebEspecificaciones WHERE IdEspecificacion = ?", (id_esp,))
    conn.commit()
    conn.close()
    return esp


def bump_drafts_after_publish(codigo_base, variante, tipo, revision):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT IdBorrador, Revision FROM EspWebBorradores
        WHERE CodigoBase = ? AND Variante = ? AND Tipo = ?
    """, (cb, va, tipo))
    row = cur.fetchone()
    if not row:
        conn.close(); return
    draft_id, draft_rev = row[0], row[1]

    if draft_rev < revision:
        conn.close(); return

    nueva = draft_rev + 1
    while True:
        cur.execute("""
            SELECT 1 FROM EspWebEspecificaciones
              WHERE CodigoBase=? AND Variante=? AND Tipo=? AND Revision=?
            UNION ALL
            SELECT 1 FROM EspWebBorradores
              WHERE CodigoBase=? AND Variante=? AND Tipo=? AND Revision=? AND IdBorrador!=?
        """, (cb, va, tipo, nueva, cb, va, tipo, nueva, draft_id))
        if cur.fetchone() is None:
            break
        nueva += 1

    cur.execute("""
        UPDATE EspWebBorradores SET Revision = ?, FechaActualizacion = GETDATE()
        WHERE IdBorrador = ?
    """, (nueva, draft_id))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
# BORRADORES (EspWebBorradores)
# ═══════════════════════════════════════════════════════════

def contar_borradores(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM EspWebBorradores WHERE IdUsuario = ?", (id_usuario,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def obtener_borrador(id_b):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT b.IdBorrador AS id, b.IdUsuario, b.Tipo,
               b.CodigoBase, b.Variante, b.Revision, b.CodigoCompleto,
               b.Titulo, b.Cliente, b.Producto, b.DatosJson,
               b.FechaCreacion, b.FechaActualizacion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebBorradores b
        JOIN EmpWebUsuarios u ON u.IdUsuario = b.IdUsuario
        WHERE b.IdBorrador = ?
    """, (id_b,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    conn.close()
    return result


def obtener_borrador_de_familia(codigo_base, variante, tipo):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT TOP 1 b.IdBorrador AS id, b.IdUsuario, b.Tipo,
               b.CodigoBase, b.Variante, b.Revision, b.CodigoCompleto,
               b.Titulo, b.Cliente, b.Producto, b.DatosJson,
               b.FechaCreacion, b.FechaActualizacion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebBorradores b
        JOIN EmpWebUsuarios u ON u.IdUsuario = b.IdUsuario
        WHERE b.CodigoBase = ? AND b.Variante = ? AND b.Tipo = ?
    """, (cb, va, tipo))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    conn.close()
    return result


def listar_borradores_usuario(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT b.IdBorrador AS id, b.IdUsuario, b.Tipo,
               b.CodigoBase, b.Variante, b.Revision, b.CodigoCompleto,
               b.Titulo, b.Cliente, b.Producto, b.DatosJson,
               b.FechaCreacion, b.FechaActualizacion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebBorradores b
        JOIN EmpWebUsuarios u ON u.IdUsuario = b.IdUsuario
        WHERE b.IdUsuario = ?
        ORDER BY b.FechaActualizacion DESC
    """, (id_usuario,))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def listar_borradores_usuario_por_tipo(id_usuario, tipo):
    """Borradores del usuario filtrados por tipo."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT b.IdBorrador AS id, b.IdUsuario, b.Tipo,
               b.CodigoBase, b.Variante, b.Revision, b.CodigoCompleto,
               b.Titulo, b.Cliente, b.Producto, b.DatosJson,
               b.FechaCreacion, b.FechaActualizacion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebBorradores b
        JOIN EmpWebUsuarios u ON u.IdUsuario = b.IdUsuario
        WHERE b.IdUsuario = ? AND b.Tipo = ?
        ORDER BY b.FechaActualizacion DESC
    """, (id_usuario, tipo))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def crear_borrador(*, id_usuario, usuario_nombre, tipo, codigo_base, variante,
                  revision, titulo, cliente, producto, datos):
    """usuario_nombre se ignora — JOIN en lecturas."""
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    cc = codigo_completo(cb, va)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO EspWebBorradores
            (IdUsuario, Tipo, CodigoBase, Variante, Revision, CodigoCompleto,
             Titulo, Cliente, Producto, DatosJson,
             FechaCreacion, FechaActualizacion)
        OUTPUT INSERTED.IdBorrador
        VALUES (?,?,?,?,?,?,?,?,?,?, GETDATE(), GETDATE())
    """, (id_usuario, tipo, cb, va, revision, cc,
          titulo, cliente, producto, json.dumps(datos, ensure_ascii=False)))
    _row = cur.fetchone()
    new_id = int(_row[0]) if _row and _row[0] is not None else None
    conn.commit()
    conn.close()
    return new_id


def actualizar_borrador(id_b, *, titulo, cliente, producto, datos):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE EspWebBorradores
           SET Titulo = ?, Cliente = ?, Producto = ?, DatosJson = ?,
               FechaActualizacion = GETDATE()
         WHERE IdBorrador = ?
    """, (titulo, cliente, producto,
          json.dumps(datos, ensure_ascii=False), id_b))
    conn.commit()
    conn.close()


def eliminar_borrador(id_b):
    b = obtener_borrador(id_b)
    if not b:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM EspWebBorradores WHERE IdBorrador = ?", (id_b,))
    conn.commit()
    conn.close()
    return b


def publicar_borrador(id_b, nombre_descarga=None):
    """Transfiere datos del borrador a especificaciones y borra el borrador."""
    b = obtener_borrador(id_b)
    if not b:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO EspWebEspecificaciones
            (IdUsuario, Tipo, CodigoBase, Variante, Revision, CodigoCompleto,
             Titulo, Cliente, Producto, NombreDescarga, DatosJson, FechaGeneracion)
        OUTPUT INSERTED.IdEspecificacion
        VALUES (?,?,?,?,?,?,?,?,?,?,?, GETDATE())
    """, (b["id_usuario"], b["tipo"],
          b["codigo_base"], b["variante"], b["revision"], b["codigo_completo"],
          b["titulo"], b["cliente"], b["producto"], nombre_descarga,
          b["datos_json"]))
    _row = cur.fetchone()
    new_id = int(_row[0]) if _row and _row[0] is not None else None

    cur.execute("DELETE FROM EspWebBorradores WHERE IdBorrador = ?", (id_b,))
    conn.commit()
    conn.close()
    return new_id


# ═══════════════════════════════════════════════════════════
# FILTROS POR TIPO
# ═══════════════════════════════════════════════════════════

def ultimas_publicadas_por_tipo(tipo, limite=20):
    """Últimas publicadas filtradas por tipo."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT e.IdEspecificacion AS id, e.IdUsuario, e.Tipo,
               e.CodigoBase, e.Variante, e.Revision, e.CodigoCompleto,
               e.Titulo, e.Cliente, e.Producto, e.NombreDescarga,
               e.DatosJson, e.FechaGeneracion,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebEspecificaciones e
        JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
        WHERE e.Tipo = ?
        ORDER BY e.IdEspecificacion DESC
        OFFSET 0 ROWS FETCH NEXT {int(limite)} ROWS ONLY
    """, (tipo,))
    rows = _rows_to_dicts(cur)
    conn.close()
    return _marcar_ultimas(rows)


def borradores_compartidos_por_tipo(id_usuario, tipo, es_admin=False):
    """Borradores compartidos conmigo filtrados por tipo."""
    conn = get_db_connection()
    cur = conn.cursor()
    base_sql = f"""
        SELECT DISTINCT b.IdBorrador AS id, b.IdUsuario, b.Tipo,
               b.CodigoBase, b.Variante, b.Revision, b.CodigoCompleto,
               b.Titulo, b.Cliente, b.Producto, b.DatosJson,
               b.FechaCreacion, b.FechaActualizacion,
               {_nombre_completo_sql('u')} AS usuario_nombre,
               {_nombre_completo_sql('u')} AS dueno_nombre
        FROM EspWebBorradores b
        JOIN EmpWebUsuarios u ON u.IdUsuario = b.IdUsuario
        WHERE b.IdUsuario != ? AND b.Tipo = ?
    """
    if es_admin:
        cur.execute(base_sql + " ORDER BY b.FechaActualizacion DESC",
                    (id_usuario, tipo))
    else:
        cur.execute(base_sql + """
            AND (
                b.IdBorrador IN (SELECT IdBorrador FROM EspWebPermisos
                                 WHERE IdReceptor = ? AND IdBorrador IS NOT NULL)
                OR b.IdUsuario IN (SELECT IdOtorgante FROM EspWebPermisos
                                   WHERE IdReceptor = ? AND IdBorrador IS NULL)
            )
            ORDER BY b.FechaActualizacion DESC
        """, (id_usuario, tipo, id_usuario, id_usuario))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════
# PERMISOS (EspWebPermisos unificada)
# ═══════════════════════════════════════════════════════════

def usuarios_con_acceso_seccion(seccion="especificaciones"):
    """Usuarios que tienen al menos un menú del grupo ESPECIFICACIONES."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT u.IdUsuario AS id,
               {_nombre_completo_sql('u')} AS nombre
        FROM EmpWebUsuarios u
        JOIN EmpWebPermisosUsuario pu ON pu.IdUsuario = u.IdUsuario
        JOIN EmpWebMenus m ON m.IdMenu = pu.IdMenu
        WHERE u.Activo = 1 AND m.Grupo = 'ESPECIFICACIONES'
        ORDER BY {_nombre_completo_sql('u')}
    """)
    rows = [{"id": r[0], "nombre": r[1]} for r in cur.fetchall()]
    conn.close()
    return rows


def obtener_permisos_globales(id_dueno):
    """Permisos globales otorgados por el dueño (IdBorrador NULL)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT p.IdPermiso AS id, p.IdOtorgante AS id_dueno,
               p.IdReceptor AS id_usuario,
               p.PuedeEditar AS puede_editar,
               p.PuedePublicar AS puede_publicar,
               p.PuedeEliminar AS puede_eliminar,
               p.FechaOtorgado AS fecha_otorgado,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebPermisos p
        JOIN EmpWebUsuarios u ON u.IdUsuario = p.IdReceptor
        WHERE p.IdOtorgante = ? AND p.IdBorrador IS NULL
        ORDER BY {_nombre_completo_sql('u')}
    """, (id_dueno,))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def set_permisos_globales(id_dueno, permisos):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM EspWebPermisos
         WHERE IdOtorgante = ? AND IdBorrador IS NULL
    """, (id_dueno,))
    for p in permisos:
        cur.execute("""
            INSERT INTO EspWebPermisos
                (IdOtorgante, IdReceptor, IdBorrador,
                 PuedeEditar, PuedePublicar, PuedeEliminar)
            VALUES (?, ?, NULL, ?, ?, ?)
        """, (id_dueno, int(p["id_usuario"]),
              int(p.get("puede_editar", 1)),
              int(p.get("puede_publicar", 0)),
              int(p.get("puede_eliminar", 0))))
    conn.commit()
    conn.close()


def obtener_permisos_especificos(id_borrador):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT p.IdPermiso AS id, p.IdOtorgante AS id_dueno,
               p.IdReceptor AS id_usuario, p.IdBorrador AS id_borrador,
               p.PuedeEditar AS puede_editar,
               p.PuedePublicar AS puede_publicar,
               p.PuedeEliminar AS puede_eliminar,
               p.FechaOtorgado AS fecha_otorgado,
               {_nombre_completo_sql('u')} AS usuario_nombre
        FROM EspWebPermisos p
        JOIN EmpWebUsuarios u ON u.IdUsuario = p.IdReceptor
        WHERE p.IdBorrador = ?
        ORDER BY {_nombre_completo_sql('u')}
    """, (id_borrador,))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def set_permisos_especificos(id_borrador, permisos):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM EspWebPermisos WHERE IdBorrador = ?", (id_borrador,))
    b = obtener_borrador(id_borrador)
    if not b:
        conn.close(); return
    id_dueno = b["id_usuario"]
    for p in permisos:
        cur.execute("""
            INSERT INTO EspWebPermisos
                (IdOtorgante, IdReceptor, IdBorrador,
                 PuedeEditar, PuedePublicar, PuedeEliminar)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_dueno, int(p["id_usuario"]), id_borrador,
              int(p.get("puede_editar", 0)),
              int(p.get("puede_publicar", 0)),
              int(p.get("puede_eliminar", 0))))
    conn.commit()
    conn.close()


def calcular_permisos_borrador(id_borrador, id_usuario, es_admin=False):
    b = obtener_borrador(id_borrador)
    if not b:
        return None

    if b["id_usuario"] == id_usuario:
        return {"puede_ver": True, "puede_editar": True,
                "puede_publicar": True, "puede_eliminar": True, "es_dueno": True}

    if es_admin:
        return {"puede_ver": True, "puede_editar": True,
                "puede_publicar": True, "puede_eliminar": True, "es_dueno": False}

    conn = get_db_connection()
    cur = conn.cursor()

    # Override específico
    cur.execute("""
        SELECT PuedeEditar, PuedePublicar, PuedeEliminar
        FROM EspWebPermisos
        WHERE IdBorrador = ? AND IdReceptor = ?
    """, (id_borrador, id_usuario))
    esp = cur.fetchone()

    if esp:
        conn.close()
        return {"puede_ver": True,
                "puede_editar":    bool(esp[0]),
                "puede_publicar":  bool(esp[1]),
                "puede_eliminar":  bool(esp[2]),
                "es_dueno": False}

    # Permiso global
    cur.execute("""
        SELECT PuedeEditar, PuedePublicar, PuedeEliminar
        FROM EspWebPermisos
        WHERE IdOtorgante = ? AND IdReceptor = ? AND IdBorrador IS NULL
    """, (b["id_usuario"], id_usuario))
    glob = cur.fetchone()
    conn.close()

    if glob:
        return {"puede_ver": True,
                "puede_editar":    bool(glob[0]),
                "puede_publicar":  bool(glob[1]),
                "puede_eliminar":  bool(glob[2]),
                "es_dueno": False}

    return {"puede_ver": False, "puede_editar": False,
            "puede_publicar": False, "puede_eliminar": False, "es_dueno": False}


def borradores_compartidos_conmigo(id_usuario, es_admin=False):
    conn = get_db_connection()
    cur = conn.cursor()
    base_sql = f"""
        SELECT DISTINCT b.IdBorrador AS id, b.IdUsuario, b.Tipo,
               b.CodigoBase, b.Variante, b.Revision, b.CodigoCompleto,
               b.Titulo, b.Cliente, b.Producto, b.DatosJson,
               b.FechaCreacion, b.FechaActualizacion,
               {_nombre_completo_sql('u')} AS usuario_nombre,
               {_nombre_completo_sql('u')} AS dueno_nombre
        FROM EspWebBorradores b
        JOIN EmpWebUsuarios u ON u.IdUsuario = b.IdUsuario
        WHERE b.IdUsuario != ?
    """
    if es_admin:
        cur.execute(base_sql + " ORDER BY b.FechaActualizacion DESC",
                    (id_usuario,))
    else:
        cur.execute(base_sql + """
            AND (
                b.IdBorrador IN (SELECT IdBorrador FROM EspWebPermisos
                                 WHERE IdReceptor = ? AND IdBorrador IS NOT NULL)
                OR b.IdUsuario IN (SELECT IdOtorgante FROM EspWebPermisos
                                   WHERE IdReceptor = ? AND IdBorrador IS NULL)
            )
            ORDER BY b.FechaActualizacion DESC
        """, (id_usuario, id_usuario, id_usuario))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════
# NOTIFICACIONES (EspWebNotificaciones)
# ═══════════════════════════════════════════════════════════

def crear_notificacion(id_usuario, mensaje, url=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO EspWebNotificaciones (IdUsuario, Mensaje, Url)
        VALUES (?, ?, ?)
    """, (id_usuario, mensaje, url))
    conn.commit()
    conn.close()


def notificaciones_no_leidas(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT TOP 20 IdNotificacion AS id, IdUsuario, Mensaje, Url, Leida, Fecha
        FROM EspWebNotificaciones
         WHERE IdUsuario = ? AND Leida = 0
         ORDER BY Fecha DESC
    """, (id_usuario,))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def marcar_notificaciones_leidas(id_usuario, ids=None):
    conn = get_db_connection()
    cur = conn.cursor()
    if ids:
        placeholders = ",".join("?" * len(ids))
        cur.execute(f"""
            UPDATE EspWebNotificaciones SET Leida = 1
             WHERE IdUsuario = ? AND IdNotificacion IN ({placeholders})
        """, [id_usuario] + list(ids))
    else:
        cur.execute("UPDATE EspWebNotificaciones SET Leida = 1 WHERE IdUsuario = ?",
                    (id_usuario,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
# EDICIÓN ACTIVA (EspWebEdicionActiva)
# ═══════════════════════════════════════════════════════════

def marcar_edicion_activa(id_borrador, id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        MERGE EspWebEdicionActiva AS target
        USING (SELECT ? AS IdBorrador, ? AS IdUsuario) AS source
        ON target.IdBorrador = source.IdBorrador
           AND target.IdUsuario = source.IdUsuario
        WHEN MATCHED THEN
            UPDATE SET UltimaActividad = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (IdBorrador, IdUsuario, UltimaActividad)
            VALUES (source.IdBorrador, source.IdUsuario, GETDATE());
    """, (id_borrador, id_usuario))
    conn.commit()
    conn.close()


def quien_esta_editando(id_borrador, id_usuario_actual=None, minutos=5):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT e.IdUsuario, {_nombre_completo_sql('u')} AS nombre
          FROM EspWebEdicionActiva e
          JOIN EmpWebUsuarios u ON u.IdUsuario = e.IdUsuario
         WHERE e.IdBorrador = ?
           AND e.UltimaActividad >= DATEADD(MINUTE, -{int(minutos)}, GETDATE())
    """, (id_borrador,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    if id_usuario_actual and row[0] == id_usuario_actual:
        return None
    return row[1]


def limpiar_edicion_activa(id_borrador, id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM EspWebEdicionActiva
         WHERE IdBorrador = ? AND IdUsuario = ?
    """, (id_borrador, id_usuario))
    conn.commit()
    conn.close()


def borrador_cambio_desde(id_b, fecha_actualizacion_original):
    if not fecha_actualizacion_original:
        return False
    b = obtener_borrador(id_b)
    if not b:
        return True
    return str(b["fecha_actualizacion"]) != str(fecha_actualizacion_original)


# ═══════════════════════════════════════════════════════════
# USUARIOS
# ═══════════════════════════════════════════════════════════

def obtener_usuario(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT IdUsuario AS id,
               NombreUsuario AS nombre,
               Nombre, Apellido,
               {_nombre_completo_sql('EmpWebUsuarios')} AS nombre_completo,
               Email, Activo AS activo, FechaAlta AS fecha_alta
        FROM EmpWebUsuarios WHERE IdUsuario = ?
    """, (id_usuario,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    conn.close()
    return result


def actualizar_email_usuario(id_usuario, email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE EmpWebUsuarios SET Email = ? WHERE IdUsuario = ?",
                (email, id_usuario))
    conn.commit()
    conn.close()


def listar_usuarios_aprobadores():
    """
    Lista de usuarios activos para el select "Aprobó" de los formularios.
    Devuelve id + nombre_completo ordenados alfabéticamente.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT IdUsuario AS id,
               {_nombre_completo_sql('EmpWebUsuarios')} AS nombre_completo
        FROM EmpWebUsuarios
        WHERE Activo = 1
        ORDER BY {_nombre_completo_sql('EmpWebUsuarios')}
    """)
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════
# CONTACTOS (EspWebContactosCorreo)
# ═══════════════════════════════════════════════════════════

def listar_contactos(limite=500):
    """Lista todos los contactos ordenados por nombre/email."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT TOP {int(limite)}
               IdContacto AS id, Email, Nombre, TotalEnvios, FechaAlta, UltimoUso
        FROM EspWebContactosCorreo
        ORDER BY COALESCE(Nombre, Email), Email
    """)
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def obtener_contacto(id_contacto):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdContacto AS id, Email, Nombre, TotalEnvios, FechaAlta, UltimoUso
        FROM EspWebContactosCorreo
        WHERE IdContacto = ?
    """, (id_contacto,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    conn.close()
    return result


def obtener_contacto_por_email(email):
    email = (email or "").strip().lower()
    if not email:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdContacto AS id, Email, Nombre, TotalEnvios, FechaAlta, UltimoUso
        FROM EspWebContactosCorreo
        WHERE LOWER(Email) = ?
    """, (email,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    conn.close()
    return result


def crear_contacto(email, nombre):
    """
    Crea un contacto nuevo SIN incrementar TotalEnvios (uso manual desde UI).
    Devuelve el ID creado, o None si el email ya existe.
    """
    email = (email or "").strip().lower()
    if not email:
        return None
    if obtener_contacto_por_email(email):
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO EspWebContactosCorreo (Email, Nombre, TotalEnvios, FechaAlta)
        OUTPUT INSERTED.IdContacto
        VALUES (?, ?, 0, GETDATE())
    """, (email, (nombre or "").strip() or None))
    row = cur.fetchone()
    if not row or row[0] is None:
        conn.close()
        raise RuntimeError(
            "No se pudo obtener el ID del contacto. "
            "Verificá que IdContacto sea IDENTITY en la tabla."
        )
    new_id = int(row[0])
    conn.commit()
    conn.close()
    return new_id


def actualizar_contacto(id_contacto, email, nombre):
    """
    Actualiza email + nombre. Devuelve True si actualizó, False si el email
    ya está usado por OTRO contacto.
    """
    email = (email or "").strip().lower()
    if not email:
        return False

    existente = obtener_contacto_por_email(email)
    if existente and existente["id"] != id_contacto:
        return False

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE EspWebContactosCorreo
           SET Email = ?, Nombre = ?
         WHERE IdContacto = ?
    """, (email, (nombre or "").strip() or None, id_contacto))
    rows = cur.rowcount
    conn.commit()
    conn.close()
    return rows > 0


def eliminar_contacto(id_contacto):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM EspWebContactosCorreo WHERE IdContacto = ?", (id_contacto,))
    rows = cur.rowcount
    conn.commit()
    conn.close()
    return rows > 0


def buscar_contactos(q, limite=10):
    q = (q or "").strip()
    if not q:
        return []
    conn = get_db_connection()
    cur = conn.cursor()
    like = f"%{q}%"
    cur.execute(f"""
        SELECT TOP {int(limite)} IdContacto AS id, Email, Nombre, TotalEnvios, UltimoUso
          FROM EspWebContactosCorreo
         WHERE Email LIKE ? OR COALESCE(Nombre, '') LIKE ?
         ORDER BY TotalEnvios DESC, UltimoUso DESC
    """, (like, like))
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows


def registrar_contacto(email, nombre=None):
    """Llamada desde el worker de envíos — incrementa TotalEnvios."""
    email = (email or "").strip().lower()
    if not email:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        MERGE EspWebContactosCorreo AS target
        USING (SELECT ? AS Email, ? AS Nombre) AS source
        ON target.Email = source.Email
        WHEN MATCHED THEN
            UPDATE SET Nombre      = COALESCE(source.Nombre, target.Nombre),
                       TotalEnvios = target.TotalEnvios + 1,
                       UltimoUso   = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (Email, Nombre, TotalEnvios, FechaAlta, UltimoUso)
            VALUES (source.Email, source.Nombre, 1, GETDATE(), GETDATE());
    """, (email, nombre))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
# ENVÍOS (EspWebEnviosCorreo)
# ═══════════════════════════════════════════════════════════

def crear_envio(id_esp, id_usuario, destinatario, remitente, asunto, cuerpo=""):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO EspWebEnviosCorreo
            (IdEspecificacion, IdUsuario, Destinatario, Remitente, Asunto, Cuerpo, Estado)
        OUTPUT INSERTED.IdEnvio
        VALUES (?, ?, ?, ?, ?, ?, 'pendiente')
    """, (id_esp, id_usuario, destinatario, remitente, asunto, cuerpo))
    _row = cur.fetchone()
    new_id = int(_row[0]) if _row and _row[0] is not None else None
    conn.commit()
    conn.close()
    return new_id


def obtener_envio(id_envio):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdEnvio AS id, IdEspecificacion AS id_esp, IdUsuario, IdContacto,
               Destinatario, Remitente, Asunto, Cuerpo, Estado, Error,
               Intentos, FechaCreacion, FechaInicio, FechaEnvio
        FROM EspWebEnviosCorreo WHERE IdEnvio = ?
    """, (id_envio,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    conn.close()
    return result


def marcar_envio_enviando(id_envio):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE EspWebEnviosCorreo
           SET Estado = 'enviando',
               FechaInicio = GETDATE(),
               Intentos = Intentos + 1
         WHERE IdEnvio = ?
    """, (id_envio,))
    conn.commit()
    conn.close()


def marcar_envio_enviado(id_envio):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE EspWebEnviosCorreo
           SET Estado = 'enviado',
               FechaEnvio = GETDATE(),
               Error = NULL
         WHERE IdEnvio = ?
    """, (id_envio,))
    conn.commit()
    conn.close()


def marcar_envio_error(id_envio, error):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE EspWebEnviosCorreo SET Estado = 'error', Error = ?
         WHERE IdEnvio = ?
    """, (error, id_envio))
    conn.commit()
    conn.close()


def envios_pendientes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdEnvio AS id, IdEspecificacion AS id_esp, IdUsuario, IdContacto,
               Destinatario, Remitente, Asunto, Cuerpo, Estado, Error,
               Intentos, FechaCreacion, FechaInicio, FechaEnvio
        FROM EspWebEnviosCorreo
         WHERE Estado IN ('pendiente', 'enviando')
         ORDER BY IdEnvio ASC
    """)
    rows = _rows_to_dicts(cur)
    conn.close()
    return rows