from flask import Blueprint, render_template, request, jsonify, session
from routes.decorators import menu_required
from db import get_db_connection
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

usuarios_bp = Blueprint('usuarios', __name__)

@usuarios_bp.route('/usuarios')
@menu_required('/usuarios')
def index():
    return render_template('usuarios/index.html')

@usuarios_bp.route('/usuarios/listar')
@menu_required('/usuarios')
def listar():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT IdUsuario, NombreUsuario, Activo, FechaAlta
        FROM EmpWebUsuarios
        ORDER BY IdUsuario
    """)
    
    rows = cursor.fetchall()
    usuarios = []
    for row in rows:
        usuarios.append({
            'id': row[0],
            'nombre': row[1],
            'activo': row[2],
            'fecha_alta': row[3].strftime('%d/%m/%Y %H:%M') if row[3] else ''
        })
    
    conn.close()
    return jsonify(usuarios)

@usuarios_bp.route('/usuarios/detalle/<int:id_usuario>')
@menu_required('/usuarios')
def detalle(id_usuario):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Error de conexión'}), 500
    
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT IdUsuario, NombreUsuario, Activo, FechaAlta
        FROM EmpWebUsuarios
        WHERE IdUsuario = ?
    """, (id_usuario,))
    
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    usuario = {
        'id': user_row[0],
        'nombre': user_row[1],
        'activo': user_row[2],
        'fecha_alta': user_row[3].strftime('%d/%m/%Y %H:%M') if user_row[3] else ''
    }
    
    # Menús asignados
    cursor.execute("""
        SELECT m.IdMenu, m.NombreMenu, m.Url, m.Icono
        FROM EmpWebPermisosUsuario p
        INNER JOIN EmpWebMenus m ON p.IdMenu = m.IdMenu
        WHERE p.IdUsuario = ? AND m.Activo = 1
        ORDER BY m.Orden
    """, (id_usuario,))
    
    menus_asignados = []
    for row in cursor.fetchall():
        menus_asignados.append({
            'id': row[0],
            'nombre': row[1],
            'url': row[2],
            'icono': row[3]
        })
    
    # Todos los menús disponibles
    cursor.execute("""
        SELECT IdMenu, NombreMenu, Url, Icono, Orden
        FROM EmpWebMenus
        WHERE Activo = 1
        ORDER BY Orden
    """)
    
    menus_disponibles = []
    for row in cursor.fetchall():
        menus_disponibles.append({
            'id': row[0],
            'nombre': row[1],
            'url': row[2],
            'icono': row[3],
            'orden': row[4]
        })
    
    conn.close()
    return jsonify({
        'usuario': usuario,
        'menus_asignados': menus_asignados,
        'menus_disponibles': menus_disponibles
    })

@usuarios_bp.route('/usuarios/crear', methods=['POST'])
@menu_required('/usuarios')
def crear():
    data = request.get_json()
    nombre = data.get('nombre', '').strip()
    password = data.get('password', '')
    activo = data.get('activo', True)
    
    if not nombre:
        return jsonify({'success': False, 'error': 'El nombre de usuario es requerido'})
    
    if not password:
        return jsonify({'success': False, 'error': 'La contraseña es requerida'})
    
    if len(password) < 4:
        return jsonify({'success': False, 'error': 'La contraseña debe tener al menos 4 caracteres'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM EmpWebUsuarios WHERE NombreUsuario = ?", (nombre,))
        if cursor.fetchone()[0] > 0:
            return jsonify({'success': False, 'error': 'El nombre de usuario ya existe'})
        
        # Usar generate_password_hash de werkzeug
        password_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO EmpWebUsuarios (NombreUsuario, PasswordHash, Activo, FechaAlta)
            OUTPUT INSERTED.IdUsuario
            VALUES (?, ?, ?, GETDATE())
        """, (nombre, password_hash, 1 if activo else 0))
        
        id_usuario = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({'success': True, 'id': id_usuario, 'mensaje': f'Usuario {nombre} creado exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@usuarios_bp.route('/usuarios/editar/<int:id_usuario>', methods=['POST'])
@menu_required('/usuarios')
def editar(id_usuario):
    data = request.get_json()
    nombre = data.get('nombre', '').strip()
    activo = data.get('activo', True)
    
    if not nombre:
        return jsonify({'success': False, 'error': 'El nombre de usuario es requerido'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM EmpWebUsuarios WHERE NombreUsuario = ? AND IdUsuario != ?", (nombre, id_usuario))
        if cursor.fetchone()[0] > 0:
            return jsonify({'success': False, 'error': 'El nombre de usuario ya existe'})
        
        cursor.execute("""
            UPDATE EmpWebUsuarios
            SET NombreUsuario = ?, Activo = ?
            WHERE IdUsuario = ?
        """, (nombre, 1 if activo else 0, id_usuario))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': f'Usuario actualizado exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@usuarios_bp.route('/usuarios/cambiar-password/<int:id_usuario>', methods=['POST'])
@menu_required('/usuarios')
def cambiar_password(id_usuario):
    data = request.get_json()
    password = data.get('password', '')
    
    if not password:
        return jsonify({'success': False, 'error': 'La contraseña es requerida'})
    
    if len(password) < 4:
        return jsonify({'success': False, 'error': 'La contraseña debe tener al menos 4 caracteres'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        # Usar generate_password_hash de werkzeug
        password_hash = generate_password_hash(password)
        cursor.execute("""
            UPDATE EmpWebUsuarios
            SET PasswordHash = ?
            WHERE IdUsuario = ?
        """, (password_hash, id_usuario))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Contraseña actualizada exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@usuarios_bp.route('/usuarios/eliminar/<int:id_usuario>', methods=['DELETE'])
@menu_required('/usuarios')
def eliminar(id_usuario):
    usuario_actual = session.get('user_id')
    
    if id_usuario == usuario_actual:
        return jsonify({'success': False, 'error': 'No puede eliminar su propio usuario'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM EmpWebPermisosUsuario WHERE IdUsuario = ?", (id_usuario,))
        cursor.execute("DELETE FROM EmpWebUsuarios WHERE IdUsuario = ?", (id_usuario,))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Usuario eliminado exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@usuarios_bp.route('/usuarios/asignar-menu', methods=['POST'])
@menu_required('/usuarios')
def asignar_menu():
    data = request.get_json()
    id_usuario = data.get('id_usuario')
    id_menu = data.get('id_menu')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM EmpWebPermisosUsuario
            WHERE IdUsuario = ? AND IdMenu = ?
        """, (id_usuario, id_menu))
        
        if cursor.fetchone()[0] > 0:
            return jsonify({'success': False, 'error': 'El menú ya está asignado a este usuario'})
        
        cursor.execute("""
            INSERT INTO EmpWebPermisosUsuario (IdUsuario, IdMenu)
            VALUES (?, ?)
        """, (id_usuario, id_menu))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Menú asignado exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@usuarios_bp.route('/usuarios/quitar-menu', methods=['POST'])
@menu_required('/usuarios')
def quitar_menu():
    data = request.get_json()
    id_usuario = data.get('id_usuario')
    id_menu = data.get('id_menu')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM EmpWebPermisosUsuario
            WHERE IdUsuario = ? AND IdMenu = ?
        """, (id_usuario, id_menu))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Menú removido exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()