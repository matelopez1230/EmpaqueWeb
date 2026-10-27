from werkzeug.security import generate_password_hash, check_password_hash

# Crear hash
password = "Nati2026"
hash_password = generate_password_hash(password)

print(hash_password)