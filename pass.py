from werkzeug.security import check_password_hash

# Reemplaza con el hash que obtuviste de la BD
hash_bd = 'scrypt:32768:8:1$4CvuafuvOGJo5q2j$ffc120c0d73d53585b10273cf3f5209c170211cb6ed962a5b118f6c949ff8c3b6be9d92c5ed1e74aea004dc721101932865a2259133771d9e905da2241138344'  # Pega aquí tu hash real

password_prueba = 'admin'

if check_password_hash(hash_bd, password_prueba):
    print("✅ Contraseña correcta")
else:
    print("❌ Contraseña incorrecta")