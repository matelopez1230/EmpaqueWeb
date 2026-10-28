import os
from dotenv import load_dotenv

load_dotenv()  # ← carga el .env

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-para-desarrollo'
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024