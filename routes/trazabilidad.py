from flask import Blueprint, render_template, request, jsonify, session, make_response
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime

trazabilidad_bp = Blueprint('trazabilidad', __name__)

@trazabilidad_bp.route('/trazabilidad')
@menu_required('/trazabilidad')
def index():
    """Página principal de trazabilidad"""
    return render_template('trazabilidad/index.html')

@trazabilidad_bp.route('/trazabilidad/buscar')
@menu_required('/trazabilidad')
def buscar():
    """Busca lotes por filtros acumulativos"""
    lote = request.args.get('lote', '')
    cliente = request.args.get('cliente', '')
    producto = request.args.get('producto', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # 🔥 Agregar FechaPick a la lista de selección para poder ordenar
    query = """
        SELECT DISTINCT
            pl.NroOF AS Lote,
            pl.CodArt AS Producto,
            a.DesArt AS Descripcion,
            e.Cliente,
            pl.CantidadPickeada AS Cantidad,
            e.FechaCreacion AS FechaEmpaque,
            MONTH(e.FechaCreacion) as Mes,
            YEAR(e.FechaCreacion) as Anio,
            pl.FechaPick as FechaPick  -- 🔥 Agregado para ORDER BY
        FROM EmpWebPickingLotes pl
        INNER JOIN EmpWebEmpaques e ON pl.IdEmpaque = e.IdEmpaque
        INNER JOIN Artic a ON pl.CodArt = a.CodArt
        WHERE 1=1
    """
    params = []
    
    if lote:
        query += " AND pl.NroOF LIKE ?"
        params.append(f'%-{lote}%')
    
    if cliente:
        query += " AND e.Cliente LIKE ?"
        params.append(f'%{cliente}%')
    
    if producto:
        query += " AND (pl.CodArt LIKE ? OR a.DesArt LIKE ?)"
        params.append(f'%{producto}%')
        params.append(f'%{producto}%')
    
    if fecha_desde:
        query += " AND CAST(e.FechaCreacion AS DATE) >= ?"
        params.append(fecha_desde)
    
    if fecha_hasta:
        query += " AND CAST(e.FechaCreacion AS DATE) <= ?"
        params.append(fecha_hasta)
    
    query += " ORDER BY FechaPick DESC"  # 🔥 Ahora FechaPick está en la selección
    
    cursor.execute(query, params)
    
    rows = cursor.fetchall()
    resultados = []
    for row in rows:
        fecha = row[5]
        mes = fecha.month if fecha else ''
        anio = fecha.year if fecha else ''
        resultados.append({
            'lote': row[0],
            'producto': row[1],
            'descripcion': row[2],
            'cliente': row[3],
            'cantidad': float(row[4]) if row[4] else 0,
            'fecha_empaque': fecha.strftime('%d/%m/%Y') if fecha else '',
            'mes_entrega': f"{mes:02d}/{anio}" if mes and anio else ''
        })
    
    conn.close()
    return jsonify(resultados)

@trazabilidad_bp.route('/trazabilidad/clientes')
@menu_required('/trazabilidad')
def get_clientes():
    """Obtiene la lista de clientes disponibles después de filtrar por lote y producto"""
    lote = request.args.get('lote', '')
    producto = request.args.get('producto', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    query = """
        SELECT DISTINCT e.Cliente
        FROM EmpWebPickingLotes pl
        INNER JOIN EmpWebEmpaques e ON pl.IdEmpaque = e.IdEmpaque
        INNER JOIN Artic a ON pl.CodArt = a.CodArt
        WHERE 1=1
    """
    params = []
    
    if lote:
        query += " AND pl.NroOF LIKE ?"
        params.append(f'%-{lote}%')
    
    if producto:
        query += " AND (pl.CodArt LIKE ? OR a.DesArt LIKE ?)"
        params.append(f'%{producto}%')
        params.append(f'%{producto}%')
    
    if fecha_desde:
        query += " AND CAST(e.FechaCreacion AS DATE) >= ?"
        params.append(fecha_desde)
    
    if fecha_hasta:
        query += " AND CAST(e.FechaCreacion AS DATE) <= ?"
        params.append(fecha_hasta)
    
    query += " ORDER BY e.Cliente"
    
    cursor.execute(query, params)
    
    rows = cursor.fetchall()
    clientes = [row[0] for row in rows if row[0]]
    
    conn.close()
    return jsonify(clientes)

@trazabilidad_bp.route('/trazabilidad/pdf')
@menu_required('/trazabilidad')
def generar_pdf():
    """Genera PDF con los datos filtrados"""
    lote = request.args.get('lote', '')
    cliente = request.args.get('cliente', '')
    producto = request.args.get('producto', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    conn = get_db_connection()
    if not conn:
        return "Error de conexión", 500
    
    cursor = conn.cursor()
    
    # 🔥 Agregar FechaPick a la lista de selección
    query = """
        SELECT DISTINCT
            pl.NroOF AS Lote,
            pl.CodArt AS Producto,
            a.DesArt AS Descripcion,
            e.Cliente,
            pl.CantidadPickeada AS Cantidad,
            e.FechaCreacion AS FechaEmpaque,
            pl.FechaPick as FechaPick
        FROM EmpWebPickingLotes pl
        INNER JOIN EmpWebEmpaques e ON pl.IdEmpaque = e.IdEmpaque
        INNER JOIN Artic a ON pl.CodArt = a.CodArt
        WHERE 1=1
    """
    params = []
    
    if lote:
        query += " AND pl.NroOF LIKE ?"
        params.append(f'%-{lote}%')
    
    if cliente:
        query += " AND e.Cliente LIKE ?"
        params.append(f'%{cliente}%')
    
    if producto:
        query += " AND (pl.CodArt LIKE ? OR a.DesArt LIKE ?)"
        params.append(f'%{producto}%')
        params.append(f'%{producto}%')
    
    if fecha_desde:
        query += " AND CAST(e.FechaCreacion AS DATE) >= ?"
        params.append(fecha_desde)
    
    if fecha_hasta:
        query += " AND CAST(e.FechaCreacion AS DATE) <= ?"
        params.append(fecha_hasta)
    
    query += " ORDER BY FechaPick DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    fecha_actual = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Generar HTML para PDF
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Reporte de Trazabilidad</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; font-size: 12px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            .info {{ margin-bottom: 20px; background: #f8f9fa; padding: 10px; border-radius: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th {{ background: #2c3e50; color: white; padding: 10px; text-align: left; }}
            td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
            .footer {{ margin-top: 30px; font-size: 10px; color: #7f8c8d; text-align: center; }}
            .text-right {{ text-align: right; }}
        </style>
    </head>
    <body>
        <h1>Reporte de Trazabilidad</h1>
        <div class="info">
            <p><strong>Fecha de generación:</strong> {fecha_actual}</p>
            <p><strong>Filtro Lote:</strong> {lote if lote else 'Todos'}</p>
            <p><strong>Filtro Producto:</strong> {producto if producto else 'Todos'}</p>
            <p><strong>Filtro Cliente:</strong> {cliente if cliente else 'Todos'}</p>
            <p><strong>Filtro Fecha desde:</strong> {fecha_desde if fecha_desde else 'Todas'}</p>
            <p><strong>Filtro Fecha hasta:</strong> {fecha_hasta if fecha_hasta else 'Todas'}</p>
            <p><strong>Total de registros:</strong> {len(rows)}</p>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Lote</th>
                    <th>Producto</th>
                    <th>Descripción</th>
                    <th>Cliente</th>
                    <th class="text-right">Cantidad</th>
                    <th>Fecha Empaque</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for row in rows:
        html += f"""
            <tr>
                <td>{row[0]}</td>
                <td>{row[1]}</td>
                <td>{row[2]}</td>
                <td>{row[3]}</td>
                <td class="text-right">{float(row[4]) if row[4] else 0}</td>
                <td>{row[5].strftime('%d/%m/%Y') if row[5] else ''}</td>
            </tr>
        """
    
    html += """
            </tbody>
        </table>
        <div class="footer">
            <p>Sistema de Gestión de Empaques - Reporte de Trazabilidad</p>
        </div>
    </body>
    </html>
    """
    
    return html