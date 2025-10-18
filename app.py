from flask import Flask, render_template, request, redirect, url_for, flash, session
from static.database.config import Config
from static.database.models import db, Transacao, Usuario, hash_senha, verificar_senha, Meta
from sqlalchemy import func
from functools import wraps
from decimal import Decimal, InvalidOperation
import csv
import io
from datetime import datetime
import pandas as pd
import tabula
import traceback

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = 'sua_chave_secreta_aqui'
db.init_app(app)


def extrair_beneficiario(descricao_completa):
    try:
        partes = descricao_completa.split(' - ')
        if len(partes) > 1:
            beneficiario = partes[1].split(' - ')[0].strip()
            if 'Agência:' in beneficiario or 'Conta:' in beneficiario: return partes[0]
            return beneficiario
        return descricao_completa.split(',')[0]
    except:
        return descricao_completa


@app.route('/importar', methods=['GET', 'POST'])
def importar_transacoes():
    usuario_logado_id = session['id_usuario']
    if request.method == 'POST':
        if 'arquivo_transacoes' not in request.files or not request.files['arquivo_transacoes'].filename:
            flash('Nenhum arquivo selecionado!', 'danger')
            return redirect(request.url)

        arquivo = request.files['arquivo_transacoes']
        filename = arquivo.filename.lower()

        if not (filename.endswith('.csv') or filename.endswith('.pdf')):
            flash('Formato de arquivo inválido. Por favor, envie um arquivo .csv ou .pdf', 'warning')
            return redirect(request.url)

        try:
            novas_transacoes = []
            transacoes_recusadas = 0
            saldo_atual, _, _ = calcular_saldo(usuario_logado_id)

            if filename.endswith('.csv'):
                # --- LÓGICA ORIGINAL PARA CSV SIMPLES RESTAURADA ---
                stream = io.StringIO(arquivo.stream.read().decode("UTF-8"), newline=None)
                csv_reader = csv.DictReader(stream)  # Delimitador padrão: vírgula

                for row in csv_reader:
                    valor_str = row.get('Valor', '0').strip()
                    descricao_completa = row.get('Descrição', 'Não informado')
                    data_str = row.get('Data', '')

                    if not valor_str or not data_str: continue

                    valor_num = Decimal(valor_str)
                    data_transacao = datetime.strptime(data_str, '%d/%m/%Y').date()

                    if valor_num > 0:
                        tipo = 'receita'
                        valor_final = valor_num
                    else:
                        tipo = 'despesa'
                        valor_final = abs(valor_num)

                    if tipo == "despesa":
                        if valor_final > saldo_atual:
                            transacoes_recusadas += 1
                            continue
                        else:
                            saldo_atual -= valor_final
                    else:
                        saldo_atual += valor_final

                    novas_transacoes.append(Transacao(
                        descricao=descricao_completa, valor=valor_final, tipo=tipo,
                        beneficiario=extrair_beneficiario(descricao_completa),
                        id_usuario=usuario_logado_id, data=data_transacao
                    ))

            elif filename.endswith('.pdf'):
                # --- LÓGICA PERSONALIZADA PARA O PDF DO BRADESCO ---
                lista_de_tabelas = tabula.read_pdf(
                    arquivo, pages='all', stream=True, guess=False,
                    encoding='latin-1', pandas_options={'header': None, 'dtype': str}
                )

                if not lista_de_tabelas:
                    flash('Nenhuma tabela encontrada no arquivo PDF.', 'warning')
                    return redirect(url_for("listar_transacoes"))

                df = pd.concat(lista_de_tabelas, ignore_index=True)

                for i in range(0, len(df) - 1, 2):
                    try:
                        linha_desc, linha_dados = df.iloc[i], df.iloc[i + 1]
                        descricao_principal = str(linha_desc[0]) if pd.notna(linha_desc[0]) else ''
                        data_str, credito_str, debito_str = str(linha_dados[0]).split(' ')[0], str(linha_dados[1]), str(
                            linha_dados[2])

                        datetime.strptime(data_str, '%d/%m/%Y')
                        valor_final, tipo = None, None

                        try:
                            valor_credito = Decimal(credito_str.replace('.', '').replace(',', '.').strip())
                            if valor_credito > 0: valor_final, tipo = valor_credito, 'receita'
                        except (InvalidOperation, TypeError, ValueError):
                            pass

                        if tipo is None:
                            try:
                                valor_debito = Decimal(debito_str.replace('.', '').replace(',', '.').strip())
                                if valor_debito > 0: valor_final, tipo = valor_debito, 'despesa'
                            except (InvalidOperation, TypeError, ValueError):
                                pass

                        if tipo is None: continue

                        if tipo == "despesa":
                            if valor_final > saldo_atual:
                                transacoes_recusadas += 1; continue
                            else:
                                saldo_atual -= valor_final
                        else:
                            saldo_atual += valor_final

                        novas_transacoes.append(Transacao(
                            descricao=descricao_principal, valor=valor_final, tipo=tipo,
                            beneficiario=extrair_beneficiario(descricao_principal),
                            id_usuario=usuario_logado_id, data=datetime.strptime(data_str, '%d/%m/%Y').date()
                        ))
                    except (ValueError, IndexError):
                        continue

            if novas_transacoes:
                db.session.add_all(novas_transacoes)
                db.session.commit()
                flash(f'{len(novas_transacoes)} transações importadas com sucesso!', 'success')
            else:
                flash('Nenhuma nova transação válida foi encontrada no arquivo.', 'info')

            if transacoes_recusadas > 0:
                flash(f'{transacoes_recusadas} despesas foram ignoradas por saldo insuficiente.', 'warning')

            return redirect(url_for("listar_transacoes"))

        except Exception as e:
            db.session.rollback()
            print("Ocorreu um erro detalhado:")
            traceback.print_exc()
            flash(f'Ocorreu um erro ao processar o arquivo. Verifique o formato. Erro: {e}', 'danger')
            return redirect(request.url)

    return render_template('importar.html')


