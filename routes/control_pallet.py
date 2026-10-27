from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime

control_pallet_bp = Blueprint('control_pallet', __name__)

@control_pallet_bp.route('/control-pallet')
@menu_required('/control-pallet')
def index():
    """Página principal de control de pallet"""
    return render_template('control_pallet/index.html')

@control_pallet_bp.route('/control-pallet/empaques-disponibles')
@menu_required('/control-pallet')
def empaques_disponibles():
    """Obtiene empaques que tienen pallets pendientes de verificar O ya verificados (para mostrar el botón cerrar)"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            e.IdEmpaque,
            e.NumeroEmpaque,
            e.Cliente,
            e.DireccionEnvio,
            COUNT(DISTINCT p.IdPallet) as TotalPallets,
            SUM(CASE WHEN p.ControlEstado = 'VERIFICADO' THEN 1 ELSE 0 END) as Verificados
        FROM EmpWebEmpaques e
        INNER JOIN EmpWebPalletEmpaque p ON e.IdEmpaque = p.IdEmpaque
        WHERE e.Estado = 'EN_PROCESO'
        AND EXISTS (
            SELECT 1 FROM EmpWebPalletDetalle pd WHERE pd.IdPallet = p.IdPallet
        )
        GROUP BY e.IdEmpaque, e.NumeroEmpaque, e.Cliente, e.DireccionEnvio
        ORDER BY e.NumeroEmpaque
    """)
    
    rows = cursor.fetchall()
    print(f"DEBUG - Empaques encontrados: {len(rows)}")  # Debug
    
    empaques = []
    for row in rows:
        empaques.append({
            'id': row[0],
            'numero': row[1],
            'cliente': row[2],
            'direccion': row[3],
            'total_pallets': row[4] or 0,
            'verificados': row[5] or 0
        })
    
    conn.close()
    return jsonify(empaques)

@control_pallet_bp.route('/control-pallet/pallets-empaque/<int:id_empaque>')
@menu_required('/control-pallet')
def pallets_empaque(id_empaque):
    """Obtiene los pallets de un empaque pendientes de verificar"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.IdPallet,
            p.NumeroPallet,
            p.ControlEstado,
            COUNT(DISTINCT ed.CodArt) as TotalProductos,
            COUNT(DISTINCT CASE WHEN cp.IdControl IS NOT NULL THEN ed.CodArt END) as ProductosVerificados,
            SUM(pd.CantidadAsignada) as TotalBultos,
            SUM(pd.CantidadAsignada * a.PesNetArt) as PesoTotal
        FROM EmpWebPalletEmpaque p
        INNER JOIN EmpWebPalletDetalle pd ON p.IdPallet = pd.IdPallet
        INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        LEFT JOIN EmpWebControlPalletDetalle cpd ON pd.IdPalletDetalle = cpd.IdPalletDetalle
        LEFT JOIN EmpWebControlPallet cp ON cpd.IdControl = cp.IdControl AND cp.IdPallet = p.IdPallet
        WHERE p.IdEmpaque = ?
        GROUP BY p.IdPallet, p.NumeroPallet, p.ControlEstado
        ORDER BY p.NumeroPallet
    """, (id_empaque,))
    
    rows = cursor.fetchall()
    pallets = []
    for row in rows:
        pallets.append({
            'id': row[0],
            'numero': row[1],
            'control_estado': row[2],
            'total_productos': row[3] or 0,
            'productos_verificados': row[4] or 0,
            'total_bultos': int(row[5]) if row[5] else 0,
            'peso_total': float(row[6]) if row[6] else 0
        })
    
    conn.close()
    return jsonify(pallets)

