from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime

desempacar_bp = Blueprint('desempacar', __name__)

@desempacar_bp.route('/desempacar')
@menu_required('/desempacar')
def index():
    """Página principal de desempacar"""
    return render_template('desempacar/index.html')

@desempacar_bp.route('/desempacar/empaques-disponibles')
@menu_required('/desempacar')
def empaques_disponibles():
    """Obtiene empaques que tienen productos disponibles para desempacar"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT
            e.IdEmpaque,
            e.NumeroEmpaque,
            e.Cliente,
            e.DireccionEnvio
        FROM EmpWebEmpaques e
        INNER JOIN EmpWebEmpaqueDetalle ed ON e.IdEmpaque = ed.IdEmpaque
        WHERE e.Estado = 'EN_PROCESO'
        AND e.ControlCompletado = 0  -- NO remitido
        AND ed.CantidadPickeada = 0   -- NO pickeado
        AND ed.CantidadRequerida > 0
        ORDER BY e.NumeroEmpaque
    """)
    
    rows = cursor.fetchall()
    empaques = []
    for row in rows:
        empaques.append({
            'id': row[0],
            'numero': row[1],
            'cliente': row[2],
            'direccion': row[3]
        })
    
    conn.close()
    return jsonify(empaques)

@desempacar_bp.route('/desempacar/productos-empaque/<int:id_empaque>')
@menu_required('/desempacar')
def productos_empaque(id_empaque):
    """Obtiene los productos de un empaque que se pueden desempacar"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            ed.IdEmpaqueDetalle,
            ed.CodArt,
            a.DesArt AS Descripcion,
            ed.CantidadRequerida,
            ed.CantidadPickeada,
            ed.CantidadRequerida - ed.CantidadPickeada AS CantidadPendiente
        FROM EmpWebEmpaqueDetalle ed
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        WHERE ed.IdEmpaque = ?
        AND ed.CantidadPickeada = 0  -- NO pickeado
        AND ed.CantidadRequerida > 0
        ORDER BY ed.CodArt
    """, (id_empaque,))
    
    rows = cursor.fetchall()
    productos = []
    for row in rows:
        productos.append({
            'id_detalle': row[0],
            'codart': row[1],
            'descripcion': row[2],
            'cantidad_requerida': float(row[3]) if row[3] else 0,
            'cantidad_pickeada': float(row[4]) if row[4] else 0,
            'cantidad_pendiente': float(row[5]) if row[5] else 0
        })
    
    conn.close()
    return jsonify(productos)

@desempacar_bp.route('/desempacar/desempacar', methods=['POST'])
@menu_required('/desempacar')
def desempacar():
    """Elimina un producto del empaque"""
    data = request.get_json()
    id_empaque_detalle = data.get('id_empaque_detalle')
    id_empaque = data.get('id_empaque')
    motivo = data.get('motivo', '')
    user_id = session.get('user_id')
    
    if not id_empaque_detalle or not id_empaque:
        return jsonify({'success': False, 'error': 'Faltan datos'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Verificar que el producto existe y no ha sido pickeado
        cursor.execute("""
            SELECT ed.CodArt, ed.CantidadPickeada, ed.CantidadRequerida,
                   e.Estado, e.ControlCompletado
            FROM EmpWebEmpaqueDetalle ed
            INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
            WHERE ed.IdEmpaqueDetalle = ?
        """, (id_empaque_detalle,))
        
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Producto no encontrado'})
        
        codart = row[0]
        cantidad_pickeada = float(row[1]) if row[1] else 0
        cantidad_requerida = float(row[2]) if row[2] else 0
        estado_empaque = row[3]
        control_completado = row[4]
        
        # Validar que no se pueda desempacar
        if cantidad_pickeada > 0:
            return jsonify({'success': False, 'error': 'No se puede desempacar porque el producto ya fue pickeado'})
        
        if estado_empaque != 'EN_PROCESO':
            return jsonify({'success': False, 'error': f'El empaque está en estado {estado_empaque}. No se puede desempacar'})
        
        if control_completado == 1:
            return jsonify({'success': False, 'error': 'El empaque ya fue remitido. No se puede desempacar'})
        
        # Verificar si el producto tiene pallets asignados
        cursor.execute("""
            SELECT COUNT(*) FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebPalletEmpaque p ON pd.IdPallet = p.IdPallet
            WHERE pd.IdEmpaqueDetalle = ?
        """, (id_empaque_detalle,))
        
        if cursor.fetchone()[0] > 0:
            return jsonify({'success': False, 'error': 'El producto tiene pallets asignados. Desasignelo primero desde "Quitar Producto de Pallet"'})
        
        # Eliminar el producto del empaque
        cursor.execute("""
            DELETE FROM EmpWebEmpaqueDetalle
            WHERE IdEmpaqueDetalle = ?
        """, (id_empaque_detalle,))
        
        # Registrar en historial
        cursor.execute("""
            INSERT INTO EmpWebPickingLotesHistorial (IdPickingOriginal, Usuario, FechaAccion, Accion, Motivo)
            VALUES (NULL, ?, GETDATE(), 'DESEMPACAR', ?)
        """, (user_id, f'Producto {codart} eliminado del empaque. Motivo: {motivo}'))
        
        # Verificar si el empaque quedó vacío
        cursor.execute("""
            SELECT COUNT(*) FROM EmpWebEmpaqueDetalle
            WHERE IdEmpaque = ?
        """, (id_empaque,))
        
        if cursor.fetchone()[0] == 0:
            # Si el empaque quedó vacío, eliminarlo también
            cursor.execute("""
                DELETE FROM EmpWebEmpaques
                WHERE IdEmpaque = ?
            """, (id_empaque,))
            
            # También eliminar reservas asociadas
            cursor.execute("""
                DELETE FROM EmpWebReservasPendientes
                WHERE NroCbt IN (
                    SELECT NroCbt FROM EmpWebEmpaqueDetalle WHERE IdEmpaque = ?
                )
            """, (id_empaque,))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': f'Producto {codart} eliminado del empaque exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()