# test_login.py — Diagnóstico completo del login
import db
from werkzeug.security import check_password_hash

# ─── Configurá acá el usuario y contraseña que estás probando ───
USUARIO_INGRESADO = "admin"          # ← CAMBIÁ por el que usás
PASSWORD_INGRESADO = "adminMapsa2026**"      # ← CAMBIÁ por el que usás
# ────────────────────────────────────────────────────────────────

print("=" * 70)
print("DIAGNÓSTICO DE LOGIN")
print("=" * 70)

# 1) Conexión
print("\n[1] Probando conexión...")
conn = db.get_db_connection()
if not conn:
    print("   ❌ FALLA — get_db_connection() devolvió None")
    print("   → Mirá arriba el mensaje 'Error al conectar...' para saber por qué")
    exit(1)
print("   ✅ Conexión OK")

# 2) Info del servidor y DB
cur = conn.cursor()
cur.execute("SELECT DB_NAME(), SUSER_NAME(), @@SERVERNAME")
db_name, user_name, srv_name = cur.fetchone()
print(f"   → Base de datos: {db_name}")
print(f"   → Usuario SQL:   {user_name}")
print(f"   → Servidor:      {srv_name}")

# 3) Contar usuarios
cur.execute("SELECT COUNT(*) FROM EmpWebUsuarios")
total = cur.fetchone()[0]
print(f"\n[2] Usuarios en EmpWebUsuarios: {total}")

# 4) Buscar el usuario exacto que ingresaste
print(f"\n[3] Buscando usuario '{USUARIO_INGRESADO}'...")
cur.execute("""
    SELECT IdUsuario, NombreUsuario, PasswordHash, Activo
    FROM EmpWebUsuarios
    WHERE NombreUsuario = ?
""", (USUARIO_INGRESADO,))
row = cur.fetchone()

if not row:
    print(f"   ❌ NO EXISTE el usuario '{USUARIO_INGRESADO}' en la DB")
    print(f"   → Listado completo de usuarios existentes:")
    cur.execute("SELECT IdUsuario, NombreUsuario, Activo FROM EmpWebUsuarios ORDER BY IdUsuario")
    for r in cur.fetchall():
        print(f"      ID={r[0]}  Usuario='{r[1]}'  Activo={r[2]}")
    conn.close()
    exit(1)

id_u, nombre_db, hash_pwd, activo = row
print(f"   ✅ Encontrado: ID={id_u}, Nombre='{nombre_db}', Activo={activo}")
print(f"   → Hash (primeros 40 chars): {(hash_pwd or '(VACÍO)')[:40]}")
print(f"   → Longitud del hash: {len(hash_pwd) if hash_pwd else 0}")

# 5) Chequear Activo
print(f"\n[4] Verificando estado Activo...")
if activo != 1:
    print(f"   ❌ El usuario tiene Activo={activo} (debería ser 1)")
    print(f"   → SQL para arreglar: UPDATE EmpWebUsuarios SET Activo=1 WHERE IdUsuario={id_u}")
else:
    print(f"   ✅ Activo=1")

# 6) Verificar el hash
print(f"\n[5] Verificando contraseña '{PASSWORD_INGRESADO}' contra el hash...")
try:
    resultado = check_password_hash(hash_pwd, PASSWORD_INGRESADO)
    if resultado:
        print(f"   ✅ LA CONTRASEÑA ES CORRECTA")
    else:
        print(f"   ❌ check_password_hash devolvió FALSE")
        print(f"   → La contraseña que probás no coincide con el hash guardado")
        print(f"   → O el hash no es un hash válido de Werkzeug")
except Exception as e:
    print(f"   ❌ check_password_hash tiró EXCEPCIÓN: {e}")
    print(f"   → El campo PasswordHash probablemente NO es un hash de Werkzeug")
    print(f"   → Valor actual: {hash_pwd[:80] if hash_pwd else '(vacío)'}")

# 7) Detectar tipo de hash
print(f"\n[6] Tipo de hash detectado:")
if not hash_pwd:
    print(f"   (vacío)")
elif hash_pwd.startswith("scrypt:"):
    print(f"   ✅ scrypt (Werkzeug moderno)")
elif hash_pwd.startswith("pbkdf2:"):
    print(f"   ✅ pbkdf2 (Werkzeug clásico, compatible)")
elif hash_pwd.startswith("sha256$") or hash_pwd.startswith("sha1$"):
    print(f"   ⚠️  hash viejo de Werkzeug (formato 'algo$salt$hash')")
elif len(hash_pwd) < 30:
    print(f"   ❌ MUY CORTO — probablemente TEXTO PLANO: '{hash_pwd}'")
else:
    print(f"   ⚠️  Formato desconocido: {hash_pwd[:50]}...")

conn.close()
print("\n" + "=" * 70)