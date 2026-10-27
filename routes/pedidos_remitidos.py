from flask import Blueprint, render_template, request, jsonify, session, make_response
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime
import pdfkit
import os

pedidos_remitidos_bp = Blueprint('pedidos_remitidos', __name__)

@pedidos_remitidos_bp.route('/pedidos-remitidos')
@menu_required('/pedidos-remitidos')
def index():
    """Página principal de pedidos remitidos"""
    return render_template('pedidos_remitidos/index.html')

@pedidos_remitidos_bp.route('/pedidos-remitidos/buscar')
@menu_required('/pedidos-remitidos')
def buscar():
    """Busca pedidos remitidos por filtros"""
    empaque = request.args.get('empaque', '')
    pedido = request.args.get('pedido', '')
    cliente = request.args.get('cliente', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    query = """
        SELECT 
            NumeroEmpaque,
            Cliente,
            DireccionEnvio,
            CodArt,
            Descripcion,
            TotalPedido,
            TotalEntregado,
            FechaRemito,
            NROREMITO,
            PedidosRelacionados,
            lotes
        FROM EmpWebPedidosRemitidos
        WHERE 1=1
    """
    params = []
    
    if empaque:
        query += " AND NumeroEmpaque LIKE ?"
        params.append(f'%{empaque}%')
    
    if pedido:
        query += " AND PedidosRelacionados LIKE ?"
        params.append(f'%{pedido}%')
    
    if cliente:
        query += " AND Cliente LIKE ?"
        params.append(f'%{cliente}%')
    
    if fecha_desde:
        query += " AND CAST(FechaRemito AS DATE) >= ?"
        params.append(fecha_desde)
    
    if fecha_hasta:
        query += " AND CAST(FechaRemito AS DATE) <= ?"
        params.append(fecha_hasta)
    
    query += " ORDER BY NumeroEmpaque, CodArt"
    
    cursor.execute(query, params)
    
    rows = cursor.fetchall()
    resultados = []
    for row in rows:
        resultados.append({
            'numero_empaque': row[0],
            'cliente': row[1],
            'direccion': row[2],
            'cod_art': row[3],
            'descripcion': row[4],
            'total_pedido': float(row[5]) if row[5] else 0,
            'total_entregado': float(row[6]) if row[6] else 0,
            'fecha_remito': row[7].strftime('%d/%m/%Y') if row[7] else '',
            'nro_remito': row[8],
            'pedidos_relacionados': row[9],
            'pedidos_relacionados': row[10] or ''
        })
    
    conn.close()
    return jsonify(resultados)

@pedidos_remitidos_bp.route('/pedidos-remitidos/pdf')
@menu_required('/pedidos-remitidos')
def generar_pdf():
    """Genera HTML para impresión/PDF con los datos filtrados"""
    empaque = request.args.get('empaque', '')
    pedido = request.args.get('pedido', '')
    cliente = request.args.get('cliente', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    conn = get_db_connection()
    if not conn:
        return "Error de conexión", 500
    
    cursor = conn.cursor()
    
    query = """
        SELECT 
            NumeroEmpaque,
            Cliente,
            DireccionEnvio,
            CodArt,
            Descripcion,
            TotalPedido,
            TotalEntregado,
            FechaRemito,
            Lotes
        FROM EmpWebPedidosRemitidos
        WHERE 1=1
    """
    params = []
    
    if empaque:
        query += " AND NumeroEmpaque LIKE ?"
        params.append(f'%{empaque}%')
    
    if pedido:
        query += " AND PedidosRelacionados LIKE ?"
        params.append(f'%{pedido}%')
    
    if cliente:
        query += " AND Cliente LIKE ?"
        params.append(f'%{cliente}%')
    
    if fecha_desde:
        query += " AND CAST(FechaRemito AS DATE) >= ?"
        params.append(fecha_desde)
    
    if fecha_hasta:
        query += " AND CAST(FechaRemito AS DATE) <= ?"
        params.append(fecha_hasta)
    
    query += " ORDER BY NumeroEmpaque, CodArt"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    fecha_actual = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Generar HTML para impresión
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Pedidos Remitidos</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; font-size: 12px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            .info {{ margin-bottom: 20px; background: #f8f9fa; padding: 10px; border-radius: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th {{ background: #2c3e50; color: white; padding: 10px; text-align: left; }}
            td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
            .footer {{ margin-top: 30px; font-size: 10px; color: #7f8c8d; text-align: center; }}
            .text-right {{ text-align: right; }}
            @media print {{
                body {{ margin: 0; }}
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="no-print" style="text-align: right; margin-bottom: 10px;">
            <button onclick="window.print();" style="padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                <i class="fas fa-print"></i> Imprimir / Guardar PDF
            </button>
        </div>
        <h1>Reporte de Pedidos Remitidos</h1>
        <div class="info">
            <p><strong>Fecha de generación:</strong> {fecha_actual}</p>
            <p><strong>Filtro Empaque:</strong> {empaque if empaque else 'Todos'}</p>
            <p><strong>Filtro Pedido:</strong> {pedido if pedido else 'Todos'}</p>
            <p><strong>Filtro Cliente:</strong> {cliente if cliente else 'Todos'}</p>
            <p><strong>Filtro Fecha:</strong> {fecha_desde if fecha_desde else 'Todas'} - {fecha_hasta if fecha_hasta else 'Todas'}</p>
            <p><strong>Total de registros:</strong> {len(rows)}</p>
        </div>
        <table>
            <thead>
                <tr>
                    <th>N° Empaque</th>
                    <th>Cliente</th>
                    <th>Dirección</th>
                    <th>Código</th>
                    <th>Descripción</th>
                    <th class="text-right">Total Pedido</th>
                    <th class="text-right">Total Entregado</th>
                    <th>Fecha Remito</th>
                    <th>N° lote</th>
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
                <td>{row[4]}</td>
                <td class="text-right">{float(row[5]) if row[5] else 0}</td>
                <td class="text-right">{float(row[6]) if row[6] else 0}</td>
                <td>{row[7].strftime('%d/%m/%Y') if row[7] else '-'}</td>
                <td>{row[8] or '-'}</td>
            </tr>
        """
    
    html += """
            </tbody>
        </table>
        <div class="footer">
            <p>Sistema de Gestión de Empaques - Reporte de Pedidos Remitidos</p>
        </div>
    </body>
    </html>
    """
    
    return html