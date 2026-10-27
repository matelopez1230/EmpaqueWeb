from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
import pyodbc
from datetime import datetime

pickeo_bp = Blueprint('pickeo', __name__)

@pickeo_bp.route('/picking')
@menu_required('/picking')
def index():
    """Página principal del módulo de pickeo"""
    return render_template('pickeo/index.html')


@pickeo_bp.route('/picking/detalle-empaque/<int:id_empaque>')
@menu_required('/picking')
def detalle_empaque(id_empaque):
    """Obtiene el detalle de productos de un empaque, un registro por cada pallet (pickeo aislado por pallet)"""
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            pd.IdPalletDetalle,
            ed.IdEmpaqueDetalle,
            ed.CodArt,
            a.DesArt AS Descripcion,
            pd.CantidadAsignada AS CantidadRequerida,
            ISNULL((
                SELECT SUM(pl.CantidadPickeada)
                FROM EmpWebPickingLotes pl
                WHERE pl.IdPalletDetalle = pd.IdPalletDetalle
            ), 0) AS CantidadPickeada,
            p.NumeroPallet,
            p.IdPallet
        FROM EmpWebPalletEmpaque p
        INNER JOIN EmpWebPalletDetalle pd ON p.IdPallet = pd.IdPallet
        INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        WHERE ed.IdEmpaque = ? AND p.UsuarioAsignado = ?
        ORDER BY p.NumeroPallet, ed.CodArt
    """, (id_empaque, user_id))

    rows = cursor.fetchall()
    detalles = []
    for row in rows:
        id_pallet_detalle = row[0]
        id_empaque_detalle = row[1]
        codart = row[2]
        descripcion = row[3]
        cantidad_asignada = float(row[4]) if row[4] else 0
        cantidad_pickeada = float(row[5]) if row[5] else 0
        numero_pallet = row[6]
        id_pallet = row[7]
        
        cantidad_pendiente = cantidad_asignada - cantidad_pickeada
        
        detalles.append({
            'id_pallet_detalle': id_pallet_detalle,
            'id_empaque_detalle': id_empaque_detalle,
            'codart': codart,
            'descripcion': descripcion,
            'requerido': cantidad_asignada,
            'pickeado': cantidad_pickeada,
            'pendiente': cantidad_pendiente,
            'estado': 'COMPLETADO' if cantidad_pendiente <= 0 else ('PARCIAL' if cantidad_pickeada > 0 else 'PENDIENTE'),
            'pallet': numero_pallet,
            'id_pallet': id_pallet
        })
    
    conn.close()
    return jsonify(detalles)


@pickeo_bp.route('/picking/verificar-lote', methods=['POST'])
@menu_required('/picking')
def verificar_lote():
    """Verifica que un lote (OF) sea válido para un artículo"""
    data = request.get_json()
    nro_of = data.get('nro_of')
    codart = data.get('codart')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP 1 nroof, codart, DesArt, canretof
        FROM EmpWebLotesDisponibles
        WHERE nroof = ? AND codart = ?
    """, (nro_of, codart))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            'success': True,
            'nro_of': row[0],
            'codart': row[1],
            'descripcion': row[2],
            'disponible': float(row[3])
        })
    else:
        return jsonify({'success': False, 'error': 'Lote no válido para este artículo'})


