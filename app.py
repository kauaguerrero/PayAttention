from flask import Flask, render_template, request, redirect, url_for, flash, session
from static.database.config import Config
from static.database.models import db, Transacao, Usuario, hash_senha, verificar_senha, Meta
from sqlalchemy import func
from functools import wraps
from datetime import datetime
from decimal import Decimal
import csv
import io
import re
import pdfplumber

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = 'sua_chave_secreta_aqui'
db.init_app(app)


# Funções Auxiliares

def buscar_transacao(id_transacao, id_usuario):
    return Transacao.query.filter_by(id_transacao=id_transacao, id_usuario=id_usuario).first()

def extrair_beneficiario(descricao_completa):
    # (Sua função continua a mesma, sem alterações)
    try:
        partes = descricao_completa.split(' - ')
        if len(partes) > 1:
            beneficiario = partes[1].split(' - ')[0].strip()
            if 'Agência:' in beneficiario or 'Conta:' in beneficiario:
                return partes[0]
            return beneficiario
        return descricao_completa.split(',')[0]
    except:
        return descricao_completa


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'id_usuario' not in session:
            flash("Você precisa estar logado para acessar esta página.", "error")
            return redirect(url_for('fazer_login'))
        return f(*args, **kwargs)

    return decorated_function


def calcular_saldo(usuario_id):
    saldos = db.session.query(
        func.sum(Transacao.valor).filter(Transacao.tipo == 'receita', Transacao.id_usuario == usuario_id).label(
            'total_receita'),
        func.sum(Transacao.valor).filter(Transacao.tipo == 'despesa', Transacao.id_usuario == usuario_id).label(
            'total_despesa')
    ).first()
    entrada_total = saldos.total_receita or Decimal(0)
    saida_total = saldos.total_despesa or Decimal(0)
    saldo = entrada_total - saida_total
    return saldo, entrada_total, saida_total


# --- CLASSE DE EXTRAÇÃO DE PDF ---

