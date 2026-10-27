from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
import pyodbc
from datetime import datetime

reportes_bp = Blueprint('reportes', __name__)

@reportes_bp.route('/reporte-empaque')
@menu_required('/reporte-empaque')
def index():
    """Página principal de reporte de empaque"""
    return render_template('reportes/reporte_empaque.html')

@reportes_bp.route('/reporte-empaque/dashboard')
@menu_required('/reporte-empaque')
def dashboard():
    """Obtiene los conteos para las tarjetas del dashboard"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Contar por estado (GrupoPickeo)
    cursor.execute("""
        SELECT GrupoPickeo, COUNT(*) as Cantidad
        FROM EmpWebReporteGral
        GROUP BY GrupoPickeo
    """)
    
    rows = cursor.fetchall()
    
    counts = {
        'NO PICKEADO': 0,
        'PICKEADO PARCIAL': 0,
        'PENDIENTE DE CONTROL': 0,
        'PENDIENTE DE REMITIR': 0,
        'REMITIDO PARCIAL': 0,
        'REMITIDO COMPLETO': 0
    }
    
    for row in rows:
        grupo = row[0]
        cantidad = row[1]
        if grupo in counts:
            counts[grupo] = cantidad
    
    conn.close()
    return jsonify(counts)

@reportes_bp.route('/reporte-empaque/pedidos-por-estado')
@menu_required('/reporte-empaque')
def pedidos_por_estado():
    """Obtiene los pedidos filtrados por estado"""
    estado = request.args.get('estado', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT NroPedido, Cliente, DireccionEnvio, NumeroEmpaque, GrupoPickeo
        FROM EmpWebReporteGral
        WHERE GrupoPickeo = ?
        ORDER BY NroPedido
    """, (estado,))
    
    rows = cursor.fetchall()
    pedidos = []
    for row in rows:
        pedidos.append({
            'NroPedido': row[0],
            'Cliente': row[1],
            'DireccionEnvio': row[2],
            'NumeroEmpaque': row[3],
            'GrupoPickeo': row[4]
        })
    
    conn.close()
    return jsonify(pedidos)

