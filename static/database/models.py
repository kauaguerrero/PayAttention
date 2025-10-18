from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Numeric
from datetime import datetime
import bcrypt

def hash_senha(senha: str) -> str:
    senha_hashed = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt(rounds=12))
    return senha_hashed.decode()

def verificar_senha(senha_str: str, senha_hashed: str) -> bool:
    senha_hashed_validation = bcrypt.checkpw(senha_str.encode('utf-8'), senha_hashed.encode())
    return senha_hashed_validation

db = SQLAlchemy()

class Usuario(db.Model):
    __tablename__ = "usuarios"
    id_usuario = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    senha = db.Column(db.String(255), nullable=False)

    def to_dict(self):
        return {
            'id_usuario': self.id_usuario,
            'nome': self.nome,
            'email': self.email,
        }

    def __repr__(self):
        return f"<Usuário {self.nome}: {self.email}>"

class Transacao(db.Model):
    __tablename__ = "transacoes"
    id_transacao = db.Column(db.Integer, primary_key=True, autoincrement=True)
    descricao = db.Column(db.String(255))
    valor = db.Column(Numeric(10, 2), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    beneficiario = db.Column(db.String(100))
    data = db.Column(db.DateTime, default=datetime.now(), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    usuario = db.relationship('Usuario', backref='transacoes')
    categoria = db.Column(db.String(50), nullable=True, default='Outros')

    def to_dict(self):
        return {
            'id': self.id_transacao,
            'tipo': self.tipo,
            'valor': float(self.valor),
            'descricao': self.descricao,
            'beneficiario': self.beneficiario,
            'data': self.data.isoformat(),
            'categoria': self.categoria,
        }

    def __repr__(self):
        return f"<Transacao {self.tipo}: R$ {self.valor} ({self.data})>"

class Meta(db.Model):
    __tablename__ = 'metas'
    id_meta = db.Column(db.Integer, primary_key=True)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    ano = db.Column(db.Integer, nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)

    def __repr__(self):
        return f"<Meta {self.id_usuario} - {self.mes}/{self.ano}: R${self.valor}>"