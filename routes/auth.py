from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify

from werkzeug.security import check_password_hash
from db import get_db_connection
import pyodbc

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if not conn:
            flash('Error de conexión a la base de datos')
            return render_template('login.html')
        
        cursor = conn.cursor()
        # Buscar usuario activo
        cursor.execute("SELECT IdUsuario, NombreUsuario, PasswordHash FROM EmpWebUsuarios WHERE NombreUsuario = ? AND Activo = 1", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            
            # Cargar menús permitidos para este usuario
            menus = obtener_menus_usuario(user[0])
            session['menus'] = menus  # lista de diccionarios
            
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos')
    
    return render_template('login.html')

@auth_bp.route('/cambiar-password', methods=['POST'])
def cambiar_password():
    """Cambia la contraseña del usuario logueado"""
    data = request.get_json()
    password_actual = data.get('password_actual', '')
    password_nueva = data.get('password_nueva', '')
    user_id = session.get('user_id')
    
    if not password_actual or not password_nueva:
        return jsonify({'success': False, 'error': 'Complete todos los campos'})
    
    if len(password_nueva) < 4:
        return jsonify({'success': False, 'error': 'La nueva contraseña debe tener al menos 4 caracteres'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Error de conexión'})
    
    cursor = conn.cursor()
    
    try:
        from werkzeug.security import check_password_hash, generate_password_hash
        
        cursor.execute("SELECT PasswordHash FROM EmpWebUsuarios WHERE IdUsuario = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'})
        
        if not check_password_hash(row[0], password_actual):
            return jsonify({'success': False, 'error': 'Contraseña actual incorrecta'})
        
        nuevo_hash = generate_password_hash(password_nueva)
        cursor.execute("UPDATE EmpWebUsuarios SET PasswordHash = ? WHERE IdUsuario = ?", (nuevo_hash, user_id))
        
        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Contraseña cambiada exitosamente'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

def obtener_menus_usuario(id_usuario):
    print(f"\n=== DEBUG menus: id_usuario={id_usuario} ===")
    
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.NombreMenu, m.Url, m.Icono, m.Orden, m.Grupo
        FROM EmpWebMenus m
        INNER JOIN EmpWebPermisosUsuario pu ON m.IdMenu = pu.IdMenu
        WHERE pu.IdUsuario = ? AND m.Activo = 1
        ORDER BY m.Orden
    """, (id_usuario,))
    rows = cursor.fetchall()
    conn.close()
    menus = []
    for row in rows:
        menus.append({
            'nombre': row[0],
            'url': row[1],
            'icono': row[2],
            'orden': row[3],
            'grupo': row[4] or 'LOGISTICA'
        })
    print(f"=== Menús desde SQL Server: {len(menus)} ===")

    # ─── Inyección temporal ───
    try:
        from maintenance.pdf_generator.permisos import usuario_tiene_permiso
        tiene = usuario_tiene_permiso(id_usuario)
        print(f"=== ¿Tiene permiso en SQLite?: {tiene} ===")
        if tiene:
            menus.append({
                'nombre': 'Especificaciones PDF',
                'url':    '/especificaciones-pdf/',
                'icono':  'fas fa-file-pdf',
                'orden':  100,
                'grupo':  'LOGISTICA',
            })
            print(f"=== ✅ Menú 'Especificaciones PDF' agregado ===")
        else:
            print(f"=== ❌ Usuario {id_usuario} NO tiene el permiso 11 en SQLite ===")
    except Exception as e:
        print(f"[WARN] No se pudo inyectar menú Especificaciones PDF: {e}")
        import traceback
        traceback.print_exc()

    print(f"=== Total menús finales: {len(menus)} ===")
    return menus