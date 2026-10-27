import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-para-desarrollo'
    # Puedes agregar más configuraciones si lo deseas