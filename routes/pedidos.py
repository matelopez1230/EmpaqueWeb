from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
import pyodbc

pedidos_bp = Blueprint('pedidos', __name__)

@pedidos_bp.route('/pedidos-pendientes')
@menu_required('/pedidos-pendientes')
def pedidos_pendientes():
    # Obtener parámetros de búsqueda y orden
    q = request.args.get('q', '')
    order_col = request.args.get('order_col', 'Entrega')  # columna por defecto
    order_dir = request.args.get('order_dir', 'asc')       # dirección por defecto

    # Validar que la columna de orden sea una de las permitidas (para evitar inyección SQL)
    columnas_permitidas = ['Entrega', 'NroCbt', 'Cliente', 'CodArt', 'CodDesArticulo', 'CantPendiente', 'StockDisponible', 'EstadoStock']
    if order_col not in columnas_permitidas:
        order_col = 'Entrega'
    if order_dir not in ['asc', 'desc']:
        order_dir = 'asc'

    conn = get_db_connection()
    if not conn:
        return "Error de conexión", 500

    cursor = conn.cursor()
    
    # Construir consulta con filtro múltiple (cliente, pedido, artículo, descripción)
    query = "SELECT * FROM EmpWebPedidosConStock WHERE 1=1"
    params = []
    
    if q:
        query += """ AND (Cliente LIKE ? OR NroCbt LIKE ? OR CodArt LIKE ? OR CodDesArticulo LIKE ?)"""
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'])
    
    # Agregar ordenamiento dinámico
    query += f" ORDER BY {order_col} {order_dir}"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Obtener nombres de columnas
    columns = [column[0] for column in cursor.description]
    
    pedidos = []
    for row in rows:
        pedido = dict(zip(columns, row))
        pedidos.append(pedido)

        print("=== PEDIDOS CON PICKEO O EMPAQUE ===")
    for ped in pedidos:
        if ped.get('EstaPickeado') == 1 or ped.get('EstaEnEmpaque') == 1:
            print(f"NroCbt: {ped['NroCbt']}, CodArt: {ped['CodArt']}, EstaPickeado: {ped['EstaPickeado']}, EstaEnEmpaque: {ped['EstaEnEmpaque']}, StockDisponible: {ped['StockDisponible']}")
    
    conn.close()
    
    return render_template('pedidos_pendientes.html', 
                           pedidos=pedidos, 
                           q=q,
                           order_col=order_col,
                           order_dir=order_dir)


