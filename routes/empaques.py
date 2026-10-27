from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
import pyodbc
from datetime import datetime

empaques_bp = Blueprint('empaques', __name__)

@empaques_bp.route('/empaques')
@menu_required('/empaques')
def index():
    """Página principal de gestión de empaques"""
    return render_template('empaques/index.html')

@empaques_bp.route('/empaques/productos-agrupados')
@menu_required('/empaques')
def productos_agrupados():
    """Obtiene productos agrupados que NO tienen empaque"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            p.codgrpemp AS CodGrupo,
            p.deszonvta AS Zona,
            p.Cliente,
            p.DomEnv AS DireccionEnvio,
            p.CodArt,
            p.CodDesArticulo,
            p.Orden,
            p.Observaciones,
            r.CantidadReservada AS Cantidad,
            p.NroCbt AS Pedido
        FROM EmpWebPedidosConStock p
        INNER JOIN EmpWebReservasPendientes r 
            ON p.NroCbt = r.NroCbt 
            AND p.CodArt = r.CodArt
            AND r.Estado = 'RESERVADO'
        WHERE NOT EXISTS (
            SELECT 1 
            FROM EmpWebEmpaqueDetalle ed
            INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
            WHERE ed.NroCbt = p.NroCbt 
            AND ed.CodArt = p.CodArt
            AND e.Estado IN ('EN_PROCESO', 'PALLETIZADO', 'COMPLETADO')
        )
        ORDER BY p.codgrpemp, p.deszonvta, p.DomEnv
    """)
    
    rows = cursor.fetchall()
    
    grupos = {}
    for row in rows:
        codgrpemp = row[0]
        zona = row[1]
        cliente = row[2]
        direccion = row[3]
        codart = row[4]
        descripcion = row[5]
        orden = row[6] or ''
        observaciones = row[7] or ''
        cantidad = float(row[8]) if row[8] else 0
        pedido = row[9]
        
        key = (codgrpemp, zona, direccion)
        
        if key not in grupos:
            grupos[key] = {
                'CodGrupo': codgrpemp,
                'Zona': zona,
                'Cliente': cliente,
                'DireccionEnvio': direccion,
                'CodArt': [],
                'CodDesArticulo': [],
                'Ordenes': set(),
                'ObservacionesList': set(),
                'TotalReservado': 0,
                'Pedidos': set(),
                'NombresCliente': set()
            }
        
        grupos[key]['CodArt'].append(codart)
        grupos[key]['CodDesArticulo'].append(descripcion)
        grupos[key]['TotalReservado'] += cantidad
        if orden:
            grupos[key]['Ordenes'].add(orden)
        if observaciones:
            grupos[key]['ObservacionesList'].add(observaciones)
        grupos[key]['Pedidos'].add(pedido)
        grupos[key]['NombresCliente'].add(cliente)
    
    productos = []
    for key, item in grupos.items():
        nombre_cliente = ' / '.join(item['NombresCliente']) if len(item['NombresCliente']) > 1 else item['Cliente']
        
        productos.append({
            'CodGrupo': item['CodGrupo'],
            'Zona': item['Zona'],
            'Cliente': nombre_cliente,
            'DireccionEnvio': item['DireccionEnvio'],
            'CodArt': ', '.join(item['CodArt']),
            'CodDesArticulo': ', '.join(item['CodDesArticulo']),
            'Orden': ' / '.join(item['Ordenes']) if item['Ordenes'] else '',
            'Observaciones': ' / '.join(item['ObservacionesList']) if item['ObservacionesList'] else '',
            'TotalReservado': item['TotalReservado'],
            'CantidadPedidos': len(item['Pedidos'])
        })
    
    conn.close()
    return jsonify(productos)

@empaques_bp.route('/empaques/detalle-por-grupo', methods=['POST'])
@menu_required('/empaques')
def detalle_por_grupo():
    """Obtiene el detalle de productos por pedido para un grupo específico"""
    data = request.get_json()
    codgrpemp = data.get('codgrpemp')
    direccion = data.get('direccion')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    # 🔥 CONSULTA SIMPLE: Solo reservas activas
    cursor.execute("""
        SELECT 
            p.NroCbt AS Pedido,
            p.CodArt,
            p.CodDesArticulo AS Descripcion,
            r.CantidadReservada AS Cantidad,
            p.Orden,
            p.Observaciones
        FROM EmpWebPedidosConStock p
        INNER JOIN EmpWebReservasPendientes r 
            ON p.NroCbt = r.NroCbt 
            AND p.CodArt = r.CodArt
            AND r.Estado = 'RESERVADO'
        WHERE p.codgrpemp = ? 
        AND p.DomEnv = ?
        AND NOT EXISTS (
            SELECT 1 
            FROM EmpWebEmpaqueDetalle ed
            INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
            WHERE ed.NroCbt = p.NroCbt 
            AND ed.CodArt = p.CodArt
            AND e.Estado IN ('EN_PROCESO', 'PALLETIZADO', 'COMPLETADO')
        )
        ORDER BY p.NroCbt, p.CodArt
    """, (codgrpemp, direccion))
    
    rows = cursor.fetchall()
    productos = []
    
    for row in rows:
        cantidad = float(row[3]) if row[3] else 0
        if cantidad > 0:
            productos.append({
                'pedido': row[0],
                'codart': row[1],
                'descripcion': row[2],
                'cantidad': cantidad,
                'orden': row[4] if row[4] else '',
                'observaciones': row[5] if row[5] else ''
            })
    
    conn.close()
    
    return jsonify({'success': True, 'productos': productos})