class ExtratorPDFSemIA:
    # (Sua classe continua a mesma, sem alterações)
    def __init__(self):
        self.padroes_data = [r'\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b', r'\b(\d{2})[/\-.](\d{2})[/\-.](\d{2})\b',
                             r'\b(\d{4})[/\-.](\d{2})[/\-.](\d{2})\b']
        self.padroes_valor = [r'R?\$?\s*(-?\d{1,3}(?:\.\d{3})*,\d{2})', r'(-?\d{1,3}(?:\.\d{3})*,\d{2})',
                              r'(-?\d+,\d{2})']
        self.palavras_despesa = ['débito', 'debito', 'pagamento', 'compra', 'saque', 'tarifa', 'taxa', 'anuidade',
                                 'iof', 'juros', 'transferência enviada', 'pix enviado', 'ted enviada']
        self.palavras_receita = ['crédito', 'credito', 'depósito', 'deposito', 'salário', 'salario', 'recebimento',
                                 'transferência recebida', 'pix recebido', 'ted recebida', 'rendimento']
        self.palavras_ignorar = ['saldo', 'saldo anterior', 'saldo atual', 'total', 'lançamentos futuros', 'página',
                                 'extrato', 'período', 'agência', 'conta', 'titular', 'cpf', 'cnpj']

    def extrair_texto_pdf(self, arquivo_pdf):
        linhas = []
        with pdfplumber.open(arquivo_pdf) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text();
                if texto: linhas.extend(texto.split('\n'))
        return linhas

    def limpar_valor(self, valor_str):
        valor_str = valor_str.replace('R$', '').replace(' ', '').strip();
        negativo = valor_str.startswith('-');
        valor_str = valor_str.lstrip('-');
        valor_str = valor_str.replace('.', '').replace(',', '.')
        try:
            valor = float(valor_str); return -valor if negativo else valor
        except:
            return 0.0

    def extrair_data(self, texto):
        for padrao in self.padroes_data:
            match = re.search(padrao, texto)
            if match:
                grupos = match.groups()
                if len(grupos[0]) == 2:
                    dia, mes, ano = grupos;
                    if len(ano) == 2: ano = '20' + ano
                    try:
                        data = datetime(int(ano), int(mes), int(dia)); return data.strftime('%Y-%m-%d')
                    except:
                        pass
                elif len(grupos[0]) == 4:
                    ano, mes, dia = grupos
                    try:
                        data = datetime(int(ano), int(mes), int(dia)); return data.strftime('%Y-%m-%d')
                    except:
                        pass
        return datetime.now().strftime('%Y-%m-%d')

    def extrair_valor(self, texto):
        for padrao in self.padroes_valor:
            match = re.search(padrao, texto)
            if match: return self.limpar_valor(match.group(1))
        return 0.0

    def identificar_tipo(self, texto, valor):
        texto_lower = texto.lower();
        if valor < 0: return 'despesa'
        for palavra in self.palavras_despesa:
            if palavra in texto_lower: return 'despesa'
        for palavra in self.palavras_receita:
            if palavra in texto_lower: return 'receita'
        return 'receita' if valor > 0 else 'despesa'

    def deve_ignorar(self, texto):
        texto_lower = texto.lower();
        if len(texto.strip()) < 10: return True
        for palavra in self.palavras_ignorar:
            if palavra in texto_lower: return True
        return False

    def extrair_descricao(self, texto, valor_str):
        descricao = texto
        for padrao in self.padroes_data: descricao = re.sub(padrao, '', descricao)
        descricao = descricao.replace(valor_str, '');
        descricao = re.sub(r'R?\$?\s*-?\d+[\.,]\d+', '', descricao);
        descricao = ' '.join(descricao.split())
        return descricao.strip() or "Transação"

    def extrair_transacoes(self, arquivo_pdf):
        linhas = self.extrair_texto_pdf(arquivo_pdf);
        transacoes = []
        for linha in linhas:
            if not linha.strip() or self.deve_ignorar(linha): continue
            valor = self.extrair_valor(linha)
            if valor == 0.0: continue
            data = self.extrair_data(linha);
            tipo = self.identificar_tipo(linha, valor);
            valor_final = abs(valor);
            descricao = self.extrair_descricao(linha, str(valor))
            beneficiario = descricao.split('-')[0].strip()[:100]
            if not beneficiario: beneficiario = "Não informado"
            transacao = {'data': data, 'descricao': descricao[:255], 'valor': valor_final, 'tipo': tipo,
                         'beneficiario': beneficiario}
            transacoes.append(transacao)
        return transacoes


# --- FUNÇÕES DE PROCESSAMENTO DE FICHEIROS ---

def processar_pdf(arquivo, usuario_id):
    try:
        extrator = ExtratorPDFSemIA()
        transacoes_extraidas = extrator.extrair_transacoes(arquivo)

        if not transacoes_extraidas:
            flash('Nenhuma transação encontrada no PDF.', 'warning')
            # CORREÇÃO: Apontar para o endpoint correto
            return redirect(url_for('importar_extrato'))

        saldo_atual, _, _ = calcular_saldo(usuario_id)
        novas_transacoes = [];
        recusadas = 0

        for t in transacoes_extraidas:
            valor = Decimal(str(t['valor']));
            tipo = t['tipo']
            if tipo == 'despesa':
                if valor > saldo_atual: recusadas += 1; continue
                saldo_atual -= valor
            else:
                saldo_atual += valor
            try:
                data_transacao = datetime.strptime(t['data'], '%Y-%m-%d').date()
            except:
                data_transacao = datetime.now().date()
            nova_transacao = Transacao(descricao=t['descricao'], valor=valor, tipo=tipo, beneficiario=t['beneficiario'],
                                       id_usuario=usuario_id, data=data_transacao, categoria='Outros')
            novas_transacoes.append(nova_transacao)

        if novas_transacoes:
            db.session.add_all(novas_transacoes);
            db.session.commit()
            flash(f'{len(novas_transacoes)} transações importadas!', 'success')
        if recusadas > 0:
            flash(f'{recusadas} despesas ignoradas por saldo insuficiente.', 'warning')
        return redirect(url_for('listar_transacoes'))

    except Exception as e:
        db.session.rollback();
        flash(f'Erro ao processar PDF: {str(e)}', 'danger')
        print(f"Erro no processamento de PDF: {e}")
        # CORREÇÃO: Apontar para o endpoint correto
        return redirect(url_for('importar_extrato'))