# (O resto do seu código, de login_required em diante, permanece igual)
# ...
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
            'total_despesa')).first()
    entrada_total = saldos.total_receita or Decimal(0)
    saida_total = saldos.total_despesa or Decimal(0)
    saldo = entrada_total - saida_total
    return saldo, entrada_total, saida_total


@app.route("/login", methods=["GET", "POST"])
def fazer_login():
    if 'id_usuario' in session: return redirect(url_for("listar_transacoes"))
    if request.method == "GET": return render_template("login.html")
    email = request.form.get("email")
    senha_str = request.form.get("senha")
    if not email or not senha_str: flash("Por favor, preencha E-mail e Senha.", "error"); return redirect(
        url_for("fazer_login"))
    usuario = Usuario.query.filter_by(email=email).first()
    if usuario and verificar_senha(senha_str, usuario.senha):
        session['id_usuario'] = usuario.id_usuario
        session['nome_usuario'] = usuario.nome.split()[0]
        flash(f"Bem-vindo(a), {session['nome_usuario']}!", "success")
        return redirect(url_for("listar_transacoes"))
    else:
        flash("E-mail ou senha inválidos.", "error"); return redirect(url_for("fazer_login"))


@app.route("/logout")
def fazer_logout():
    session.pop('id_usuario', None);
    session.pop('nome_usuario', None)
    flash("Você saiu da sua conta com sucesso.", "success")
    return redirect(url_for("fazer_login"))


