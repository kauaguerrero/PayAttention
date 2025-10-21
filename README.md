# PayAttention 💸

## 📝 Descrição

O PayAttention é um sistema de gerenciamento de finanças desenvolvido como um projeto para a faculdade de Sistemas de Informação. A plataforma ajuda os usuários a terem um controle claro e objetivo sobre suas receitas e despesas, facilitando o planejamento financeiro pessoal.

---

---

## ✨ Funcionalidades

- **Dashboard Intuitivo:** Visualização rápida do balanço mensal, últimas transações e gráficos.
- **Cadastro de Transações:** Permite registrar receitas e despesas de forma simples.
- **Categorização:** Organize suas transações por categorias (Ex: Alimentação, Transporte, Lazer).
- **Relatórios Visuais:** Gráficos que ajudam a entender para onde o dinheiro está indo.
---

## 🚀 Tecnologias Utilizadas

Este projeto foi construído utilizando as seguintes tecnologias:

- **Frontend:** HTML, CSS, FLASK
- **Backend:** Python
- **Banco de Dados:** SQLAlchemy

---

## ⚙️ Como Executar o Projeto

Siga os passos abaixo para rodar o projeto em seu ambiente local.

### Pré-requisitos

Antes de começar, você vai precisar ter instalado em sua máquina as seguintes ferramentas:
- [Git](https://git-scm.com)
- Tudo que estiver contido no requirements.txt
- Além de um editor de código como o [VSCode](https://code.visualstudio.com/)

## 🚀 Como Rodar o Projeto Localmente

1.  Clone o repositório:
    ```bash
    git clone [URL_DO_SEU_REPOSITORIO]
    cd PayAttention_FINAL
    ```

2.  Crie e ative um ambiente virtual:
    ```bash
    python -m venv venv
    source venv/bin/activate  # No Windows: venv\Scripts\activate
    ```

3.  Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Crie seu arquivo de ambiente:**
    Copie o arquivo de exemplo para criar seu arquivo `.env` local.
    ```bash
    # No Linux/macOS
    cp .env.example .env
    
    # No Windows (Prompt de Comando)
    copy .env.example .env
    ```

5.  Rode a aplicação:
    ```bash
    python app.py
    ```