def processar_csv(arquivo, usuario_id):
    try:
        stream = io.StringIO(arquivo.stream.read().decode("UTF-8"), newline=None)
        csv_reader = csv.DictReader(stream)
        novas_transacoes = [];
        recusadas = 0
        saldo_atual, _, _ = calcular_saldo(usuario_id)

        for row in csv_reader:
            valor_str = row.get('Valor', '0').strip()
            valor_num = Decimal(valor_str)
            tipo = 'receita' if valor_num > 0 else 'despesa'
            valor_final = abs(valor_num)

            if tipo == "despesa":
                if valor_final > saldo_atual: recusadas += 1; continue
                saldo_atual -= valor_final
            else:
                saldo_atual += valor_final

            data_str = row.get('Data', '')
            data_transacao = datetime.strptime(data_str, '%d/%m/%Y').date() if data_str else datetime.utcnow().date()
            nova_transacao = Transacao(descricao=row.get('Descrição', 'Não informado'), valor=valor_final, tipo=tipo,
                                       beneficiario=extrair_beneficiario(row.get('Descrição', '')),
                                       id_usuario=usuario_id, data=data_transacao)
            novas_transacoes.append(nova_transacao)

        if novas_transacoes:
            db.session.add_all(novas_transacoes);
            db.session.commit()
            flash(f'{len(novas_transacoes)} transações importadas com sucesso!', 'success')
        if recusadas > 0:
            flash(f'{recusadas} despesas ignoradas por saldo insuficiente.', 'warning')
        return redirect(url_for("listar_transacoes"))
    except Exception as e:
        db.session.rollback();
        print(f"Erro ao processar CSV: {e}")
        flash(f'Ocorreu um erro ao processar o ficheiro CSV: {e}', 'danger')
        return redirect(url_for("importar_extrato"))


# --- ROTA UNIFICADA DE IMPORTAÇÃO (O "DISPATCHER") ---

@app.route('/importar-extrato', methods=['GET', 'POST'])
@login_required
def importar_extrato():
    if request.method == 'POST':
        if 'arquivo_extrato' not in request.files or not request.files['arquivo_extrato'].filename:
            flash('Nenhum ficheiro selecionado!', 'danger');
            return redirect(request.url)

        arquivo = request.files['arquivo_extrato']
        filename = arquivo.filename.lower()
        usuario_id = session['id_usuario']

        if filename.endswith('.csv'):
            return processar_csv(arquivo, usuario_id)
        elif filename.endswith('.pdf'):
            return processar_pdf(arquivo, usuario_id)
        else:
            flash('Formato não suportado. Use CSV ou PDF.', 'warning')
            return redirect(request.url)

    return render_template('importar_extrato.html')  # A página de upload


@app.route("/apagar_todas", methods=["POST"])
@login_required
def apagar_todas_transacoes():
    usuario_id = session['id_usuario']
    try:
        Transacao.query.filter_by(id_usuario=usuario_id).delete()
        db.session.commit()
        flash("Todas as suas transações foram excluídas com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao apagar todas as transações: {e}")
        flash("Ocorreu um erro ao tentar excluir as transações.", "danger")
    return redirect(url_for('listar_transacoes'))

@app.route("/")
@app.route("/dashboard")
@login_required
def listar_transacoes():
    usuario_id = session['id_usuario'];
    hoje = datetime.now()
    saldo, entrada_total, saida_total = calcular_saldo(usuario_id)
    meta_salva = Meta.query.filter_by(id_usuario=usuario_id, mes=hoje.month, ano=hoje.year).first()
    meta_investimento = meta_salva.valor if meta_salva else Decimal('0.00')
    total_investido_query = db.session.query(func.sum(Transacao.valor)).filter(Transacao.id_usuario == usuario_id,
                                                                               Transacao.tipo == 'despesa',
                                                                               Transacao.categoria.ilike(
                                                                                   'Investimento'),
                                                                               func.extract('month',
                                                                                            Transacao.data) == hoje.month,
                                                                               func.extract('year',
                                                                                            Transacao.data) == hoje.year).scalar()
    total_investido = total_investido_query or Decimal('0.00')
    todas_transacoes = Transacao.query.filter_by(id_usuario=usuario_id).order_by(Transacao.data.desc()).all()
    transacoes_dict = [t.to_dict() for t in todas_transacoes]
    return render_template("dashboard.html", transacoes=transacoes_dict, saldo=float(saldo),
                           entrada_total=float(entrada_total), saida_total=float(saida_total),
                           meta_investimento=float(meta_investimento), total_investido=float(total_investido))