@pedidos_bp.route('/toggle-reserva', methods=['POST'])
@menu_required('/pedidos-pendientes')
def toggle_reserva():
    data = request.get_json() or request.form
    pedido = data.get('pedido')
    articulo = data.get('articulo')
    cantidad = float(data.get('cantidad', 0))
    marcar = data.get('marcar') in ('true', True, '1')
    user_id = session.get('user_id')
    
    if not all([pedido, articulo, user_id]):
        return jsonify({'success': False, 'error': 'Faltan datos'})
    
    if cantidad <= 0:
        return jsonify({'success': False, 'error': 'Cantidad inválida'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        if marcar:
            # ============================================================
            # RESERVAR
            # ============================================================
            
            # 1. Verificar si ya existe reserva
            cursor.execute("""
                SELECT COUNT(*) FROM EmpWebReservasPendientes 
                WHERE NroCbt = ? AND CodArt = ? AND Estado = 'RESERVADO'
            """, (pedido, articulo))
            
            if cursor.fetchone()[0] > 0:
                return jsonify({'success': False, 'error': 'Ya existe una reserva para este pedido/artículo'})
            
            # 2. Verificar si ya está en empaque
            cursor.execute("""
                SELECT COUNT(*) 
                FROM EmpWebEmpaqueDetalle ed
                INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
                WHERE ed.NroCbt = ? AND ed.CodArt = ?
                AND e.Estado != 'CONTROL_COMPLETADO'  -- 🔥 Excluir empaques remitidos
            """, (pedido, articulo))
            
            if cursor.fetchone()[0] > 0:
                return jsonify({
                    'success': False, 
                    'error': 'No se puede reservar porque el producto ya está en un empaque'
                })
            
            # 3. Verificar si ya está pickeado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM EmpWebPickingLotes pl
                INNER JOIN EmpWebEmpaqueDetalle ed ON pl.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
                INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
                WHERE ed.NroCbt = ? AND ed.CodArt = ?
                AND e.Estado != 'CONTROL_COMPLETADO'
            """, (pedido, articulo))
            
            if cursor.fetchone()[0] > 0:
                return jsonify({
                    'success': False, 
                    'error': 'No se puede reservar porque el producto ya está pickeado'
                })
            
            # 🔥 4. Obtener stock disponible REAL desde la nueva vista
            cursor.execute("""
                SELECT 
                    CantidadPendiente,
                    StockDisponibleReal
                FROM EmpWebStockDisponibleReal
                WHERE NroCbt = ? AND CodArt = ?
            """, (pedido, articulo))
            
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'error': 'Pedido no encontrado'})
            
            can_ped_pen = float(row[0]) if row[0] else 0
            stock_disponible = float(row[1]) if row[1] else 0
            
            # 5. Validar stock disponible
            if stock_disponible <= 0:
                return jsonify({
                    'success': False, 
                    'error': f'Stock insuficiente. Disponible: {stock_disponible}'
                })
            
            # 🔥 6. Validar que la cantidad a reservar no supere el stock disponible
            if cantidad > stock_disponible:
                return jsonify({
                    'success': False, 
                    'error': f'La cantidad ({cantidad}) supera el stock disponible ({stock_disponible})'
                })
            
            # 7. Calcular cantidad a reservar (respetando pendiente y stock)
            cantidad_a_reservar = min(cantidad, can_ped_pen, stock_disponible)
            
            if cantidad_a_reservar <= 0:
                return jsonify({'success': False, 'error': 'No hay cantidad disponible para reservar'})
            
            # 8. Insertar reserva
            cursor.execute("""
                INSERT INTO EmpWebReservasPendientes (Empresa, NroCbt, CodArt, CantidadReservada, UsuarioReserva, Estado)
                VALUES ('', ?, ?, ?, ?, 'RESERVADO')
            """, (pedido, articulo, cantidad_a_reservar, user_id))
            
            conn.commit()
            return jsonify({
                'success': True, 
                'mensaje': f'Reserva creada. Cantidad: {cantidad_a_reservar}'
            })
            
        else:
            # ============================================================
            # DESRESERVAR
            # ============================================================
            
            # 1. Verificar que NO esté en empaque ACTIVO (excluir CONTROL_COMPLETADO)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM EmpWebEmpaqueDetalle ed
                INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
                WHERE ed.NroCbt = ? AND ed.CodArt = ?
                AND e.Estado != 'CONTROL_COMPLETADO'
            """, (pedido, articulo))

            if cursor.fetchone()[0] > 0:
                return jsonify({
                    'success': False, 
                    'error': 'No se puede desreservar porque el producto ya está en un empaque activo'
                })

            # 2. Verificar que NO esté pickeado ACTIVO (excluir CONTROL_COMPLETADO)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM EmpWebPickingLotes pl
                INNER JOIN EmpWebEmpaqueDetalle ed ON pl.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
                INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
                WHERE ed.NroCbt = ? AND ed.CodArt = ?
                AND e.Estado != 'CONTROL_COMPLETADO'
            """, (pedido, articulo))

            if cursor.fetchone()[0] > 0:
                return jsonify({
                    'success': False, 
                    'error': 'No se puede desreservar porque el producto ya está pickeado'
                })
            
            # 3. Eliminar la reserva
            cursor.execute("""
                DELETE FROM EmpWebReservasPendientes 
                WHERE NroCbt = ? AND CodArt = ? AND Estado = 'RESERVADO'
            """, (pedido, articulo))
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'error': 'No se encontró la reserva'})
            
            conn.commit()
            return jsonify({'success': True, 'mensaje': 'Reserva eliminada exitosamente'})
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()
