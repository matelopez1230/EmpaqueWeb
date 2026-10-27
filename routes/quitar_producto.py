from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime

quitar_producto_bp = Blueprint('quitar_producto', __name__)

@quitar_producto_bp.route('/quitar-producto-pallet')
@menu_required('/quitar-producto-pallet')
def index():
    """Página principal para quitar producto de pallet"""
    return render_template('quitar_producto/index.html')

@quitar_producto_bp.route('/quitar-producto-pallet/buscar')
@menu_required('/quitar-producto-pallet')
def buscar():
    """Busca productos asignados a pallets por empaque"""
    empaque = request.args.get('empaque', '')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            pd.IdPalletDetalle,
            e.NumeroEmpaque,
            p.NumeroPallet,
            ed.CodArt,
            a.DesArt AS Descripcion,
            pd.CantidadAsignada,
            ISNULL(ed.CantidadPickeada, 0) AS CantidadPickeada,
            ed.IdEmpaqueDetalle,
            p.IdPallet,
            u.NombreUsuario AS UsuarioAsignado
        FROM EmpWebPalletDetalle pd
        INNER JOIN EmpWebPalletEmpaque p ON pd.IdPallet = p.IdPallet
        INNER JOIN EmpWebEmpaques e ON p.IdEmpaque = e.IdEmpaque
        INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        LEFT JOIN EmpWebUsuarios u ON p.UsuarioAsignado = u.IdUsuario
        WHERE e.NumeroEmpaque LIKE ?
        ORDER BY e.NumeroEmpaque, p.NumeroPallet, ed.CodArt
    """, (f'%{empaque}%',))
    
    rows = cursor.fetchall()
    productos = []
    for row in rows:
        productos.append({
            'id_pallet_detalle': row[0],
            'numero_empaque': row[1],
            'numero_pallet': row[2],
            'codart': row[3],
            'descripcion': row[4],
            'cantidad_asignada': float(row[5]) if row[5] else 0,
            'cantidad_pickeada': float(row[6]) if row[6] else 0,
            'id_empaque_detalle': row[7],
            'id_pallet': row[8],
            'usuario_asignado': row[9] or 'No asignado'
        })
    
    conn.close()
    return jsonify(productos)

@quitar_producto_bp.route('/quitar-producto-pallet/eliminar', methods=['POST'])
@menu_required('/quitar-producto-pallet')
def eliminar():
    """Elimina un producto completo de un pallet (con deshacer pickeo automático)"""
    data = request.get_json()
    id_pallet_detalle = data.get('id_pallet_detalle')
    motivo = data.get('motivo', '')
    user_id = session.get('user_id')
    
    if not id_pallet_detalle:
        return jsonify({'success': False, 'error': 'ID de pallet no proporcionado'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Obtener información completa
        cursor.execute("""
            SELECT pd.IdPallet, pd.IdEmpaqueDetalle, pd.CantidadAsignada, 
                   ed.CodArt, ed.CantidadPickeada, ed.CantidadRequerida,
                   e.IdEmpaque, e.NumeroEmpaque, p.NumeroPallet
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebPalletEmpaque p ON pd.IdPallet = p.IdPallet
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            INNER JOIN EmpWebEmpaques e ON p.IdEmpaque = e.IdEmpaque
            WHERE pd.IdPalletDetalle = ?
        """, (id_pallet_detalle,))
        
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Producto no encontrado'})
        
        id_pallet = row[0]
        id_empaque_detalle = row[1]
        cantidad_asignada = float(row[2]) if row[2] else 0
        codart = row[3]
        cantidad_pickeada = float(row[4]) if row[4] else 0
        cantidad_requerida = float(row[5]) if row[5] else 0
        id_empaque = row[6]
        numero_empaque = row[7]
        numero_pallet = row[8]
        
        # ============================================================
        # 0. ELIMINAR CONTROLES DE PALLET ASOCIADOS (NUEVO)
        # ============================================================
        # Verificar si tiene controles de pallet
        cursor.execute("""
            SELECT COUNT(*) FROM EmpWebControlPalletDetalle cpd
            WHERE cpd.IdPalletDetalle = ?
        """, (id_pallet_detalle,))
        
        tiene_controles = cursor.fetchone()[0] > 0
        
        if tiene_controles:
            print(f"DEBUG - Eliminando controles para IdPalletDetalle: {id_pallet_detalle}")
            
            # 0a. Eliminar los detalles de control asociados a este pallet
            cursor.execute("""
                DELETE FROM EmpWebControlPalletDetalle
                WHERE IdPalletDetalle = ?
            """, (id_pallet_detalle,))
            
            # 0b. Limpiar cabeceras de control que quedaron vacías
            cursor.execute("""
                DELETE FROM EmpWebControlPallet
                WHERE IdControl NOT IN (
                    SELECT DISTINCT IdControl FROM EmpWebControlPalletDetalle
                )
            """)
        
        # 1. Si tiene pickeos, deshacerlos primero
        if cantidad_pickeada > 0:
            cursor.execute("""
                SELECT IdPicking, CantidadPickeada, NroOF
                FROM EmpWebPickingLotes
                WHERE IdEmpaqueDetalle = ?
                ORDER BY FechaPick DESC
            """, (id_empaque_detalle,))
            
            picks = cursor.fetchall()
            for pick in picks:
                id_picking = pick[0]
                cantidad_pick = float(pick[1]) if pick[1] else 0
                nro_of = pick[2]
                
                # Registrar en historial
                cursor.execute("""
                    INSERT INTO EmpWebPickingLotesHistorial (IdPickingOriginal, Usuario, FechaAccion, Accion, Motivo)
                    VALUES (?, ?, GETDATE(), 'ELIMINADO_POR_QUITAR_PALLET', ?)
                """, (id_picking, user_id, motivo))
                
                # Eliminar pickeo
                cursor.execute("DELETE FROM EmpWebPickingLotes WHERE IdPicking = ?", (id_picking,))
        
        # 2. Eliminar el registro del pallet
        cursor.execute("DELETE FROM EmpWebPalletDetalle WHERE IdPalletDetalle = ?", (id_pallet_detalle,))
        
        # 3. Actualizar la cantidad pickeada en el detalle del empaque
        # Restar la cantidad asignada de la cantidad pickeada (si había pickeo)
        nueva_cantidad_pickeada = max(0, cantidad_pickeada - cantidad_asignada)
        nuevo_estado = 'PENDIENTE' if nueva_cantidad_pickeada == 0 else 'PARCIAL'
        
        cursor.execute("""
            UPDATE EmpWebEmpaqueDetalle 
            SET CantidadPickeada = ?,
                Estado = ?
            WHERE IdEmpaqueDetalle = ?
        """, (nueva_cantidad_pickeada, nuevo_estado, id_empaque_detalle))
        
        # 4. Verificar si el pallet quedó vacío
        cursor.execute("SELECT COUNT(*) FROM EmpWebPalletDetalle WHERE IdPallet = ?", (id_pallet,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("DELETE FROM EmpWebPalletEmpaque WHERE IdPallet = ?", (id_pallet,))
        
        # 5. Actualizar estado del empaque
        cursor.execute("""
            UPDATE EmpWebEmpaques 
            SET Estado = 'EN_PROCESO',
                ControlCompletado = 0
            WHERE IdEmpaque = ?
        """, (id_empaque,))
        
        conn.commit()
        
        # Construir mensaje con información de lo eliminado
        mensaje_adicional = ""
        if tiene_controles:
            mensaje_adicional = " Controles de pallet eliminados."
        if cantidad_pickeada > 0:
            mensaje_adicional += f" Se deshicieron {cantidad_pickeada} unidades pickeadas."
        
        return jsonify({
            'success': True, 
            'mensaje': f'Producto {codart} eliminado del pallet {numero_pallet} del empaque {numero_empaque}.{mensaje_adicional}'
        })
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@quitar_producto_bp.route('/quitar-producto-pallet/reducir', methods=['POST'])
@menu_required('/quitar-producto-pallet')
def reducir():
    """Reduce la cantidad de un producto en un pallet"""
    data = request.get_json()
    id_pallet_detalle = data.get('id_pallet_detalle')
    cantidad_a_quitar = float(data.get('cantidad', 0))
    motivo = data.get('motivo', '')
    user_id = session.get('user_id')
    
    if not id_pallet_detalle:
        return jsonify({'success': False, 'error': 'ID de pallet no proporcionado'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Obtener información
        cursor.execute("""
            SELECT pd.IdPallet, pd.IdEmpaqueDetalle, pd.CantidadAsignada, 
                   ed.CodArt, ed.CantidadPickeada, e.NumeroEmpaque, p.NumeroPallet
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebPalletEmpaque p ON pd.IdPallet = p.IdPallet
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            INNER JOIN EmpWebEmpaques e ON p.IdEmpaque = e.IdEmpaque
            WHERE pd.IdPalletDetalle = ?
        """, (id_pallet_detalle,))
        
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Producto no encontrado'})
        
        id_pallet = row[0]
        id_empaque_detalle = row[1]
        cantidad_asignada = float(row[2]) if row[2] else 0
        codart = row[3]
        cantidad_pickeada = float(row[4]) if row[4] else 0
        numero_empaque = row[5]
        numero_pallet = row[6]
        
        if cantidad_a_quitar <= 0:
            return jsonify({'success': False, 'error': 'Cantidad inválida'})
        
        if cantidad_a_quitar > cantidad_asignada:
            return jsonify({'success': False, 'error': f'No se puede quitar más de lo asignado ({cantidad_asignada})'})
        
        if cantidad_a_quitar > cantidad_asignada - cantidad_pickeada:
            return jsonify({'success': False, 'error': f'No se puede quitar porque ya se pickearon {cantidad_pickeada} unidades. Primero debe deshacer el pickeo.'})
        
        nueva_cantidad = cantidad_asignada - cantidad_a_quitar
        
        if nueva_cantidad > 0:
            # Solo actualizar la cantidad
            cursor.execute("""
                UPDATE EmpWebPalletDetalle
                SET CantidadAsignada = ?
                WHERE IdPalletDetalle = ?
            """, (nueva_cantidad, id_pallet_detalle))
        else:
            # ============================================================
            # Si llega a 0, eliminar controles primero (NUEVO)
            # ============================================================
            cursor.execute("""
                DELETE FROM EmpWebControlPalletDetalle
                WHERE IdPalletDetalle = ?
            """, (id_pallet_detalle,))
            
            cursor.execute("""
                DELETE FROM EmpWebControlPallet
                WHERE IdControl NOT IN (
                    SELECT DISTINCT IdControl FROM EmpWebControlPalletDetalle
                )
            """)
            
            # Eliminar el registro del pallet
            cursor.execute("DELETE FROM EmpWebPalletDetalle WHERE IdPalletDetalle = ?", (id_pallet_detalle,))
            
            # Verificar si el pallet quedó vacío
            cursor.execute("SELECT COUNT(*) FROM EmpWebPalletDetalle WHERE IdPallet = ?", (id_pallet,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("DELETE FROM EmpWebPalletEmpaque WHERE IdPallet = ?", (id_pallet,))
            
            # Actualizar estado del empaque
            cursor.execute("""
                UPDATE EmpWebEmpaques 
                SET Estado = 'EN_PROCESO',
                    ControlCompletado = 0
                WHERE IdEmpaque = (
                    SELECT IdEmpaque FROM EmpWebPalletEmpaque WHERE IdPallet = ?
                )
            """, (id_pallet,))
        
        # Registrar en historial
        cursor.execute("""
            INSERT INTO EmpWebPickingLotesHistorial (IdPickingOriginal, Usuario, FechaAccion, Accion, Motivo)
            VALUES (NULL, ?, GETDATE(), 'REDUCIR_CANTIDAD_PALLET', ?)
        """, (user_id, f'Producto {codart} - Cantidad reducida: {cantidad_a_quitar} del pallet {numero_pallet}. Motivo: {motivo}'))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'mensaje': f'Cantidad reducida de {codart} en pallet {numero_pallet} de {cantidad_asignada} a {nueva_cantidad}'
        })
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()