@app.route("/cadastrar_usuario", methods=["GET", "POST"])
def cadastrar_usuario():
    if 'id_usuario' in session: return redirect(url_for("listar_transacoes"))
    if request.method == "GET": return render_template("cadastro_usuario.html")
    nome = request.form.get("nome")
    email = request.form.get("email")
    senha_str = request.form.get("senha")
    if not nome or not email or len(senha_str) < 7: flash(
        "Preencha todos os campos e use uma senha com no mínimo 7 caracteres.", "error"); return redirect(
        url_for("cadastrar_usuario"))
    if Usuario.query.filter_by(email=email).first(): flash("Este e-mail já está cadastrado.", "error"); return redirect(
        url_for("cadastrar_usuario"))
    senha_hashed = hash_senha(senha_str)
    novo_usuario = Usuario(nome=nome, email=email, senha=senha_hashed)
    try:
        db.session.add(novo_usuario);
        db.session.commit()
        session['id_usuario'] = novo_usuario.id_usuario
        session['nome_usuario'] = novo_usuario.nome.split()[0]
        flash("Cadastro realizado com sucesso! Você já pode gerenciar suas finanças.", "success")
        return redirect(url_for("listar_transacoes"))
    except Exception as e:
        db.session.rollback()
        print(f"Erro de DB: {e}")
        flash("Ocorreu um erro ao salvar o usuário.", "error")
        return redirect(url_for("cadastrar_usuario"))


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def gerenciar_perfil():
    usuario_logado_id = session['id_usuario']
    usuario = Usuario.query.get(usuario_logado_id)
    if request.method == "GET":
        return render_template("perfil.html", usuario=usuario)
    elif request.method == "POST":
        novo_nome = request.form.get("nome")
        novo_email = request.form.get("email")
        senha_atual_str = request.form.get("senha_atual")
        nova_senha_str = request.form.get("nova_senha")
        if not usuario: flash("Erro: Usuário não encontrado.", "error"); return redirect(url_for("listar_transacoes"))
        if not senha_atual_str or not verificar_senha(senha_atual_str, usuario.senha): flash(
            "Senha atual incorreta. Nenhuma alteração foi salva.", "error"); return redirect(
            url_for("gerenciar_perfil"))
        alteracao_feita = False
        if novo_nome and novo_nome != usuario.nome:
            usuario.nome = novo_nome;
            session['nome_usuario'] = novo_nome.split()[0];
            alteracao_feita = True
        if novo_email and novo_email != usuario.email:
            if Usuario.query.filter(Usuario.email == novo_email,
                                    Usuario.id_usuario != usuario_logado_id).first(): flash(
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
                db.session.commit()
                flash("Seus dados de perfil foram atualizados com sucesso!", "success")
            except Exception as e:
                db.session.rollback()
                print(f"Erro de DB ao atualizar perfil: {e}")
                flash("Ocorreu um erro ao salvar as alterações.", "error")
        else:
            flash("Nenhuma alteração foi detectada ou salva.", "info")
        return redirect(url_for("gerenciar_perfil"))


@app.route("/cadastrar_transacao", methods=["GET", "POST"])
@login_required
def cadastrar_transacao():
    if request.method == "GET": return render_template("cadastro_transacao.html")
    usuario_logado_id = session['id_usuario']
    try:
        descricao = request.form["descricao"];
        valor = Decimal(request.form["valor"]);
        tipo = request.form["type"].strip().lower();
        beneficiario = request.form.get("beneficiario", "N/A");
        categoria = request.form.get("categoria", "Outros")
    except ValueError:
        flash("Valor inválido. Certifique-se de que o campo 'Valor' seja um número.", "error"); return redirect(
            url_for("cadastrar_transacao"))
    saldo_atual, _, _ = calcular_saldo(usuario_logado_id)
    if tipo == "despesa":
        if valor > saldo_atual: flash(
            f"Despesa de R$ {valor:.2f} excede o saldo atual de R$ {saldo_atual:.2f}. Saldo insuficiente.",
            "error"); return redirect(url_for("cadastrar_transacao"))
    if tipo not in ["receita", "despesa"]: flash("Tipo de transação inválido. Use 'Receita' ou 'Despesa'.",
                                                 "error"); return redirect(url_for("cadastrar_transacao"))
    nova_transacao = Transacao(descricao=descricao, valor=valor, tipo=tipo, beneficiario=beneficiario,
                               id_usuario=usuario_logado_id, categoria=categoria)
    try:
        db.session.add(nova_transacao);
        db.session.commit()
        flash("Transação cadastrada com sucesso!", "success")
        return redirect(url_for("listar_transacoes"))
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao salvar transação: {e}")
        flash("Ocorreu um erro ao cadastrar a transação.", "error")
        return redirect(url_for("cadastrar_transacao"))


@app.route("/dashboard")
@login_required
def listar_transacoes():
    usuario_id = session['id_usuario']
    hoje = datetime.now()
    saldo, entrada_total, saida_total = calcular_saldo(usuario_id)
    meta_salva = Meta.query.filter_by(id_usuario=usuario_id, mes=hoje.month, ano=hoje.year).first()
    meta_investimento = meta_salva.valor if meta_salva else Decimal('0.00')
    total_investido_query = db.session.query(func.sum(Transacao.valor)).filter(Transacao.id_usuario == usuario_id,
                                                                               Transacao.tipo == 'receita',
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


def buscar_transacao_por_cod(id, id_usuario): return Transacao.query.filter_by(id_transacao=id,
                                                                               id_usuario=id_usuario).first()


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


@app.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_transacao(id):
    usuario_id = session['id_usuario']
    transacao_db = buscar_transacao_por_cod(id, usuario_id)
    if transacao_db and transacao_db.id_usuario == usuario_id:
        if request.method == "POST":
            saldo_atual, _, _ = calcular_saldo(usuario_id)
            valor_antigo_db = transacao_db.valor or Decimal(0)
            valor_antigo_para_subtrair = valor_antigo_db if transacao_db.tipo == 'despesa' else Decimal(0)
            saldo_temporario = saldo_atual + valor_antigo_para_subtrair
            try:
                novo_valor = Decimal(request.form["valor"]);
                novo_tipo = request.form["type"].strip().lower()
            except ValueError:
                flash("Valor inválido. Certifique-se de que o campo 'Valor' seja um número.", "error"); return redirect(
                    url_for("editar_transacao", id=id))
            if novo_tipo == "despesa" and novo_valor > saldo_temporario: flash(
                f"Despesa de R$ {novo_valor:.2f} excede o saldo disponível de R$ {saldo_temporario:.2f} após a edição. Saldo insuficiente.",
                "error"); return redirect(url_for("editar_transacao", id=id))
            transacao_db.descricao = request.form["descricao"];
            transacao_db.valor = novo_valor;
            transacao_db.tipo = novo_tipo;
            transacao_db.beneficiario = request.form.get("beneficiario", "N/A");
            transacao_db.categoria = request.form.get("categoria", "Outros")
            db.session.commit()
            flash("Transação editada com sucesso!", "success")
            return redirect(url_for("listar_transacoes"))
        transacao_dict = transacao_db.to_dict()
        return render_template("editar.html", transacao=transacao_dict)
    else:
        flash("Transação não encontrada ou você não tem permissão para editá-la.", "error"); return redirect(
            url_for("listar_transacoes"))


@app.route("/apagar/<int:id>", methods=["POST"])
@login_required
def apagar_transacao(id):
    usuario_id = session['id_usuario']
    transacao_db = buscar_transacao_por_cod(id, usuario_id)
    if transacao_db and transacao_db.id_usuario == usuario_id:
        db.session.delete(transacao_db);
        db.session.commit()
        flash("Transação excluída com sucesso.", "success")
    else:
        flash("Transação não encontrada ou você não tem permissão para excluí-la.", "error")
    return redirect(url_for("listar_transacoes"))


@app.route("/meta", methods=["GET", "POST"])
@login_required
def gerenciar_meta():
    usuario_id = session['id_usuario']
    hoje = datetime.utcnow()
    meta_atual = Meta.query.filter_by(id_usuario=usuario_id, mes=hoje.month, ano=hoje.year).first()
    if request.method == "POST":
        try:
            novo_valor_meta = Decimal(request.form['meta'])
        except (ValueError, KeyError):
            flash("Valor de meta inválido.", "error"); return redirect(url_for('gerenciar_meta'))
        if meta_atual:
            meta_atual.valor = novo_valor_meta;
            flash("Sua meta mensal foi atualizada com sucesso!", "success")
        else:
            nova_meta = Meta(valor=novo_valor_meta, mes=hoje.month, ano=hoje.year, id_usuario=usuario_id)
            db.session.add(nova_meta)
            flash("Sua meta mensal foi definida com sucesso!", "success")
        db.session.commit()
        return redirect(url_for('listar_transacoes'))
    valor_meta_existente = meta_atual.valor if meta_atual else Decimal('0.00')
    return render_template("definir_meta.html", meta_atual=valor_meta_existente)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)