@empaques_bp.route('/empaques/crear', methods=['POST'])
@menu_required('/empaques')
def crear_empaque():
    """Crea un nuevo empaque (permite múltiples empaques por pedido)"""
    
    data = request.get_json()
    zona = data.get('zona', '')
    cliente = data.get('cliente')
    codgrpemp = data.get('codgrpemp')
    direccion = data.get('direccion')
    productos = data.get('productos', [])
    user_id = session.get('user_id')
    
    if not cliente or not direccion or not productos:
        return jsonify({'success': False, 'error': 'Faltan datos'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        productos_con_cantidad = []
        
        for prod in productos:
            pedido = prod['pedido']
            codart = prod['codart']
            
            # 1. Verificar que NO tenga empaque activo
            cursor.execute("""
                SELECT COUNT(*) 
                FROM EmpWebEmpaqueDetalle ed
                INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
                WHERE ed.NroCbt = ? AND ed.CodArt = ?
                AND e.Estado IN ('EN_PROCESO', 'PALLETIZADO', 'COMPLETADO')
            """, (pedido, codart))
            
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return jsonify({
                    'success': False, 
                    'error': f'El pedido {pedido} - {codart} ya tiene un empaque activo'
                })
            
            # 2. Verificar que NO tenga empaque COMPLETADO (para evitar duplicados)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM EmpWebEmpaqueDetalle ed
                INNER JOIN EmpWebEmpaques e ON ed.IdEmpaque = e.IdEmpaque
                WHERE ed.NroCbt = ? AND ed.CodArt = ?
                AND e.Estado IN ('EN_PROCESO', 'PALLETIZADO', 'COMPLETADO')
            """, (pedido, codart))

            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return jsonify({
                    'success': False, 
                    'error': f'El pedido {pedido} - {codart} ya tiene un empaque activo'
                })
                        
            # 3. Obtener la cantidad reservada
            cursor.execute("""
                SELECT CantidadReservada
                FROM EmpWebReservasPendientes
                WHERE NroCbt = ? AND CodArt = ? AND Estado = 'RESERVADO'
            """, (pedido, codart))
            
            row_reserva = cursor.fetchone()
            if not row_reserva:
                conn.rollback()
                return jsonify({'success': False, 'error': f'El pedido {pedido} - {codart} no tiene reserva activa'})
            
            total_reservado = float(row_reserva[0]) if row_reserva[0] else 0
            
            if total_reservado <= 0:
                conn.rollback()
                return jsonify({
                    'success': False, 
                    'error': f'El pedido {pedido} - {codart} no tiene cantidad reservada'
                })
            
            productos_con_cantidad.append({
                'pedido': pedido,
                'codart': codart,
                'cantidad': total_reservado
            })
        
        # Generar número correlativo
        fecha = datetime.now().strftime('%Y%m%d')
        prefijo = f'EMP-{fecha}-'
        
        cursor.execute("""
            SELECT MAX(CAST(REPLACE(NumeroEmpaque, ?, '') AS INT))
            FROM EmpWebEmpaques
            WHERE NumeroEmpaque LIKE ?
        """, (prefijo, prefijo + '%'))
        
        row_max = cursor.fetchone()
        ultimo_numero = row_max[0] if row_max and row_max[0] else 0
        nuevo_numero = ultimo_numero + 1
        numero_empaque = f'{prefijo}{nuevo_numero:03d}'
        
        cursor.execute("""
            INSERT INTO EmpWebEmpaques (NumeroEmpaque, Cliente, DireccionEnvio, UsuarioCreacion, Estado, ZonaEnvio)
            OUTPUT INSERTED.IdEmpaque
            VALUES (?, ?, ?, ?, 'EN_PROCESO', ?)
        """, (numero_empaque, cliente, direccion, user_id, zona))
        
        id_empaque = cursor.fetchone()[0]
        
        for prod in productos_con_cantidad:
            cursor.execute("""
                INSERT INTO EmpWebEmpaqueDetalle (IdEmpaque, NroCbt, CodArt, CantidadRequerida)
                VALUES (?, ?, ?, ?)
            """, (id_empaque, prod['pedido'], prod['codart'], prod['cantidad']))
        
        conn.commit()
        return jsonify({'success': True, 'id_empaque': id_empaque, 'numero': numero_empaque})
    
    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@empaques_bp.route('/empaques/detalle/<int:id_empaque>')
@menu_required('/empaques')
def detalle_empaque(id_empaque):
    """Obtiene el detalle completo de un empaque"""
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
            e.FechaCreacion,
            e.FechaPalletizado,
            e.Estado,
            u.NombreUsuario AS UsuarioCreacion
        FROM EmpWebEmpaques e
        LEFT JOIN EmpWebUsuarios u ON e.UsuarioCreacion = u.IdUsuario
        WHERE e.IdEmpaque = ?
    """, (id_empaque,))
    
    empaque_row = cursor.fetchone()
    if not empaque_row:
        conn.close()
        return jsonify({'error': 'Empaque no encontrado'}), 404
    
    empaque = {
        'id': empaque_row[0],
        'numero': empaque_row[1],
        'cliente': empaque_row[2],
        'direccion': empaque_row[3],
        'fecha_creacion': empaque_row[4].strftime('%d/%m/%Y %H:%M') if empaque_row[4] else '',
        'fecha_palletizado': empaque_row[5].strftime('%d/%m/%Y %H:%M') if empaque_row[5] else '',
        'estado': empaque_row[6],
        'usuario_creacion': empaque_row[7] if empaque_row[7] else ''
    }
    
    cursor.execute("""
        SELECT 
            ed.IdEmpaqueDetalle,
            ed.NroCbt AS Pedido,
            ed.CodArt,
            a.DesArt AS Descripcion,
            ed.CantidadRequerida,
            ed.CantidadPickeada,
            ed.CantidadRequerida - ed.CantidadPickeada AS CantidadPendiente,
            ed.Estado
        FROM EmpWebEmpaqueDetalle ed
        INNER JOIN Artic a ON ed.CodArt = a.CodArt
        WHERE ed.IdEmpaque = ?
        ORDER BY ed.CodArt
    """, (id_empaque,))
    
    detalles = []
    for row in cursor.fetchall():
        id_detalle = row[0]
        
        cursor.execute("""
            SELECT DISTINCT p.NumeroPallet
            FROM EmpWebPalletDetalle pd
            INNER JOIN EmpWebPalletEmpaque p ON pd.IdPallet = p.IdPallet
            WHERE pd.IdEmpaqueDetalle = ?
        """, (id_detalle,))
        
        pallets_rows = cursor.fetchall()
        pallets_list = [str(p[0]) for p in pallets_rows if p[0]]
        pallets_text = ', '.join(pallets_list) if pallets_list else ''
        
        cursor.execute("""
            SELECT pl.NroOF
            FROM EmpWebPickingLotes pl
            WHERE pl.IdEmpaqueDetalle = ?
        """, (id_detalle,))
        
        lotes_rows = cursor.fetchall()
        lotes_list = [str(l[0]) for l in lotes_rows if l[0]]
        lotes_text = ', '.join(lotes_list) if lotes_list else ''
        
        detalles.append({
            'id': id_detalle,
            'pedido': row[1],
            'codart': row[2],
            'descripcion': row[3],
            'requerido': float(row[4]) if row[4] else 0,
            'pickeado': float(row[5]) if row[5] else 0,
            'pendiente': float(row[6]) if row[6] else 0,
            'estado': row[7] if row[7] else 'PENDIENTE',
            'pallets': pallets_text,
            'lotes': lotes_text
        })
    
    conn.close()
    return jsonify({'success': True, 'empaque': empaque, 'detalles': detalles})

@empaques_bp.route('/empaques/listar')
@menu_required('/empaques')
def listar_empaques():
    """Lista todos los empaques para gestión"""
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
            e.FechaCreacion,
            u.NombreUsuario AS UsuarioCreacion,
            e.Estado,
            e.FechaPalletizado,
            (SELECT COUNT(*) FROM EmpWebEmpaqueDetalle WHERE IdEmpaque = e.IdEmpaque) AS TotalProductos,
            (SELECT COUNT(*) FROM EmpWebEmpaqueDetalle WHERE IdEmpaque = e.IdEmpaque AND Estado = 'COMPLETADO') AS ProductosCompletados
        FROM EmpWebEmpaques e
        LEFT JOIN EmpWebUsuarios u ON e.UsuarioCreacion = u.IdUsuario
        ORDER BY e.FechaCreacion DESC
    """)
    
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    
    empaques = []
    for row in rows:
        empaques.append(dict(zip(columns, row)))
    
    conn.close()
    return jsonify(empaques)