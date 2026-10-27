# Importa tu aplicación Flask desde el archivo app.py
from app import app
from waitress import serve

if __name__ == '__main__':
    print("Iniciando servidor de producción Waitress...")
    # Aquí usas la configuración que quieras
    serve(app, host='0.0.0.0', port=5000, threads=4)