@pickeo_bp.route('/picking/registrar-pick', methods=['POST'])
@menu_required('/picking')
def registrar_pick():
    data = request.get_json()
    id_pallet_detalle = data.get('id_pallet_detalle')
    id_empaque_detalle = data.get('id_empaque_detalle')
    nro_of = data.get('nro_of', '').strip()
    cantidad = float(data.get('cantidad', 0))
    user_id = session.get('user_id')
    codtipart = data.get('codtipart', 'PT')
    
    print(f"=== DEBUG ===")
    print(f"id_pallet_detalle: {id_pallet_detalle}")
    print(f"id_empaque_detalle: {id_empaque_detalle}")
    print(f"nro_of: '{nro_of}'")
    print(f"cantidad: {cantidad}")
    
    if not all([id_pallet_detalle, id_empaque_detalle, cantidad]):
        return jsonify({'success': False, 'error': 'Faltan datos'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Obtener información del pallet y producto
        cursor.execute("""
            SELECT p.IdEmpaque, pd.CantidadAsignada, ed.CodArt, a.codtipart,
                   ed.IdEmpaqueDetalle
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebPalletEmpaque p ON pd.IdPallet = p.IdPallet
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            INNER JOIN Artic a ON ed.CodArt = a.CodArt
            WHERE pd.IdPalletDetalle = ?
        """, (id_pallet_detalle,))
        
        detalle = cursor.fetchone()
        if not detalle:
            return jsonify({'success': False, 'error': 'Detalle no encontrado'})
        
        id_empaque = detalle[0]
        cantidad_asignada_pallet = float(detalle[1])
        codart = detalle[2]
        codtipart_bd = detalle[3] if len(detalle) > 3 else 'PT'
        id_detalle_original = detalle[4]
        
        # OBTENER TODOS LOS DETALLES PENDIENTES DE ESTE PRODUCTO EN EL EMPAQUE
        cursor.execute("""
            SELECT IdEmpaqueDetalle, NroCbt, CantidadRequerida, CantidadPickeada,
                   (CantidadRequerida - CantidadPickeada) AS Pendiente
            FROM EmpWebEmpaqueDetalle
            WHERE IdEmpaque = ? AND CodArt = ?
            AND CantidadRequerida > CantidadPickeada
            ORDER BY NroCbt
        """, (id_empaque, codart))
        
        detalles_pendientes = cursor.fetchall()
        
        if not detalles_pendientes:
            return jsonify({'success': False, 'error': 'No hay stock pendiente para este producto'})
        
        # Validar lote según tipo
        LOTE_FIJO = '2-00001'
        es_pt = codtipart_bd == 'PT'
        
        if es_pt:
            if not nro_of:
                return jsonify({'success': False, 'error': 'Debe ingresar un número de lote para productos PT'})
            
            cursor.execute("""
                SELECT canretof FROM EmpWebOFHistorico 
                WHERE nroof = ? AND codart = ?
            """, (nro_of, codart.strip()))
            
            if not cursor.fetchone():
                return jsonify({'success': False, 'error': 'Lote no válido para este producto'})
        else:
            if nro_of != LOTE_FIJO:
                print(f"Producto no PT ({codtipart_bd}). Usando lote fijo {LOTE_FIJO}")
            nro_of = LOTE_FIJO
        
        # DISTRIBUIR LA CANTIDAD PICKEADA ENTRE LOS DETALLES PENDIENTES
        cantidad_restante = cantidad
        
        for detalle_pendiente in detalles_pendientes:
            if cantidad_restante <= 0:
                break
            
            id_detalle = detalle_pendiente[0]
            nro_cbt = detalle_pendiente[1]
            cantidad_requerida = float(detalle_pendiente[2])
            cantidad_pickeada = float(detalle_pendiente[3])
            pendiente = float(detalle_pendiente[4])
            
            if pendiente <= 0:
                continue
            
            cantidad_a_pickear = min(cantidad_restante, pendiente)
            
            print(f"Pickeando {cantidad_a_pickear} del pedido {nro_cbt}, pendiente: {pendiente}")
            
            # 🔥 VERIFICAR SI YA EXISTE UN PICKEO PARA ESTE IdPalletDetalle + IdEmpaqueDetalle + NroOF
            cursor.execute("""
                SELECT IdPicking, CantidadPickeada
                FROM EmpWebPickingLotes
                WHERE IdPalletDetalle = ? AND IdEmpaqueDetalle = ? AND NroOF = ?
            """, (id_pallet_detalle, id_detalle, nro_of))
            
            pickeo_existente = cursor.fetchone()
            
            if pickeo_existente:
                # ACTUALIZAR PICKEO EXISTENTE (mismo lote)
                id_picking = pickeo_existente[0]
                nueva_cantidad = float(pickeo_existente[1]) + cantidad_a_pickear
                
                cursor.execute("""
                    UPDATE EmpWebPickingLotes
                    SET CantidadPickeada = ?,
                        FechaPick = GETDATE()
                    WHERE IdPicking = ?
                """, (nueva_cantidad, id_picking))
                print(f"DEBUG - Pickeo actualizado para detalle {id_detalle}, lote {nro_of}: {nueva_cantidad}")
            else:
                # INSERTAR NUEVO PICKEO (nuevo lote)
                cursor.execute("""
                    INSERT INTO EmpWebPickingLotes (IdEmpaque, IdEmpaqueDetalle, IdPalletDetalle, NroOF, CodArt, CantidadPickeada, UsuarioPick)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (id_empaque, id_detalle, id_pallet_detalle, nro_of, codart, cantidad_a_pickear, user_id))
                print(f"DEBUG - Nuevo pickeo para detalle {id_detalle}, lote {nro_of}: {cantidad_a_pickear}")
            
            # Actualizar el detalle del empaque
            nueva_cantidad_pickeada = cantidad_pickeada + cantidad_a_pickear
            nuevo_estado = 'COMPLETADO' if nueva_cantidad_pickeada >= cantidad_requerida else 'PARCIAL'
            
            cursor.execute("""
                UPDATE EmpWebEmpaqueDetalle 
                SET CantidadPickeada = ?,
                    Estado = ?
                WHERE IdEmpaqueDetalle = ?
            """, (nueva_cantidad_pickeada, nuevo_estado, id_detalle))
            
            cantidad_restante -= cantidad_a_pickear
        
        if cantidad_restante > 0:
            return jsonify({'success': False, 'error': f'No se pudo distribuir toda la cantidad. Faltan {cantidad_restante} unidades'})
        
        conn.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        conn.rollback()
        print(f"EXCEPCIÓN: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()
    

@pickeo_bp.route('/picking/pallets-empaque/<int:id_empaque>')
@menu_required('/picking')
def pallets_empaque(id_empaque):
    """Obtiene los pallets de un empaque para el usuario logueado"""
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Obtener pallets del empaque
    cursor.execute("""
        SELECT 
            p.IdPallet,
            p.NumeroPallet,
            p.ControlEstado
        FROM EmpWebPalletEmpaque p
        WHERE p.IdEmpaque = ? AND p.UsuarioAsignado = ?
        ORDER BY p.NumeroPallet
    """, (id_empaque, user_id))
    
    pallets_rows = cursor.fetchall()
    pallets = []
    
    for row in pallets_rows:
        id_pallet = row[0]
        numero_pallet = row[1]
        control_estado = row[2]
        
        # Obtener total de productos distintos por artículo
        cursor.execute("""
            SELECT COUNT(DISTINCT ed.CodArt)
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            WHERE pd.IdPallet = ?
        """, (id_pallet,))
        
        total_productos = cursor.fetchone()[0] or 0
        
        # Obtener total de bultos
        cursor.execute("""
            SELECT SUM(pd.CantidadAsignada)
            FROM EmpWebPalletDetalle pd
            WHERE pd.IdPallet = ?
        """, (id_pallet,))
        
        total_bultos = cursor.fetchone()[0] or 0
        
        # Obtener peso total
        cursor.execute("""
            SELECT SUM(pd.CantidadAsignada * a.PesNetArt)
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            INNER JOIN Artic a ON ed.CodArt = a.CodArt
            WHERE pd.IdPallet = ?
        """, (id_pallet,))
        
        peso_total = cursor.fetchone()[0] or 0
        
        # Obtener productos completados (donde ya se pickeó todo)
        cursor.execute("""
            SELECT COUNT(DISTINCT ed.CodArt)
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            WHERE pd.IdPallet = ?
            AND pd.CantidadAsignada <= ISNULL((
                SELECT SUM(pl.CantidadPickeada)
                FROM EmpWebPickingLotes pl
                WHERE pl.IdPalletDetalle = pd.IdPalletDetalle
            ), 0)
        """, (id_pallet,))
        
        productos_completados = cursor.fetchone()[0] or 0
        
        pallets.append({
            'id': id_pallet,
            'numero': numero_pallet,
            'control_estado': control_estado,
            'total_productos': total_productos,
            'total_bultos': int(total_bultos),
            'peso_total': float(peso_total),
            'productos_completados': productos_completados
        })
    
    conn.close()
    return jsonify(pallets)


@pickeo_bp.route('/picking/empaques-disponibles')
@menu_required('/picking')
def empaques_disponibles():
    """Obtiene los empaques listos para pickear (con pallets y usuarios asignados)"""
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT
            e.IdEmpaque,
            e.NumeroEmpaque,
            e.Cliente,
            e.DireccionEnvio,
            e.Estado
        FROM EmpWebEmpaques e
        INNER JOIN EmpWebPalletEmpaque p ON e.IdEmpaque = p.IdEmpaque
        WHERE e.Estado = 'EN_PROCESO'
        AND p.UsuarioAsignado = ?
        AND p.ControlEstado != 'VERIFICADO'
        AND EXISTS (
            SELECT 1 FROM EmpWebPalletDetalle pd
            WHERE pd.IdPallet = p.IdPallet
        )
        ORDER BY e.NumeroEmpaque
    """, (user_id,))
    
    rows = cursor.fetchall()
    empaques = []
    for row in rows:
        empaques.append({
            'id': row[0],
            'numero': row[1],
            'cliente': row[2],
            'direccion': row[3],
            'estado': row[4]
        })
    
    conn.close()
    return jsonify(empaques)


@pickeo_bp.route('/picking/verificar-lote-avanzado', methods=['POST'])
@menu_required('/picking')
def verificar_lote_avanzado():
    """Verifica un lote y devuelve información del artículo automáticamente"""
    data = request.get_json()
    nro_of = data.get('nro_of')
    id_empaque_detalle = data.get('id_empaque_detalle', None)
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    # Buscar el lote
    cursor.execute("""
        SELECT TOP 1 nroof, codart, DesArt, canretof
        FROM EmpWebLotesDisponibles
        WHERE nroof = ?
    """, (nro_of,))
    
    lote = cursor.fetchone()
    
    if not lote:
        conn.close()
        return jsonify({'success': False, 'error': 'Lote no encontrado'})
    
    nro_of, codart_lote, descripcion_lote, disponible = lote
    
    # Si se proporciona id_empaque_detalle, verificar que coincida con el artículo esperado
    if id_empaque_detalle:
        cursor.execute("""
            SELECT CodArt, CantidadRequerida, CantidadPickeada
            FROM EmpWebEmpaqueDetalle
            WHERE IdEmpaqueDetalle = ?
        """, (id_empaque_detalle,))
        
        detalle = cursor.fetchone()
        if detalle:
            codart_esperado = detalle[0]
            if codart_lote.strip() != codart_esperado.strip():
                conn.close()
                return jsonify({
                    'success': False, 
                    'error': f'El lote corresponde a {codart_lote} pero se esperaba {codart_esperado}'
                })
    
    conn.close()
    
    return jsonify({
        'success': True,
        'nro_of': nro_of,
        'codart': codart_lote,
        'descripcion': descripcion_lote,
        'disponible': float(disponible)
    })

@pickeo_bp.route('/picking/productos-pallet/<int:id_pallet>')
@menu_required('/picking')
def productos_pallet(id_pallet):
    """Obtiene los productos de un pallet específico agrupados por artículo"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Agrupar por CodArt para sumar las cantidades, incluyendo codtipart
    cursor.execute("""
        SELECT 
            ed.CodArt,
            MAX(a.DesArt) AS Descripcion,
            SUM(pd.CantidadAsignada) AS CantidadRequerida,
            MAX(a.codtipart) AS codtipart
        FROM EmpWebPalletDetalle pd
        INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        WHERE pd.IdPallet = ?
        GROUP BY ed.CodArt
        ORDER BY ed.CodArt
    """, (id_pallet,))
    
    productos = []
    for row in cursor.fetchall():
        codart = row[0]
        descripcion = row[1]
        cantidad_requerida = float(row[2]) if row[2] else 0
        codtipart = row[3] if len(row) > 3 else 'PT'
        
        # Obtener la cantidad pickeada TOTAL para este producto en este pallet
        cursor.execute("""
            SELECT ISNULL(SUM(pl.CantidadPickeada), 0)
            FROM EmpWebPickingLotes pl
            INNER JOIN EmpWebPalletDetalle pd ON pl.IdPalletDetalle = pd.IdPalletDetalle
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            WHERE pd.IdPallet = ? AND ed.CodArt = ?
        """, (id_pallet, codart))
        
        row_pick = cursor.fetchone()
        cantidad_pickeada = float(row_pick[0]) if row_pick and row_pick[0] else 0
        cantidad_pendiente = cantidad_requerida - cantidad_pickeada
        
        if cantidad_pendiente > 0:
            # Obtener UN IdPalletDetalle que tenga stock pendiente
            cursor.execute("""
                SELECT TOP 1 pd.IdPalletDetalle, ed.IdEmpaqueDetalle
                FROM EmpWebPalletDetalle pd
                INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
                WHERE pd.IdPallet = ? AND ed.CodArt = ?
                AND pd.CantidadAsignada > ISNULL((
                    SELECT SUM(pl.CantidadPickeada)
                    FROM EmpWebPickingLotes pl
                    WHERE pl.IdPalletDetalle = pd.IdPalletDetalle
                ), 0)
            """, (id_pallet, codart))
            
            ref = cursor.fetchone()
            if ref:
                id_pallet_detalle = ref[0]
                id_empaque_detalle = ref[1]
            else:
                cursor.execute("""
                    SELECT TOP 1 pd.IdPalletDetalle, ed.IdEmpaqueDetalle
                    FROM EmpWebPalletDetalle pd
                    INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
                    WHERE pd.IdPallet = ? AND ed.CodArt = ?
                """, (id_pallet, codart))
                ref = cursor.fetchone()
                id_pallet_detalle = ref[0] if ref else 0
                id_empaque_detalle = ref[1] if ref else 0
            
            productos.append({
                'id_pallet_detalle': id_pallet_detalle,
                'id_empaque_detalle': id_empaque_detalle,
                'codart': codart.strip(),
                'descripcion': descripcion,
                'requerido': cantidad_requerida,
                'pickeado': cantidad_pickeada,
                'pendiente': cantidad_pendiente,
                'codtipart': codtipart  # 🔥 AGREGADO
            })
    
    conn.close()
    return jsonify(productos)

@pickeo_bp.route('/picking/productos-pickeado/<int:id_pallet>')
@menu_required('/picking')
def productos_pickeado(id_pallet):
    """Obtiene los productos ya pickeados de un pallet con cantidades pedidas"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            ed.CodArt,
            MAX(a.DesArt) AS Descripcion,
            SUM(pd.CantidadAsignada) AS CantidadPedida,
            SUM(pl.CantidadPickeada) AS CantidadPickeada
        FROM EmpWebPalletDetalle pd
        INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        LEFT JOIN EmpWebPickingLotes pl ON pd.IdPalletDetalle = pl.IdPalletDetalle
        WHERE pd.IdPallet = ?
        GROUP BY ed.CodArt
        ORDER BY ed.CodArt
    """, (id_pallet,))
    
    rows = cursor.fetchall()
    
    productos = []
    for row in rows:
        cantidad_pedida = float(row[2]) if row[2] else 0
        cantidad_pickeada = float(row[3]) if row[3] else 0
        diferencia = cantidad_pedida - cantidad_pickeada
        
        productos.append({
            'codart': row[0],
            'descripcion': row[1] or '',
            'cantidad_pedida': cantidad_pedida,
            'cantidad_pickeada': cantidad_pickeada,
            'diferencia': diferencia
        })
    
    conn.close()
    return jsonify(productos)