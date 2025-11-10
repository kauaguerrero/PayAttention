import os
from dotenv import load_dotenv

if not os.getenv('POSTGRES_HOST'):
    from dotenv import load_dotenv
    load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'chave-super-secreta-para-dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    pg_user = os.getenv('POSTGRES_USER')
    pg_pass = os.getenv('POSTGRES_PASSWORD')
    pg_host = os.getenv('POSTGRES_HOST')
    pg_port = os.getenv('POSTGRES_PORT')
    pg_db = os.getenv('POSTGRES_DB')

    if all([pg_user, pg_pass, pg_host, pg_port, pg_db]):
        SQLALCHEMY_DATABASE_URI = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'dados_financeiros.db')