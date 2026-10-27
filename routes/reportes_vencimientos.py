from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime

reportes_vencimientos_bp = Blueprint('reportes_vencimientos', __name__)

@reportes_vencimientos_bp.route('/reportes-vencimientos')
@menu_required('/reportes-vencimientos')
def index():
    """Página principal de reporte de vencimientos"""
    return render_template('reportes_vencimientos/index.html')

@reportes_vencimientos_bp.route('/reportes-vencimientos/datos')
@menu_required('/reportes-vencimientos')
def datos():
    """Obtiene los datos del reporte de vencimientos con filtros"""
    # Obtener parámetros de filtro
    nro_of = request.args.get('nro_of', '')
    codart = request.args.get('codart', '')
    desart = request.args.get('desart', '')
    dias_restantes = request.args.get('dias_restantes', '')
    grovenc = request.args.get('grovenc', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Construir consulta con filtros
    query = """
        SELECT 
            NroOF,
            codart,
            DesArt,
            fecof,
            diasvencim,
            FechVenc,
            StockTeorico,
            diasRestantes,
            grovenc
        FROM EmpWebReporteVencimientos
        WHERE 1=1
    """
    params = []
    
    if nro_of:
        query += " AND NroOF LIKE ?"
        params.append(f'%{nro_of}%')
    
    if codart:
        query += " AND codart LIKE ?"
        params.append(f'%{codart}%')
    
    if desart:
        query += " AND DesArt LIKE ?"
        params.append(f'%{desart}%')
    
    if dias_restantes:
        try:
            dias = int(dias_restantes)
            query += " AND diasRestantes <= ?"
            params.append(dias)
        except ValueError:
            pass
    
    if grovenc:
        query += " AND grovenc = ?"
        params.append(grovenc)
    
    query += " ORDER BY diasRestantes"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    resultados = []
    for row in rows:
        resultados.append({
            'NroOF': row[0],
            'codart': row[1],
            'DesArt': row[2],
            'fecof': row[3].strftime('%d/%m/%Y') if row[3] else '',
            'diasvencim': row[4],
            'FechVenc': row[5].strftime('%d/%m/%Y') if row[5] else '',
            'StockTeorico': float(row[6]) if row[6] else 0,
            'diasRestantes': row[7],
            'grovenc': row[8] or ''
        })
    
    conn.close()
    return jsonify(resultados)

@reportes_vencimientos_bp.route('/reportes-vencimientos/pdf')
@menu_required('/reportes-vencimientos')
def generar_pdf():
    """Genera HTML para PDF del reporte de vencimientos"""
    # Obtener parámetros de filtro (igual que datos)
    nro_of = request.args.get('nro_of', '')
    codart = request.args.get('codart', '')
    desart = request.args.get('desart', '')
    dias_restantes = request.args.get('dias_restantes', '')
    grovenc = request.args.get('grovenc', '')
    
    conn = get_db_connection()
    if not conn:
        return "Error de conexión", 500
    
    cursor = conn.cursor()
    
    query = """
        SELECT 
            NroOF,
            codart,
            DesArt,
            fecof,
            diasvencim,
            FechVenc,
            StockTeorico,
            diasRestantes,
            grovenc
        FROM EmpWebReporteVencimientos
        WHERE 1=1
    """
    params = []
    
    if nro_of:
        query += " AND NroOF LIKE ?"
        params.append(f'%{nro_of}%')
    
    if codart:
        query += " AND codart LIKE ?"
        params.append(f'%{codart}%')
    
    if desart:
        query += " AND DesArt LIKE ?"
        params.append(f'%{desart}%')
    
    if dias_restantes:
        try:
            dias = int(dias_restantes)
            query += " AND diasRestantes <= ?"
            params.append(dias)
        except ValueError:
            pass
    
    if grovenc:
        query += " AND grovenc = ?"
        params.append(grovenc)
    
    query += " ORDER BY diasRestantes"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    fecha_actual = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    # Construir HTML para PDF
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Reporte de Vencimientos</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; font-size: 11px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #e74c3c; padding-bottom: 10px; }}
            .info {{ margin-bottom: 20px; background: #f8f9fa; padding: 10px; border-radius: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th {{ background: #2c3e50; color: white; padding: 8px; text-align: left; }}
            td {{ padding: 6px; border-bottom: 1px solid #ddd; }}
            .text-right {{ text-align: right; }}
            .footer {{ margin-top: 30px; font-size: 10px; color: #7f8c8d; text-align: center; }}
            .vencido {{ background-color: #f8d7da; }}
            .por-vencer {{ background-color: #fff3cd; }}
            .normal {{ background-color: #d4edda; }}
    </style>
    </head>
    <body>
        <h1>Reporte de Vencimientos</h1>
        <div class="info">
            <p><strong>Fecha de generación:</strong> {fecha_actual}</p>
            <p><strong>Total de registros:</strong> {len(rows)}</p>
    """
    
    if nro_of:
        html += f"<p><strong>Filtro N° Lote:</strong> {nro_of}</p>"
    if codart:
        html += f"<p><strong>Filtro Artículo:</strong> {codart}</p>"
    if desart:
        html += f"<p><strong>Filtro Descripción:</strong> {desart}</p>"
    if dias_restantes:
        html += f"<p><strong>Filtro Días Restantes ≤:</strong> {dias_restantes}</p>"
    if grovenc:
        html += f"<p><strong>Filtro Grupo Vencimiento:</strong> {grovenc}</p>"
    
    html += """
        </div>
        <table>
            <thead>
                <tr>
                    <th>N° Lote</th>
                    <th>Artículo</th>
                    <th>Descripción</th>
                    <th>Fecha OF</th>
                    <th>Días Venc.</th>
                    <th>Fecha Venc.</th>
                    <th class="text-right">Stock</th>
                    <th class="text-right">Días Rest.</th>
                    <th>Grupo</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for row in rows:
        dias_rest = row[7] if row[7] is not None else 999
        clase = 'vencido' if dias_rest < 0 else ('por-vencer' if dias_rest <= 30 else 'normal')
        
        html += f"""
            <tr class="{clase}">
                <td>{row[0]}</td>
                <td>{row[1]}</td>
                <td>{row[2]}</td>
                <td>{row[3].strftime('%d/%m/%Y') if row[3] else ''}</td>
                <td>{row[4]}</td>
                <td>{row[5].strftime('%d/%m/%Y') if row[5] else ''}</td>
                <td class="text-right">{float(row[6]) if row[6] else 0}</td>
                <td class="text-right"><strong>{row[7]}</strong></td>
                <td>{row[8] or ''}</td>
            </tr>
        """
    
    html += """
            </tbody>
        </table>
        <div class="footer">
            <p>Sistema de Gestión de Empaques - Reporte de Vencimientos</p>
        </div>
    </body>
    </html>
    """
    
    return html