@control_pallet_bp.route('/control-pallet/productos-pallet/<int:id_pallet>')
@menu_required('/control-pallet')
def productos_pallet(id_pallet):
    """Obtiene los productos de un pallet para control, agrupados por artículo"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            ed.CodArt,
            MAX(a.DesArt) AS Descripcion,
            SUM(pd.CantidadAsignada) AS CantidadAsignada,
            SUM(ISNULL(pl.CantidadPickeada, 0)) AS CantidadPickeada,
            SUM(pd.CantidadAsignada) - SUM(ISNULL(pl.CantidadPickeada, 0)) AS CantidadPendiente,
            COUNT(DISTINCT ed.IdEmpaqueDetalle) AS CantidadPedidos
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
        codart = row[0]
        descripcion = row[1]
        cantidad_asignada = float(row[2]) if row[2] else 0
        cantidad_pickeada = float(row[3]) if row[3] else 0
        cantidad_pendiente = float(row[4]) if row[4] else 0
        cantidad_pedidos = row[5] or 1
        
        # Verificar si ya fue controlado (por artículo)
        cursor.execute("""
            SELECT COUNT(*) FROM EmpWebControlPalletDetalle cpd
            INNER JOIN EmpWebControlPallet cp ON cpd.IdControl = cp.IdControl
            INNER JOIN EmpWebPalletDetalle pd ON cpd.IdPalletDetalle = pd.IdPalletDetalle
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            WHERE cp.IdPallet = ? AND ed.CodArt = ?
        """, (id_pallet, codart))
        
        verificado = cursor.fetchone()[0] > 0
        
        productos.append({
            'codart': codart,
            'descripcion': descripcion,
            'cantidad_asignada': cantidad_asignada,
            'cantidad_pickeada': cantidad_pickeada,
            'cantidad_pendiente': cantidad_pendiente,
            'cantidad_pedidos': cantidad_pedidos,
            'verificado': verificado
        })
    
    conn.close()
    return jsonify(productos)

@control_pallet_bp.route('/control-pallet/cerrar-empaque', methods=['POST'])
@menu_required('/control-pallet')
def cerrar_empaque():
    """Cierra un empaque cuando todos los pallets están verificados (SOLO con el botón)"""
    data = request.get_json()
    id_empaque = data.get('id_empaque')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Verificar que todos los pallets estén verificados
        cursor.execute("""
            SELECT 
                COUNT(*) as TotalPallets,
                SUM(CASE WHEN ControlEstado = 'VERIFICADO' THEN 1 ELSE 0 END) as Verificados
            FROM EmpWebPalletEmpaque
            WHERE IdEmpaque = ?
        """, (id_empaque,))
        
        row = cursor.fetchone()
        total = row[0] or 0
        verificados = row[1] or 0
        
        if total == 0:
            return jsonify({'success': False, 'error': 'No hay pallets en este empaque'})
        
        if verificados < total:
            return jsonify({'success': False, 'error': f'Faltan {total - verificados} pallet(s) por verificar'})
        
        # Actualizar estado del empaque
        cursor.execute("""
            UPDATE EmpWebEmpaques
            SET ControlCompletado = 1,
                Estado = 'CONTROL_COMPLETADO'
            WHERE IdEmpaque = ?
        """, (id_empaque,))
        
        # 🔥 ELIMINAR RESERVAS ASOCIADAS A ESTE EMPAQUE 🔥
        # Esto evita que se reste stock dos veces (una por reserva y otra por el empaque cerrado)
        cursor.execute("""
            DELETE FROM EmpWebReservasPendientes
            WHERE NroCbt IN (
                SELECT DISTINCT ed.NroCbt
                FROM EmpWebEmpaqueDetalle ed
                WHERE ed.IdEmpaque = ?
            )
        """, (id_empaque,))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Empaque cerrado exitosamente. Reservas eliminadas.'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()
    
 
@control_pallet_bp.route('/control-pallet/verificar-producto', methods=['POST'])
@menu_required('/control-pallet')
def verificar_producto():
    """Verifica un producto de un pallet (por código de artículo)"""
    data = request.get_json()
    id_pallet = data.get('id_pallet')
    codart = data.get('codart')
    verificado = data.get('verificado', True)
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Obtener todos los IdPalletDetalle para este artículo en el pallet
        cursor.execute("""
            SELECT pd.IdPalletDetalle
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            WHERE pd.IdPallet = ? AND ed.CodArt = ?
        """, (id_pallet, codart))
        
        ids_pallet_detalle = [row[0] for row in cursor.fetchall()]
        
        if not ids_pallet_detalle:
            return jsonify({'success': False, 'error': 'Producto no encontrado en este pallet'})
        
        # Buscar o crear el control del pallet
        cursor.execute("""
            SELECT IdControl FROM EmpWebControlPallet
            WHERE IdPallet = ? AND Estado = 'PENDIENTE'
        """, (id_pallet,))
        
        control_row = cursor.fetchone()
        
        if not control_row:
            cursor.execute("""
                INSERT INTO EmpWebControlPallet (IdPallet, IdUsuario, FechaControl, Estado)
                OUTPUT INSERTED.IdControl
                VALUES (?, ?, GETDATE(), 'PENDIENTE')
            """, (id_pallet, user_id))
            id_control = cursor.fetchone()[0]
        else:
            id_control = control_row[0]
        
        if verificado:
            # Agregar verificación para cada IdPalletDetalle
            for id_pd in ids_pallet_detalle:
                cursor.execute("""
                    IF NOT EXISTS (SELECT 1 FROM EmpWebControlPalletDetalle WHERE IdControl = ? AND IdPalletDetalle = ?)
                    INSERT INTO EmpWebControlPalletDetalle (IdControl, IdPalletDetalle, CantidadVerificada, FechaVerificacion)
                    VALUES (?, ?, 0, GETDATE())
                """, (id_control, id_pd, id_control, id_pd))
        else:
            # Eliminar verificación
            for id_pd in ids_pallet_detalle:
                cursor.execute("""
                    DELETE FROM EmpWebControlPalletDetalle
                    WHERE IdControl = ? AND IdPalletDetalle = ?
                """, (id_control, id_pd))
        
        # Verificar si todos los productos del pallet están verificados
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT ed.CodArt) as Total,
                COUNT(DISTINCT CASE WHEN cpd.IdControlDetalle IS NOT NULL THEN ed.CodArt END) as Verificados
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            LEFT JOIN EmpWebControlPalletDetalle cpd ON pd.IdPalletDetalle = cpd.IdPalletDetalle
            LEFT JOIN EmpWebControlPallet cp ON cpd.IdControl = cp.IdControl AND cp.IdPallet = pd.IdPallet
            WHERE pd.IdPallet = ?
        """, (id_pallet,))
        
        row = cursor.fetchone()
        total = row[0] or 0
        verificados = row[1] or 0
        
        if verificados >= total and total > 0:
            cursor.execute("""
                UPDATE EmpWebPalletEmpaque
                SET ControlEstado = 'VERIFICADO'
                WHERE IdPallet = ?
            """, (id_pallet,))
            
            cursor.execute("""
                UPDATE EmpWebControlPallet
                SET Estado = 'VERIFICADO'
                WHERE IdControl = ?
            """, (id_control,))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'pallet_completado': verificados >= total,
            'total': total,
            'verificados': verificados
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()