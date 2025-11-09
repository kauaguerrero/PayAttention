import os
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'chave-super-secreta-para-dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DATABASE_URL = os.getenv('DATABASE_URL')

    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///' + os.path.join(BASE_DIR, 'dados_financeiros.db')

    DEBUG = os.getenv('FLASK_ENV') == 'development'