# (Todas as outras rotas: login, logout, cadastrar_usuario, perfil, transações, meta, etc., continuam aqui)
# ...
@app.route("/login", methods=["GET", "POST"])
def fazer_login():
    if 'id_usuario' in session: return redirect(url_for("listar_transacoes"))
    if request.method == "POST":
        email = request.form.get("email");
        senha_str = request.form.get("senha")
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and verificar_senha(senha_str, usuario.senha):
            session['id_usuario'] = usuario.id_usuario;
            session['nome_usuario'] = usuario.nome.split()[0]
            flash(f"Bem-vindo(a), {session['nome_usuario']}!", "success");
            return redirect(url_for("listar_transacoes"))
        else:
            flash("E-mail ou senha inválidos.", "error"); return redirect(url_for("fazer_login"))
    return render_template("login.html")


@app.route("/logout")
def fazer_logout():
    session.pop('id_usuario', None);
    session.pop('nome_usuario', None)
    flash("Você saiu da sua conta com sucesso.", "success");
    return redirect(url_for("fazer_login"))


@app.route("/cadastrar_usuario", methods=["GET", "POST"])
def cadastrar_usuario():
    if 'id_usuario' in session: return redirect(url_for("listar_transacoes"))
    if request.method == "POST":
        nome, email, senha_str = request.form.get("nome"), request.form.get("email"), request.form.get("senha")
        if not nome or not email or len(senha_str) < 7: flash(
            "Preencha todos os campos e use uma senha com no mínimo 7 caracteres.", "error"); return redirect(
            url_for("cadastrar_usuario"))
        if Usuario.query.filter_by(email=email).first(): flash("Este e-mail já está cadastrado.",
                                                               "error"); return redirect(url_for("cadastrar_usuario"))
        senha_hashed = hash_senha(senha_str)
        novo_usuario = Usuario(nome=nome, email=email, senha=senha_hashed)
        try:
            db.session.add(novo_usuario);
            db.session.commit()
            session['id_usuario'] = novo_usuario.id_usuario;
            session['nome_usuario'] = novo_usuario.nome.split()[0]
            flash("Cadastro realizado com sucesso!", "success");
            return redirect(url_for("listar_transacoes"))
        except Exception as e:
            db.session.rollback(); print(f"Erro de DB: {e}"); flash("Ocorreu um erro ao salvar o usuário.",
                                                                    "error"); return redirect(
                url_for("cadastrar_usuario"))
    return render_template("cadastro_usuario.html")


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def gerenciar_perfil():
    usuario = Usuario.query.get(session['id_usuario'])
    if request.method == "POST":
        novo_nome, novo_email = request.form.get("nome"), request.form.get("email")
        senha_atual_str, nova_senha_str = request.form.get("senha_atual"), request.form.get("nova_senha")
        if not usuario: flash("Erro: Usuário não encontrado.", "error"); return redirect(url_for("listar_transacoes"))
        if not senha_atual_str or not verificar_senha(senha_atual_str, usuario.senha): flash("Senha atual incorreta.",
                                                                                             "error"); return redirect(
            url_for("gerenciar_perfil"))
        alteracao_feita = False
        if novo_nome and novo_nome != usuario.nome: usuario.nome = novo_nome; session['nome_usuario'] = \
        novo_nome.split()[0]; alteracao_feita = True
        if novo_email and novo_email != usuario.email:
            if Usuario.query.filter(Usuario.email == novo_email,
                                    Usuario.id_usuario != session['id_usuario']).first(): flash(
                "Este e-mail já está sendo usado por outra conta.", "error"); return redirect(
                url_for("gerenciar_perfil"))
            usuario.email = novo_email;
            alteracao_feita = True
        if nova_senha_str:
            if len(nova_senha_str) < 7: flash("A nova senha deve ter no mínimo 7 caracteres.",
                                              "error"); return redirect(url_for("gerenciar_perfil"))
            usuario.senha = hash_senha(nova_senha_str);
            alteracao_feita = True
        if alteracao_feita:
            try:
                db.session.commit(); flash("Seus dados de perfil foram atualizados com sucesso!", "success")
            except Exception as e:
                db.session.rollback(); print(f"Erro de DB ao atualizar perfil: {e}"); flash(
                    "Ocorreu um erro ao salvar as alterações.", "error")
        else:
            flash("Nenhuma alteração foi detectada ou salva.", "info")
        return redirect(url_for("gerenciar_perfil"))
    return render_template("perfil.html", usuario=usuario)


