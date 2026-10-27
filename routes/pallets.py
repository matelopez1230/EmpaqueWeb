from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
import pyodbc
from datetime import datetime

pallets_bp = Blueprint('pallets', __name__)

@pallets_bp.route('/gestion-pallets')
@menu_required('/gestion-pallets')
def index():
    """Página principal de gestión de pallets"""
    return render_template('pallets/index.html')

@pallets_bp.route('/gestion-pallets/empaques-disponibles')
@menu_required('/gestion-pallets')
def empaques_disponibles():
    """Obtiene empaques en estado EN_PROCESO que tienen productos pendientes de asignación de pallets"""
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
        AND ed.CantidadRequerida > ISNULL(ed.CantidadPickeada, 0)
        AND NOT EXISTS (
            SELECT 1 
            FROM EmpWebPedidosRemitidos r 
            WHERE r.NumeroEmpaque = e.NumeroEmpaque
        )
        ORDER BY e.NumeroEmpaque
    """)
    
    rows = cursor.fetchall()
    print(f"DEBUG - Empaques encontrados: {len(rows)}")
    
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

@pallets_bp.route('/gestion-pallets/productos-pendientes/<int:id_empaque>')
@menu_required('/gestion-pallets')
def productos_pendientes(id_empaque):
    """Obtiene productos pendientes de asignación de pallet para un empaque"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Obtener productos agrupados por artículo con un IdEmpaqueDetalle de referencia
    cursor.execute("""
        SELECT 
            ed.CodArt,
            MAX(a.DesArt) AS Descripcion,
            SUM(ed.CantidadRequerida - ISNULL(ed.CantidadPickeada, 0)) AS CantidadPendiente,
            MAX(a.PesNetArt) AS PesoUnitario,
            SUM((ed.CantidadRequerida - ISNULL(ed.CantidadPickeada, 0)) * a.PesNetArt) AS PesoTotal,
            ISNULL(um.desunimed, 'SIN UNIDAD') AS UnidadMedida,
            MIN(ed.IdEmpaqueDetalle) AS IdEmpaqueDetalleReferencia
        FROM EmpWebEmpaqueDetalle ed
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        LEFT JOIN UniMe um ON a.unimedstk = um.codunimed
        WHERE ed.IdEmpaque = ?
        GROUP BY ed.CodArt, um.desunimed
        HAVING SUM(ed.CantidadRequerida - ISNULL(ed.CantidadPickeada, 0)) > 0
        ORDER BY um.desunimed ASC , MAX(a.PesNetArt) DESC, MAX(a.CodNivArt1) DESC, MAX(a.CodNivArt2) DESC, MAX(a.DesArt) DESC
    """, (id_empaque,))
    
    rows = cursor.fetchall()
    productos = []
    
    for row in rows:
        codart = row[0]
        descripcion = row[1]
        cantidad_pendiente = float(row[2]) if row[2] else 0
        peso_unitario = float(row[3]) if row[3] else 0
        peso_total = float(row[4]) if row[4] else 0
        unidad_medida = row[5] or 'SIN UNIDAD'
        id_empaque_detalle_ref = row[6]
        
        # Obtener cantidad ya asignada a pallets
        cursor.execute("""
            SELECT ISNULL(SUM(pd.CantidadAsignada), 0)
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebPalletEmpaque pe ON pd.IdPallet = pe.IdPallet
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            WHERE pe.IdEmpaque = ? AND ed.CodArt = ?
        """, (id_empaque, codart))
        
        row_asignado = cursor.fetchone()
        cantidad_asignada = float(row_asignado[0]) if row_asignado and row_asignado[0] else 0
        cantidad_disponible = cantidad_pendiente - cantidad_asignada
        
        if cantidad_disponible > 0:
            productos.append({
                'id': id_empaque_detalle_ref,  # ID real del detalle
                'codart': codart,
                'descripcion': descripcion,
                'cantidad_pendiente': cantidad_disponible,
                'peso_unitario': peso_unitario,
                'peso_total': cantidad_disponible * peso_unitario,
                'unidad_medida': unidad_medida,
                'cantidad_asignada': cantidad_asignada
            })
    
    conn.close()
    return jsonify(productos)

