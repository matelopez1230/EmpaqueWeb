import pyodbc

def get_db_connection():
    try:
        conn = pyodbc.connect(
            'DRIVER={SQL Server};'
            'SERVER=192.168.8.5\\TSSQL;'   # Doble backslash por la barra invertida
            'DATABASE=GestionWeb;'
            'UID=sa;'
            'PWD=;'                         # Si no hay contraseña, así se deja
        )
        return conn
    except Exception as e:
        print("Error al conectar a la base de datos:", e)
        return None