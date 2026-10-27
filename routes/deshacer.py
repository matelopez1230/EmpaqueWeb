from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime

deshacer_bp = Blueprint('deshacer', __name__)

@deshacer_bp.route('/deshacer-pickeo')
@menu_required('/deshacer-pickeo')
def index():
    """Página principal para deshacer pickeo"""
    return render_template('deshacer/index.html')

@deshacer_bp.route('/deshacer-pickeo/buscar')
@menu_required('/deshacer-pickeo')
def buscar_picks():
    """Busca picks para deshacer por empaque"""
    empaque = request.args.get('empaque', '')
    
    print(f"DEBUG - Buscando empaque: {empaque}")
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    # Primero, buscar el empaque por número
    cursor.execute("SELECT IdEmpaque, NumeroEmpaque FROM EmpWebEmpaques WHERE NumeroEmpaque = ?", (empaque,))
    empaque_row = cursor.fetchone()
    
    if not empaque_row:
        print(f"DEBUG - Empaque no encontrado: {empaque}")
        conn.close()
        return jsonify([])
    
    id_empaque = empaque_row[0]
    print(f"DEBUG - Empaque encontrado: ID={id_empaque}, Numero={empaque_row[1]}")
    
    # Buscar picks de ese empaque
    cursor.execute("""
        SELECT 
            pl.IdPicking,
            e.NumeroEmpaque,
            pl.NroOF,
            pl.CodArt,
            a.DesArt AS Descripcion,
            pl.CantidadPickeada,
            pl.FechaPick,
            u.NombreUsuario AS UsuarioPick,
            pl.IdEmpaque,
            pl.IdEmpaqueDetalle
        FROM EmpWebPickingLotes pl
        INNER JOIN EmpWebEmpaques e ON pl.IdEmpaque = e.IdEmpaque
        INNER JOIN Artic a ON pl.CodArt = a.CodArt
        LEFT JOIN EmpWebUsuarios u ON pl.UsuarioPick = u.IdUsuario
        WHERE pl.IdEmpaque = ?
        ORDER BY pl.FechaPick DESC
    """, (id_empaque,))
    
    rows = cursor.fetchall()
    print(f"DEBUG - Picks encontrados: {len(rows)}")
    
    picks = []
    for row in rows:
        picks.append({
            'id': row[0],
            'numero_empaque': row[1],
            'nro_of': row[2],
            'codart': row[3],
            'descripcion': row[4],
            'cantidad': float(row[5]) if row[5] else 0,
            'fecha_pick': row[6].strftime('%d/%m/%Y %H:%M') if row[6] else '',
            'usuario_pick': row[7] if row[7] else '',
            'id_empaque': row[8],
            'id_empaque_detalle': row[9]
        })
    
    conn.close()
    return jsonify(picks)

@deshacer_bp.route('/deshacer-pickeo/confirmar/<int:id_picking>', methods=['POST'])
@menu_required('/deshacer-pickeo')
def deshacer_pick(id_picking):
    """Deshace un pickeo específico"""
    data = request.get_json()
    motivo = data.get('motivo', '')
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Obtener información del pickeo
        cursor.execute("""
            SELECT IdEmpaque, IdEmpaqueDetalle, NroOF, CodArt, CantidadPickeada
            FROM EmpWebPickingLotes
            WHERE IdPicking = ?
        """, (id_picking,))
        
        pick = cursor.fetchone()
        if not pick:
            return jsonify({'success': False, 'error': 'Pickeo no encontrado'})
        
        id_empaque, id_detalle, nro_of, codart, cantidad = pick
        
        # 1. Registrar en historial
        cursor.execute("""
            INSERT INTO EmpWebPickingLotesHistorial (IdPickingOriginal, Usuario, FechaAccion, Accion, Motivo)
            VALUES (?, ?, GETDATE(), 'DESHACER', ?)
        """, (id_picking, user_id, motivo))
        
        # 2. Eliminar el registro de picking
        cursor.execute("DELETE FROM EmpWebPickingLotes WHERE IdPicking = ?", (id_picking,))
        
        # 3. Actualizar cantidad pickeada en detalle del empaque (restar)
        cursor.execute("""
            UPDATE EmpWebEmpaqueDetalle 
            SET CantidadPickeada = CantidadPickeada - ?,
                Estado = CASE 
                    WHEN CantidadRequerida <= CantidadPickeada - ? THEN 'COMPLETADO'
                    WHEN CantidadPickeada - ? > 0 THEN 'PARCIAL'
                    ELSE 'PENDIENTE'
                END
            WHERE IdEmpaqueDetalle = ?
        """, (cantidad, cantidad, cantidad, id_detalle))
        
        # 4. IMPORTANTE: Resetear el estado del pallet a PENDIENTE (no controlado)
        cursor.execute("""
            UPDATE EmpWebPalletEmpaque
            SET ControlEstado = 'PENDIENTE'
            WHERE IdPallet IN (SELECT IdPallet FROM EmpWebPalletDetalle WHERE IdEmpaqueDetalle = ?)
        """, (id_detalle,))
        
        # 5. Resetear el control completado del empaque
        cursor.execute("""
            UPDATE EmpWebEmpaques 
            SET ControlCompletado = 0,
                Estado = 'EN_PROCESO'
            WHERE IdEmpaque = ?
        """, (id_empaque,))
        
        # 6. Eliminar registros de control de pallet asociados
        cursor.execute("""
            DELETE FROM EmpWebControlPalletDetalle
            WHERE IdControl IN (SELECT IdControl FROM EmpWebControlPallet WHERE IdPallet IN 
                (SELECT IdPallet FROM EmpWebPalletDetalle WHERE IdEmpaqueDetalle = ?))
        """, (id_detalle,))
        
        cursor.execute("""
            DELETE FROM EmpWebControlPallet
            WHERE IdPallet IN (SELECT IdPallet FROM EmpWebPalletDetalle WHERE IdEmpaqueDetalle = ?)
        """, (id_detalle,))
        
        conn.commit()
        
        return jsonify({'success': True, 'mensaje': f'Pickeo deshecho. El pallet ahora está pendiente de control.'})
    
    except Exception as e:
        conn.rollback()
        print(f"DEBUG - Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()