@pallets_bp.route('/gestion-pallets/pallets-empaque/<int:id_empaque>')
@menu_required('/gestion-pallets')
def pallets_empaque(id_empaque):
    """Obtiene los pallets ya creados para un empaque"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.IdPallet,
            p.NumeroPallet,
            p.UsuarioAsignado,
            u.NombreUsuario,
            p.Estado,
            p.FechaAsignacion,
            COUNT(pd.IdPalletDetalle) AS CantidadProductos,
            ISNULL(SUM(pd.CantidadAsignada * art.PesNetArt), 0) AS PesoTotal,
            ISNULL(SUM(pd.CantidadAsignada), 0) AS TotalBultos
        FROM EmpWebPalletEmpaque p
        LEFT JOIN EmpWebUsuarios u ON p.UsuarioAsignado = u.IdUsuario
        LEFT JOIN EmpWebPalletDetalle pd ON p.IdPallet = pd.IdPallet
        LEFT JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
        LEFT JOIN Artic art ON ed.CodArt = art.CodArt
        WHERE p.IdEmpaque = ?
        GROUP BY p.IdPallet, p.NumeroPallet, p.UsuarioAsignado, u.NombreUsuario, p.Estado, p.FechaAsignacion
        ORDER BY p.NumeroPallet
    """, (id_empaque,))
    
    rows = cursor.fetchall()
    pallets = []
    for row in rows:
        pallets.append({
            'id': row[0],
            'numero': row[1],
            'usuario_id': row[2],
            'usuario_nombre': row[3] or 'No asignado',
            'estado': row[4],
            'fecha': row[5].strftime('%d/%m/%Y %H:%M') if row[5] else '',
            'cantidad_productos': row[6] or 0,
            'peso_total': float(row[7]) if row[7] else 0,
            'total_bultos': int(row[8]) if row[8] else 0
        })
    
    conn.close()
    return jsonify(pallets)

@pallets_bp.route('/gestion-pallets/crear-pallet', methods=['POST'])
@menu_required('/gestion-pallets')
def crear_pallet():
    """Crea un nuevo pallet para el empaque"""
    data = request.get_json()
    id_empaque = data.get('id_empaque')
    numero_pallet = data.get('numero_pallet')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Verificar que el número de pallet no exista en el empaque
        cursor.execute("""
            SELECT COUNT(*) FROM EmpWebPalletEmpaque
            WHERE IdEmpaque = ? AND NumeroPallet = ?
        """, (id_empaque, numero_pallet))
        
        if cursor.fetchone()[0] > 0:
            return jsonify({'success': False, 'error': f'El pallet N° {numero_pallet} ya existe en este empaque'})
        
        # Crear pallet
        cursor.execute("""
            INSERT INTO EmpWebPalletEmpaque (IdEmpaque, NumeroPallet, FechaAsignacion, Estado)
            OUTPUT INSERTED.IdPallet
            VALUES (?, ?, GETDATE(), 'PENDIENTE')
        """, (id_empaque, numero_pallet))
        
        id_pallet = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({'success': True, 'id_pallet': id_pallet, 'numero': numero_pallet})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@pallets_bp.route('/gestion-pallets/asignar-producto', methods=['POST'])