@app.route("/cadastrar_transacao", methods=["GET", "POST"])
@login_required
def cadastrar_transacao():
    if request.method == "GET": return render_template("cadastro_transacao.html")
    usuario_id = session['id_usuario']
    try:
        descricao, valor, tipo = request.form["descricao"], Decimal(request.form["valor"]), request.form[
            "type"].strip().lower()
        beneficiario, categoria = request.form.get("beneficiario", "N/A"), request.form.get("categoria", "Outros")
    except ValueError:
        flash("Valor inválido.", "error"); return redirect(url_for("cadastrar_transacao"))
    saldo_atual, _, _ = calcular_saldo(usuario_id)
    if tipo == "despesa" and valor > saldo_atual: flash(f"Despesa de R$ {valor:.2f} excede o saldo.",
                                                        "error"); return redirect(url_for("cadastrar_transacao"))
    nova_transacao = Transacao(descricao=descricao, valor=valor, tipo=tipo, beneficiario=beneficiario,
                               id_usuario=usuario_id, categoria=categoria)
    try:
        db.session.add(nova_transacao); db.session.commit(); flash("Transação cadastrada!", "success"); return redirect(
            url_for("listar_transacoes"))
    except Exception as e:
        db.session.rollback(); print(f"Erro ao salvar: {e}"); flash("Erro ao cadastrar.", "error"); return redirect(
            url_for("cadastrar_transacao"))


@app.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_transacao(id):
    transacao_db = buscar_transacao(id, session['id_usuario'])
    if not transacao_db: flash("Transação não encontrada.", "error"); return redirect(url_for("listar_transacoes"))
    if request.method == "POST":
        transacao_db.descricao = request.form["descricao"];
        transacao_db.valor = Decimal(request.form["valor"]);
        transacao_db.tipo = request.form["type"].strip().lower()
        transacao_db.beneficiario = request.form.get("beneficiario", "N/A");
        transacao_db.categoria = request.form.get("categoria", "Outros")
        db.session.commit();
        flash("Transação editada com sucesso!", "success");
        return redirect(url_for("listar_transacoes"))
    return render_template("editar.html", transacao=transacao_db.to_dict())


@app.route("/apagar/<int:id>", methods=["POST"])
@login_required
def apagar_transacao(id):
    transacao_db = buscar_transacao(id, session['id_usuario'])
    if transacao_db:
        db.session.delete(transacao_db); db.session.commit(); flash("Transação excluída.", "success")
    else:
        flash("Transação não encontrada.", "error")
    return redirect(url_for("listar_transacoes"))


@app.route("/meta", methods=["GET", "POST"])
@login_required
def gerenciar_meta():
    usuario_id = session['id_usuario'];
    hoje = datetime.utcnow()
    meta_atual = Meta.query.filter_by(id_usuario=usuario_id, mes=hoje.month, ano=hoje.year).first()
    if request.method == "POST":
        try:
            novo_valor_meta = Decimal(request.form['meta'])
        except (ValueError, KeyError):
            flash("Valor de meta inválido.", "error"); return redirect(url_for('gerenciar_meta'))
        if meta_atual:
            meta_atual.valor = novo_valor_meta; flash("Meta atualizada!", "success")
        else:
            nova_meta = Meta(valor=novo_valor_meta, mes=hoje.month, ano=hoje.year,
                             id_usuario=usuario_id); db.session.add(nova_meta); flash("Meta definida!", "success")
        db.session.commit();
        return redirect(url_for('listar_transacoes'))
    valor_meta_existente = meta_atual.valor if meta_atual else Decimal('0.00')
    return render_template("definir_meta.html", meta_atual=valor_meta_existente)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