@reportes_bp.route('/reporte-empaque/detalle-pedido')
@menu_required('/reporte-empaque')
def detalle_pedido():
    """Obtiene el detalle de un pedido específico"""
    pedido = request.args.get('pedido', '')
    empaque = request.args.get('empaque', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Obtener datos del pedido
    cursor.execute("""
        SELECT TOP 1 Cliente, DireccionEnvio
        FROM EmpWebReporteDetalleEmpaque
        WHERE NroPedido = ?
    """, (pedido,))
    
    pedido_row = cursor.fetchone()
    cliente = pedido_row[0] if pedido_row else ''
    direccion = pedido_row[1] if pedido_row else ''
    
    # 🔥 Obtener información del empaque (pallets y peso total)
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT pe.IdPallet) AS TotalPallets,
            ISNULL(SUM(pd.CantidadAsignada * a.PesNetArt), 0) AS PesoTotal
        FROM EmpWebEmpaques e
        LEFT JOIN EmpWebPalletEmpaque pe ON e.IdEmpaque = pe.IdEmpaque
        LEFT JOIN EmpWebPalletDetalle pd ON pe.IdPallet = pd.IdPallet
        LEFT JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
        LEFT JOIN Artic a ON ed.CodArt = a.CodArt
        WHERE e.NumeroEmpaque = ?
    """, (empaque,))
    
    empaque_info = cursor.fetchone()
    total_pallets = empaque_info[0] if empaque_info and empaque_info[0] else 0
    peso_total = float(empaque_info[1]) if empaque_info and empaque_info[1] else 0
    
    # Obtener detalle de items
    cursor.execute("""
        SELECT 
            NumeroEmpaque,
            CodArticulo,
            Descripcion,
            CantidadRequerida,
            CantidadPickeada,
            EstadoPickeo,
            NROREMITO,
            CANT_ENTREGADA,
            Diferencia,
            REMFECHA
        FROM EmpWebReporteDetalleEmpaque
        WHERE NroPedido = ? AND NumeroEmpaque = ?
        ORDER BY CodArticulo
    """, (pedido, empaque))
    
    rows = cursor.fetchall()
    items = []
    for row in rows:
        items.append({
            'NumeroEmpaque': row[0],
            'CodArticulo': row[1],
            'Descripcion': row[2],
            'CantidadRequerida': float(row[3]) if row[3] else 0,
            'CantidadPickeada': float(row[4]) if row[4] else 0,
            'EstadoPickeo': row[5],
            'NROREMITO': row[6],
            'CANT_ENTREGADA': float(row[7]) if row[7] else 0,
            'Diferencia': float(row[8]) if row[8] else 0,
            'REMFECHA': row[9].strftime('%d/%m/%Y') if row[9] else ''
        })
    
    conn.close()
    return jsonify({
        'success': True,
        'cliente': cliente,
        'direccion': direccion,
        'empaque': empaque,
        'total_pallets': total_pallets,
        'peso_total': peso_total,
        'items': items
    })

@reportes_bp.route('/reporte-empaque/detalle-piqueos')
@menu_required('/reporte-empaque')
def detalle_piqueos():
    """Obtiene el detalle de piqueos con filtros"""
    # Obtener parámetros de filtro
    numero_empaque = request.args.get('numero_empaque', '')
    cliente = request.args.get('cliente', '')
    direccion = request.args.get('direccion', '')
    usuario_creacion = request.args.get('usuario_creacion', '')
    estado_empaque = request.args.get('estado_empaque', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    nro_pedido = request.args.get('nro_pedido', '')
    cod_articulo = request.args.get('cod_articulo', '')
    descripcion = request.args.get('descripcion', '')
    estado_pickeo = request.args.get('estado_pickeo', '')
    nro_remito = request.args.get('nro_remito', '')
    cant_pedido = request.args.get('cant_pedido', '')
    cant_entregada = request.args.get('cant_entregada', '')
    diferencia = request.args.get('diferencia', '')
    usuarios_pick = request.args.get('usuarios_pick', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Construir consulta con filtros dinámicos
    query = """
        SELECT 
            NumeroEmpaque,
            Cliente,
            DireccionEnvio,
            FechaCreacion,
            UsuarioCreacion,
            EstadoEmpaque,
            FechaCompletado,
            NroPedido,
            CodArticulo,
            Descripcion,
            CantidadRequerida,
            CantidadPickeada,
            EstadoPickeo,
            NROREMITO,
            CANT_ENTREGADA,
            REMFECHA,
            Diferencia,
            UsuariosPick,
            CANT_PEDIDO
        FROM EmpWebReporteDetalleEmpaque
        WHERE 1=1
    """
    params = []
    
    if numero_empaque:
        query += " AND NumeroEmpaque LIKE ?"
        params.append(f'%{numero_empaque}%')
    
    if cliente:
        query += " AND Cliente LIKE ?"
        params.append(f'%{cliente}%')
    
    if direccion:
        query += " AND DireccionEnvio LIKE ?"
        params.append(f'%{direccion}%')
    
    if usuario_creacion:
        query += " AND UsuarioCreacion LIKE ?"
        params.append(f'%{usuario_creacion}%')
    
    if estado_empaque:
        query += " AND EstadoEmpaque = ?"
        params.append(estado_empaque)
    
    if fecha_desde:
        query += " AND FechaCompletado >= ?"
        params.append(fecha_desde)
    
    if fecha_hasta:
        query += " AND FechaCompletado <= ?"
        params.append(fecha_hasta + ' 23:59:59')
    
    if nro_pedido:
        query += " AND NroPedido LIKE ?"
        params.append(f'%{nro_pedido}%')
    
    if cod_articulo:
        query += " AND CodArticulo LIKE ?"
        params.append(f'%{cod_articulo}%')
    
    if descripcion:
        query += " AND Descripcion LIKE ?"
        params.append(f'%{descripcion}%')
    
    if estado_pickeo:
        query += " AND EstadoPickeo = ?"
        params.append(estado_pickeo)
    
    if nro_remito:
        query += " AND NROREMITO LIKE ?"
        params.append(f'%{nro_remito}%')
    
    if cant_pedido:
        query += " AND CANT_PEDIDO = ?"
        params.append(cant_pedido)
    
    if cant_entregada:
        query += " AND CANT_ENTREGADA = ?"
        params.append(cant_entregada)
    
    if diferencia:
        query += " AND Diferencia = ?"
        params.append(diferencia)
    
    if usuarios_pick:
        query += " AND UsuariosPick LIKE ?"
        params.append(f'%{usuarios_pick}%')
    
    query += " ORDER BY FechaCreacion DESC, NumeroEmpaque, NroPedido"
    
    cursor.execute(query, params)
    
    rows = cursor.fetchall()
    resultados = []
    for row in rows:
        resultados.append({
            'NumeroEmpaque': row[0],
            'Cliente': row[1],
            'DireccionEnvio': row[2],
            'FechaCreacion': row[3].strftime('%d/%m/%Y %H:%M') if row[3] else '',
            'UsuarioCreacion': row[4],
            'EstadoEmpaque': row[5],
            'FechaCompletado': row[6].strftime('%d/%m/%Y %H:%M') if row[6] else '',
            'NroPedido': row[7],
            'CodArticulo': row[8],
            'Descripcion': row[9],
            'CantidadRequerida': float(row[10]) if row[10] else 0,
            'CantidadPickeada': float(row[11]) if row[11] else 0,
            'EstadoPickeo': row[12],
            'NROREMITO': row[13],
            'CANT_ENTREGADA': float(row[14]) if row[14] else 0,
            'REMFECHA': row[15].strftime('%d/%m/%Y') if row[15] else '',
            'Diferencia': float(row[16]) if row[16] else 0,
            'UsuariosPick': row[17],
            'CANT_PEDIDO': float(row[18]) if row[18] else 0
        })
    
    conn.close()
    return jsonify(resultados)