@menu_required('/gestion-pallets')
def asignar_producto():
    """Asigna un producto a un pallet"""
    data = request.get_json()
    id_pallet = data.get('id_pallet')
    id_empaque_detalle = data.get('id_empaque_detalle')
    cantidad = float(data.get('cantidad', 0))
    
    print(f"DEBUG - asignar_producto: id_pallet={id_pallet}, id_empaque_detalle={id_empaque_detalle}, cantidad={cantidad}")
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Obtener el peso del producto y cantidad pendiente
        cursor.execute("""
            SELECT a.PesNetArt, ed.CantidadRequerida, ISNULL(ed.CantidadPickeada, 0)
            FROM EmpWebEmpaqueDetalle ed
            INNER JOIN Artic a ON ed.CodArt = a.CodArt
            WHERE ed.IdEmpaqueDetalle = ?
        """, (id_empaque_detalle,))
        
        row = cursor.fetchone()
        print(f"DEBUG - row: {row}")
        
        if not row:
            return jsonify({'success': False, 'error': 'Producto no encontrado'})
        
        peso_unitario = float(row[0]) if row[0] else 0
        cantidad_requerida = float(row[1]) if row[1] else 0
        cantidad_pickeada = float(row[2]) if row[2] else 0
        cantidad_pendiente = cantidad_requerida - cantidad_pickeada
        
        print(f"DEBUG - peso_unitario={peso_unitario}, cantidad_requerida={cantidad_requerida}, cantidad_pickeada={cantidad_pickeada}, cantidad_pendiente={cantidad_pendiente}")
        
        if cantidad > cantidad_pendiente:
            return jsonify({'success': False, 'error': f'La cantidad excede lo pendiente. Pendiente: {cantidad_pendiente}'})
        
        # Verificar peso del pallet
        cursor.execute("""
            SELECT ISNULL(SUM(pd.CantidadAsignada * a.PesNetArt), 0)
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebPalletEmpaque p ON pd.IdPallet = p.IdPallet
            INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
            INNER JOIN Artic a ON ed.CodArt = a.CodArt
            WHERE p.IdPallet = ?
        """, (id_pallet,))
        
        row_peso = cursor.fetchone()
        peso_actual = float(row_peso[0]) if row_peso and row_peso[0] else 0
        nuevo_peso = peso_actual + (cantidad * peso_unitario)
        
        print(f"DEBUG - peso_actual={peso_actual}, nuevo_peso={nuevo_peso}")
        
        if nuevo_peso > 960:
            return jsonify({'success': False, 'error': f'El pallet excedería los 960 kg. Peso actual: {peso_actual:.2f} kg, Máximo permitido: 960 kg'})
        
        # Verificar si ya existe asignación
        cursor.execute("""
            SELECT COUNT(*) FROM EmpWebPalletDetalle
            WHERE IdPallet = ? AND IdEmpaqueDetalle = ?
        """, (id_pallet, id_empaque_detalle))
        
        row_count = cursor.fetchone()
        existe = row_count[0] if row_count else 0
        
        if existe > 0:
            # Actualizar cantidad
            cursor.execute("""
                UPDATE EmpWebPalletDetalle
                SET CantidadAsignada = CantidadAsignada + ?, FechaAsignacion = GETDATE()
                WHERE IdPallet = ? AND IdEmpaqueDetalle = ?
            """, (cantidad, id_pallet, id_empaque_detalle))
            print("DEBUG - Actualizado")
        else:
            # Insertar nueva asignación
            cursor.execute("""
                INSERT INTO EmpWebPalletDetalle (IdPallet, IdEmpaqueDetalle, CantidadAsignada, FechaAsignacion)
                VALUES (?, ?, ?, GETDATE())
            """, (id_pallet, id_empaque_detalle, cantidad))
            print("DEBUG - Insertado")
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'peso_actual': nuevo_peso,
            'cantidad_restante': cantidad_pendiente - cantidad
        })
        
    except Exception as e:
        conn.rollback()
        print(f"DEBUG - EXCEPCIÓN: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@pallets_bp.route('/gestion-pallets/asignar-multiple', methods=['POST'])
@menu_required('/gestion-pallets')
def asignar_multiple():
    data = request.get_json()
    id_pallet = data.get('id_pallet')
    productos = data.get('productos', [])
    
    if not id_pallet or not productos:
        return jsonify({'success': False, 'error': 'Faltan datos'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        for prod in productos:
            id_empaque_detalle_ref = prod.get('id_empaque_detalle')
            cantidad = float(prod.get('cantidad', 0))
            
            if cantidad <= 0:
                continue
            
            # Obtener el empaque y el producto
            cursor.execute("""
                SELECT IdEmpaque, CodArt
                FROM EmpWebEmpaqueDetalle
                WHERE IdEmpaqueDetalle = ?
            """, (id_empaque_detalle_ref,))
            
            row = cursor.fetchone()
            if not row:
                continue
            
            id_empaque = row[0]
            codart = row[1]
            
            # 🔥 PASO 1: Calcular disponibilidad total (sin subconsultas complejas)
            cursor.execute("""
                SELECT 
                    SUM(ed.CantidadRequerida - ed.CantidadPickeada) AS DisponibleTotal
                FROM EmpWebEmpaqueDetalle ed
                WHERE ed.IdEmpaque = ? AND ed.CodArt = ?
                GROUP BY ed.CodArt
            """, (id_empaque, codart))
            
            disponibilidad_total = cursor.fetchone()
            disponible_total = float(disponibilidad_total[0]) if disponibilidad_total and disponibilidad_total[0] else 0
            
            if disponible_total <= 0:
                return jsonify({
                    'success': False,
                    'error': f'No hay stock disponible para {codart}'
                })
            
            # 🔥 PASO 2: Calcular cantidad ya asignada a pallets
            cursor.execute("""
                SELECT ISNULL(SUM(pd.CantidadAsignada), 0)
                FROM EmpWebPalletDetalle pd
                INNER JOIN EmpWebPalletEmpaque pe ON pd.IdPallet = pe.IdPallet
                INNER JOIN EmpWebEmpaqueDetalle ed ON pd.IdEmpaqueDetalle = ed.IdEmpaqueDetalle
                WHERE pe.IdEmpaque = ? AND ed.CodArt = ?
            """, (id_empaque, codart))
            
            asignado = cursor.fetchone()
            cantidad_asignada = float(asignado[0]) if asignado and asignado[0] else 0
            
            disponible_real = disponible_total - cantidad_asignada
            
            print(f"DEBUG - Producto {codart}: Total={disponible_total}, Asignado={cantidad_asignada}, Real={disponible_real}")
            
            if disponible_real < cantidad:
                return jsonify({
                    'success': False,
                    'error': f'Cantidad excede disponible para {codart}. Disponible: {disponible_real}'
                })
            
            # 🔥 PASO 3: Asignar distribuyendo entre los pedidos
            cantidad_restante = cantidad
            
            # Obtener los detalles con stock pendiente (sin subconsultas)
            cursor.execute("""
                SELECT 
                    ed.IdEmpaqueDetalle,
                    ed.NroCbt,
                    ed.CantidadRequerida - ed.CantidadPickeada AS DisponibleDetalle
                FROM EmpWebEmpaqueDetalle ed
                WHERE ed.IdEmpaque = ? AND ed.CodArt = ?
                AND ed.CantidadRequerida > ed.CantidadPickeada
                ORDER BY ed.NroCbt
            """, (id_empaque, codart))
            
            detalles = cursor.fetchall()
            
            if not detalles:
                return jsonify({
                    'success': False,
                    'error': f'No hay detalles disponibles para {codart}'
                })
            
            for detalle in detalles:
                if cantidad_restante <= 0:
                    break
                
                id_detalle = detalle[0]
                nro_cbt = detalle[1]
                disponible_detalle = float(detalle[2]) if detalle[2] else 0
                
                # 🔥 Obtener cuánto ya se asignó de este detalle
                cursor.execute("""
                    SELECT ISNULL(SUM(pd.CantidadAsignada), 0)
                    FROM EmpWebPalletDetalle pd
                    WHERE pd.IdEmpaqueDetalle = ?
                """, (id_detalle,))
                
                asignado_detalle = cursor.fetchone()
                cantidad_asignada_detalle = float(asignado_detalle[0]) if asignado_detalle and asignado_detalle[0] else 0
                
                disponible_detalle_real = disponible_detalle - cantidad_asignada_detalle
                
                if disponible_detalle_real <= 0:
                    continue
                
                cantidad_a_asignar = min(cantidad_restante, disponible_detalle_real)
                
                print(f"DEBUG - Asignando {cantidad_a_asignar} al pedido {nro_cbt}")
                
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM EmpWebPalletDetalle WHERE IdPallet = ? AND IdEmpaqueDetalle = ?)
                        UPDATE EmpWebPalletDetalle
                        SET CantidadAsignada = CantidadAsignada + ?, FechaAsignacion = GETDATE()
                        WHERE IdPallet = ? AND IdEmpaqueDetalle = ?
                    ELSE
                        INSERT INTO EmpWebPalletDetalle (IdPallet, IdEmpaqueDetalle, CantidadAsignada, FechaAsignacion)
                        VALUES (?, ?, ?, GETDATE())
                """, (id_pallet, id_detalle, cantidad_a_asignar, id_pallet, id_detalle, id_pallet, id_detalle, cantidad_a_asignar))
                
                cantidad_restante -= cantidad_a_asignar
            
            if cantidad_restante > 0:
                return jsonify({
                    'success': False,
                    'error': f'No se pudo asignar toda la cantidad. Faltan {cantidad_restante} unidades'
                })
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Productos asignados correctamente'})
    
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@pallets_bp.route('/gestion-pallets/asignar-usuario', methods=['POST'])
@menu_required('/gestion-pallets')
def asignar_usuario():
    """Asigna un usuario a uno o todos los pallets"""
    data = request.get_json()
    id_pallet = data.get('id_pallet')
    id_empaque = data.get('id_empaque')
    usuario_id = data.get('usuario_id')
    asignar_todos = data.get('asignar_todos', False)
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        if asignar_todos:
            cursor.execute("""
                UPDATE EmpWebPalletEmpaque
                SET UsuarioAsignado = ?, FechaAsignacion = GETDATE()
                WHERE IdEmpaque = ?
            """, (usuario_id, id_empaque))
        else:
            cursor.execute("""
                UPDATE EmpWebPalletEmpaque
                SET UsuarioAsignado = ?, FechaAsignacion = GETDATE()
                WHERE IdPallet = ?
            """, (usuario_id, id_pallet))
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@pallets_bp.route('/gestion-pallets/usuarios')
@menu_required('/gestion-pallets')
def get_usuarios():
    """Obtiene lista de usuarios para asignar a pallets"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT IdUsuario, NombreUsuario
        FROM EmpWebUsuarios
        WHERE Activo = 1
        ORDER BY NombreUsuario
    """)
    
    rows = cursor.fetchall()
    usuarios = []
    for row in rows:
        usuarios.append({
            'id': row[0],
            'nombre': row[1]
        })
    
    conn.close()
    return jsonify(usuarios)