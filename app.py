# app.py - SISTEMA COMPLETO LIVRO CAIXA COM USUARIOS EXPANDIDOS
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
import io
import base64
import os
import zipfile
import hashlib
import calendar
import shutil
from dateutil.relativedelta import relativedelta
import pymysql
from pymysql import Error
from PIL import Image
import requests
from io import BytesIO

# Configuração da página
st.set_page_config(
    page_title="Livro Caixa",
    page_icon="📒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CONSTANTES
PERMISSOES = {
    'admin': 'Administrador',
    'editor': 'Editor',
    'visualizador': 'Apenas Visualização'
}

# =============================================================================
# FUNÇÃO PARA CARREGAR IMAGEM DO LOGO
# =============================================================================
def carregar_imagem_logo(nome_arquivo):
    """Carrega a imagem do logo com múltiplas tentativas de caminho"""
    caminhos_tentativos = [
        nome_arquivo,
        f"./{nome_arquivo}",
        f"imagens/{nome_arquivo}",
        f"./imagens/{nome_arquivo}"
    ]

    for caminho in caminhos_tentativos:
        if os.path.exists(caminho):
            return caminho

    return None

# =============================================================================
# CONEXÃO COM PLANETSCALE
# =============================================================================
def get_db_connection():
    """Cria conexão com o PlanetScale usando PyMySQL"""
    try:
        if "planetscale" not in st.secrets:
            st.error("❌ Secrets do PlanetScale não encontrados")
            return None

        secrets = st.secrets["planetscale"]

        # Verificar campos obrigatórios
        required_fields = ["host", "user", "password", "database"]
        for field in required_fields:
            if field not in secrets or not secrets[field]:
                st.error(f"❌ Campo '{field}' não encontrado ou vazio")
                return None

        # Tentar conexão
        connection = pymysql.connect(
            host=secrets["host"],
            user=secrets["user"],
            password=secrets["password"],
            database=secrets["database"],
            ssl={'ca': '/etc/ssl/certs/ca-certificates.crt'},
            connect_timeout=10
        )

        return connection

    except pymysql.MySQLError as e:
        error_code = e.args[0] if len(e.args) > 0 else None
        if error_code == 1045:
            st.error("❌ Erro 1045: Acesso negado. Verifique usuário e senha.")
        elif error_code == 1044:
            st.error("❌ Erro 1044: Acesso negado ao banco de dados.")
        elif error_code == 2003:
            st.error("❌ Erro 2003: Não foi possível conectar ao servidor.")
        else:
            st.error(f"❌ Erro MySQL {error_code}: {e}")
        return None
    except Exception as e:
        st.error(f"❌ Erro de conexão: {e}")
        return None

# =============================================================================
# FUNÇÕES DE AUTENTICAÇÃO E TABELA USUARIOS (COM EXPANSÃO DE CAMPOS)
# =============================================================================

def init_auth_db():
    """
    Inicializa a tabela de usuarios (cria se não existir) e aplica ALTER TABLE
    para adicionar os novos campos opcionais quando necessário.
    """
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        # Criar tabela base (compatível com instalações novas)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                permissao VARCHAR(20) NOT NULL DEFAULT 'visualizador',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ADICIONAR CAMPOS OPCIONAIS - cada coluna é opcional (NULL)
        alter_statements = [
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nome_completo VARCHAR(200)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefone VARCHAR(50)",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS endereco TEXT",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS data_aniversario DATE",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS data_iniciacao DATE",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS data_elevacao DATE",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS data_exaltacao DATE",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS data_instalacao_posse DATE",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS observacoes TEXT",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS redes_sociais VARCHAR(500)"
        ]

        for stmt in alter_statements:
            try:
                cursor.execute(stmt)
            except Exception:
                # Em ambientes onde IF NOT EXISTS não é suportado, ignorar falhas
                pass

        # Inserir usuários padrão se não existirem
        cursor.execute('SELECT COUNT(*) FROM usuarios WHERE username = "admin"')
        if cursor.fetchone()[0] == 0:
            # Senha padrão: "admin123" (hash SHA256)
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cursor.execute(
                'INSERT INTO usuarios (username, password_hash, permissao) VALUES (%s, %s, %s)',
                ('admin', password_hash, 'admin')
            )

            password_hash_viewer = hashlib.sha256('visual123'.encode()).hexdigest()
            cursor.execute(
                'INSERT INTO usuarios (username, password_hash, permissao) VALUES (%s, %s, %s)',
                ('visual', password_hash_viewer, 'visualizador')
            )

        conn.commit()
    except Error as e:
        st.error(f"❌ Erro ao inicializar banco de autenticação: {e}")
    finally:
        if conn:
            conn.close()

def login_user(username, password):
    """Autentica usuário"""
    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        cursor = conn.cursor()
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        cursor.execute(
            'SELECT username, permissao FROM usuarios WHERE username = %s AND password_hash = %s',
            (username, password_hash)
        )

        result = cursor.fetchone()
        if result:
            return True, result
        else:
            return False, "Usuário ou senha incorretos"
    except Error as e:
        return False, f"Erro de banco: {e}"
    finally:
        if conn:
            conn.close()

def logout_user():
    """Faz logout do usuário"""
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.permissao = None

def user_is_admin():
    """Verifica se usuário é admin"""
    return st.session_state.permissao == 'admin'

def user_can_edit():
    """Verifica se usuário pode editar (admin ou editor)"""
    return st.session_state.permissao in ['admin', 'editor']

# =============================================================================
# FUNÇÕES DE CRIAÇÃO/LEITURA/ATUALIZAÇÃO/EXCLUSÃO DE USUÁRIOS (CRUD)
# =============================================================================

def criar_usuario(username, password, permissao, email=None,
                  nome_completo=None, telefone=None, endereco=None,
                  data_aniversario=None, data_iniciacao=None, data_elevacao=None,
                  data_exaltacao=None, data_instalacao_posse=None,
                  observacoes=None, redes_sociais=None):
    """Cria um novo usuário no sistema com os campos adicionais (apenas admin)"""
    if not user_is_admin():
        return False, "Apenas administradores podem criar usuários"

    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão com o banco"

    try:
        cursor = conn.cursor()

        # Verificar duplicidade por username ou email (se informado)
        if email:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE username = %s OR email = %s', (username, email))
        else:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE username = %s', (username,))
        if cursor.fetchone()[0] > 0:
            return False, "Usuário ou e-mail já existe"

        # Validar permissão
        if permissao not in PERMISSOES:
            return False, "Permissão inválida"

        # Criar hash da senha
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Inserir novo usuário incluindo os campos adicionais (NULL se não informados)
        cursor.execute('''
            INSERT INTO usuarios (
                username, email, password_hash, permissao,
                nome_completo, telefone, endereco,
                data_aniversario, data_iniciacao, data_elevacao,
                data_exaltacao, data_instalacao_posse, observacoes, redes_sociais
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            username, email, password_hash, permissao,
            nome_completo, telefone, endereco,
            data_aniversario, data_iniciacao, data_elevacao,
            data_exaltacao, data_instalacao_posse, observacoes, redes_sociais
        ))

        conn.commit()
        return True, f"Usuário '{username}' criado com sucesso!"

    except Error as e:
        return False, f"Erro ao criar usuário: {e}"
    finally:
        if conn:
            conn.close()

def get_all_users():
    """Busca todos os usuários (apenas admin) com campos expandidos"""
    if not user_is_admin():
        return []

    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, email, permissao, created_at,
                   nome_completo, telefone, endereco,
                   data_aniversario, data_iniciacao, data_elevacao,
                   data_exaltacao, data_instalacao_posse, observacoes, redes_sociais
            FROM usuarios
            ORDER BY created_at
        ''')
        return cursor.fetchall()
    except Error:
        return []
    finally:
        if conn:
            conn.close()

def update_user_permission(username, nova_permissao):
    """Atualiza permissão do usuário"""
    if not user_is_admin():
        return False, "Apenas administradores podem atualizar permissões"

    # Validar permissão
    if nova_permissao not in PERMISSOES:
        return False, "Permissão inválida"

    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE usuarios SET permissao = %s WHERE username = %s',
            (nova_permissao, username)
        )
        conn.commit()
        return True, "Permissão atualizada com sucesso"
    except Error as e:
        return False, f"Erro ao atualizar: {e}"
    finally:
        if conn:
            conn.close()

def delete_user(username):
    """Exclui usuário (apenas admin, sem permitir auto-exclusão)"""
    if not user_is_admin():
        return False, "Apenas administradores podem excluir usuários"

    if username == st.session_state.username:
        return False, "Você não pode excluir seu próprio usuário"

    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM usuarios WHERE username = %s', (username,))
        conn.commit()
        return True, "Usuário excluído com sucesso"
    except Error as e:
        return False, f"Erro ao excluir: {e}"
    finally:
        if conn:
            conn.close()

def change_password(username, new_password):
    """Altera senha do usuário"""
    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        cursor = conn.cursor()
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        cursor.execute(
            'UPDATE usuarios SET password_hash = %s WHERE username = %s',
            (password_hash, username)
        )
        conn.commit()
        return True, "Senha alterada com sucesso"
    except Error as e:
        return False, f"Erro ao alterar senha: {e}"
    finally:
        if conn:
            conn.close()

# =============================================================================
# FUNÇÕES PRINCIPAIS (LANCAMENTOS, CONTAS, EVENTOS...)
# =============================================================================

def init_db():
    """Inicializa as demais tabelas do sistema"""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        # Tabela de lançamentos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lancamentos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                mes VARCHAR(20) NOT NULL,
                data DATE NOT NULL,
                historico TEXT NOT NULL,
                complemento TEXT,
                entrada DECIMAL(15,2) DEFAULT 0.00,
                saida DECIMAL(15,2) DEFAULT 0.00,
                saldo DECIMAL(15,2) DEFAULT 0.00,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de contas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nome VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de eventos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS eventos_calendario (
                id INT AUTO_INCREMENT PRIMARY KEY,
                titulo VARCHAR(200) NOT NULL,
                descricao TEXT,
                data_evento DATE NOT NULL,
                hora_evento TIME,
                tipo_evento VARCHAR(50),
                cor_evento VARCHAR(20),
                created_by VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
    except Error as e:
        st.error(f"❌ Erro ao criar tabelas: {e}")
    finally:
        if conn:
            conn.close()

def get_contas():
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT nome FROM contas ORDER BY nome')
        return [row[0] for row in cursor.fetchall()]
    except Error:
        return []
    finally:
        if conn:
            conn.close()

def adicionar_conta(nome_conta):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO contas (nome) VALUES (%s)', (nome_conta,))
        conn.commit()
        st.success(f"✅ Conta '{nome_conta}' adicionada com sucesso!")
        return True
    except Error as e:
        st.error(f"❌ Erro ao adicionar conta: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_lancamentos_mes(mes):
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    try:
        query = 'SELECT * FROM lancamentos WHERE mes = %s ORDER BY data, id'
        df = pd.read_sql(query, conn, params=[mes])
        return df
    except Exception as e:
        st.error(f"Erro ao buscar lançamentos: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def salvar_lancamento(mes, data, historico, complemento, entrada, saida, saldo):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO lancamentos (mes, data, historico, complemento, entrada, saida, saldo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (mes, data, historico, complemento, entrada, saida, saldo))
        conn.commit()
        st.success("✅ Lançamento salvo com sucesso!")
        return True
    except Error as e:
        st.error(f"❌ Erro ao salvar lançamento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def atualizar_lancamento(lancamento_id, mes, data, historico, complemento, entrada, saida):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM lancamentos WHERE id = %s', (lancamento_id,))
        lancamento_antigo = cursor.fetchone()
        if not lancamento_antigo:
            st.error("❌ Lançamento não encontrado")
            return False
        cursor.execute('''
            UPDATE lancamentos 
            SET data = %s, historico = %s, complemento = %s, entrada = %s, saida = %s
            WHERE id = %s
        ''', (data, historico, complemento, entrada, saida, lancamento_id))
        cursor.execute('SELECT * FROM lancamentos WHERE mes = %s ORDER BY data, id', (mes,))
        lancamentos = cursor.fetchall()
        saldo_atual = 0.0
        for lanc in lancamentos:
            entrada_val = float(lanc[5]) if lanc[5] else 0.0
            saida_val = float(lanc[6]) if lanc[6] else 0.0
            saldo_atual += entrada_val - saida_val
            cursor.execute('UPDATE lancamentos SET saldo = %s WHERE id = %s', (saldo_atual, lanc[0]))
        conn.commit()
        return True
    except Error as e:
        st.error(f"❌ Erro ao atualizar lançamento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def excluir_lancamento(lancamento_id, mes):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM lancamentos WHERE id = %s', (lancamento_id,))
        cursor.execute('SELECT * FROM lancamentos WHERE mes = %s ORDER BY data, id', (mes,))
        lancamentos = cursor.fetchall()
        saldo_atual = 0.0
        for lanc in lancamentos:
            entrada_val = float(lanc[5]) if lanc[5] else 0.0
            saida_val = float(lanc[6]) if lanc[6] else 0.0
            saldo_atual += entrada_val - saida_val
            cursor.execute('UPDATE lancamentos SET saldo = %s WHERE id = %s', (saldo_atual, lanc[0]))
        conn.commit()
        return True
    except Error as e:
        st.error(f"❌ Erro ao excluir: {e}")
        return False
    finally:
        if conn:
            conn.close()

def limpar_lancamentos_mes(mes):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM lancamentos WHERE mes = %s', (mes,))
        conn.commit()
        st.success(f"✅ Todos os lançamentos de {mes} foram excluídos!")
        return True
    except Error as e:
        st.error(f"❌ Erro ao limpar lançamentos: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_eventos_mes(ano, mes):
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    try:
        data_inicio = f"{ano}-{mes:02d}-01"
        if mes == 12:
            data_fim = f"{ano+1}-01-01"
        else:
            data_fim = f"{ano}-{mes+1:02d}-01"
        query = '''
            SELECT * FROM eventos_calendario 
            WHERE data_evento >= %s AND data_evento < %s 
            ORDER BY data_evento, hora_evento
        '''
        df = pd.read_sql(query, conn, params=[data_inicio, data_fim])
        return df
    except Exception as e:
        st.error(f"Erro ao buscar eventos: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def gerar_calendario(ano, mes):
    cal = calendar.Calendar(firstweekday=6)  # Domingo como primeiro dia
    return cal.monthdatescalendar(ano, mes)

def salvar_evento(titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO eventos_calendario (titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento, st.session_state.username))
        conn.commit()
        st.success("✅ Evento salvo com sucesso!")
        return True
    except Error as e:
        st.error(f"❌ Erro ao salvar evento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def atualizar_evento(evento_id, titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE eventos_calendario 
            SET titulo = %s, descricao = %s, data_evento = %s, hora_evento = %s, tipo_evento = %s, cor_evento = %s
            WHERE id = %s
        ''', (titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento, evento_id))
        conn.commit()
        st.success("✅ Evento atualizado com sucesso!")
        return True
    except Error as e:
        st.error(f"❌ Erro ao atualizar evento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def excluir_evento(evento_id):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM eventos_calendario WHERE id = %s', (evento_id,))
        conn.commit()
        st.success("✅ Evento excluído com sucesso!")
        return True
    except Error as e:
        st.error(f"❌ Erro ao excluir: {e}")
        return False
    finally:
        if conn:
            conn.close()

def download_csv_mes(mes):
    df = get_lancamentos_mes(mes)
    if df.empty:
        return None
    return df.to_csv(index=False, encoding='utf-8')

def exportar_para_csv():
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            for mes in meses:
                df_mes = get_lancamentos_mes(mes)
                if not df_mes.empty:
                    csv_data = df_mes.to_csv(index=False, encoding='utf-8')
                    zip_file.writestr(f"lancamentos_{mes}.csv", csv_data)
            conn = get_db_connection()
            if conn:
                try:
                    df_contas = pd.read_sql("SELECT * FROM contas", conn)
                    if not df_contas.empty:
                        zip_file.writestr("contas.csv", df_contas.to_csv(index=False, encoding='utf-8'))
                    df_eventos = pd.read_sql("SELECT * FROM eventos_calendario", conn)
                    if not df_eventos.empty:
                        zip_file.writestr("eventos.csv", df_eventos.to_csv(index=False, encoding='utf-8'))
                finally:
                    conn.close()
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    except Exception as e:
        st.error(f"❌ Erro na exportação: {e}")
        return None

# =============================================================================
# PÁGINAS E INTERFACE (LOGIN, SIDEBAR, MENU) - com usuários expandidos
# =============================================================================

# Inicialização do estado da sessão
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.permissao = None

# Verificar secrets e conexão
if "planetscale" not in st.secrets:
    st.error("❌ Secrets do PlanetScale não configurados. Vá em Settings -> Secrets no Streamlit Cloud.")
    st.stop()

conn_test = get_db_connection()
if not conn_test:
    st.error("❌ Falha ao conectar ao banco. Verifique os secrets.")
    st.stop()
else:
    conn_test.close()

# Inicializar DBs e tabela usuarios (com campos adicionais)
init_db()
init_auth_db()

# PÁGINA DE LOGIN
if not st.session_state.logged_in:
    st.title("🔐 Login - Livro Caixa")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("""
        <div style="text-align: center; font-size: 80px; padding: 20px;">
            🔒
        </div>
        """, unsafe_allow_html=True)

    with col2:
        with st.form("login_form"):
            st.subheader("Acesso Restrito")
            username = st.text_input("Usuário", placeholder="Digite seu usuário")
            password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
            submitted = st.form_submit_button("🚪 Entrar", use_container_width=True)

            if submitted:
                if username and password:
                    success, result = login_user(username, password)
                    if success:
                        st.session_state.logged_in = True
                        st.session_state.username = result[0]
                        st.session_state.permissao = result[1]
                        st.success(f"✅ Bem-vindo, {username}!")
                        st.rerun()
                    else:
                        st.error(f"❌ {result}")
                else:
                    st.warning("⚠️ Preencha todos os campos!")

    st.stop()

# APLICAÇÃO PRINCIPAL (USUÁRIO LOGADO)
with st.sidebar:
    logo_path = carregar_imagem_logo("Logo_Loja.png")
    if logo_path:
        st.image(logo_path, width=180)
    else:
        st.markdown("""
        <div style="text-align: center; padding: 20px; border: 2px dashed #ccc; border-radius: 10px;">
            <div style="font-size: 48px;">🏢</div>
            <div style="color: #666;">Logo da Loja</div>
        </div>
        """, unsafe_allow_html=True)

    st.title("📒 Livro Caixa")
    st.markdown("---")
    st.success(f"👤 Usuário: {st.session_state.username}")
    st.info(f"🔐 Permissão: {PERMISSOES.get(st.session_state.permissao, 'Desconhecida')}")

    if st.button("🚪 Sair", use_container_width=True):
        logout_user()
        st.rerun()

    with st.expander("🔑 Alterar Senha"):
        with st.form("change_password_form"):
            new_password = st.text_input("Nova Senha", type="password")
            confirm_password = st.text_input("Confirmar Senha", type="password")
            if st.form_submit_button("💾 Alterar Senha", use_container_width=True):
                if new_password and confirm_password:
                    if new_password == confirm_password:
                        success, message = change_password(st.session_state.username, new_password)
                        if success:
                            st.success("✅ Senha alterada com sucesso!")
                        else:
                            st.error(f"❌ {message}")
                    else:
                        st.error("❌ As senhas não coincidem!")
                else:
                    st.warning("⚠️ Preencha todos os campos!")

# Menu principal
opcoes_menu = [
    "📋 Ajuda", 
    "👥 Gerenciar Usuários",
    "📝 Contas", 
    "📥 Lançamentos", 
    "📅 Calendário", 
    "📈 Balanço Financeiro", 
    "💾 Exportar Dados"
]

pagina = st.sidebar.radio("**Navegação:**", opcoes_menu)

st.markdown("---")

# ----------------------------
# PÁGINA: AJUDA
# ----------------------------
if pagina == "📋 Ajuda":
    st.title("📋 Ajuda - Livro Caixa")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("""
        ### Sistema Simplificado de Livro Caixa

        Este programa serve para lançar todas as receitas e despesas da empresa
        de forma simples e organizada.

        **✨ Funcionalidades:**
        - ✅ **Acesso Protegido**: Sistema de login seguro
        - ✅ **Gerenciamento de Usuários**: Crie e gerencie múltiplos usuários
        - ✅ **Banco de Dados PlanetScale**: Dados na nuvem com alta disponibilidade
        - ✅ **Contas Personalizáveis**: Adicione suas próprias contas
        - ✅ **Edição de Lançamentos**: Edite ou exclua lançamentos existentes
        - ✅ **Calendário Programável**: Agende eventos e compromissos
        - ✅ **Relatórios**: Balanço financeiro com gráficos
        - ✅ **Exportação**: Backup dos dados em CSV
        """)
    with col2:
        st.subheader("💡 Dicas")
        st.markdown("Use as permissões para controlar quem edita e quem apenas visualiza.")

# ----------------------------
# PÁGINA: GERENCIAR USUÁRIOS (COM CORREÇÕES NAS ABAS DE EDIÇÃO E EXCLUSÃO)
# ----------------------------
elif pagina == "👥 Gerenciar Usuários":
    st.title("👥 Gerenciar Usuários")

    if not user_is_admin():
        st.error("❌ Acesso restrito - Apenas administradores podem gerenciar usuários")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["➕ Criar Usuário", "✏️ Editar Permissões", "🗑️ Excluir Usuários"])

    with tab1:
        st.subheader("➕ Criar Novo Usuário")
        with st.form("form_criar_usuario"):
            col1, col2 = st.columns(2)
            with col1:
                novo_username = st.text_input("Nome de usuário", placeholder="Digite o nome de usuário")
                email = st.text_input("E-mail", placeholder="Digite o e-mail do usuário (opcional)")
                nova_senha = st.text_input("Senha", type="password", placeholder="Digite a senha")
                confirmar_senha = st.text_input("Confirmar Senha", type="password", placeholder="Confirme a senha")
                permissao = st.selectbox("Permissão", options=list(PERMISSOES.keys()),
                                         format_func=lambda x: PERMISSOES[x])
            with col2:
                nome_completo = st.text_input("Nome Completo (opcional)")
                telefone = st.text_input("Telefone (opcional)")
                endereco = st.text_area("Endereço (opcional)")
                data_aniversario = st.date_input("Data de Aniversário (opcional)", value=None)
                data_iniciacao = st.date_input("Data de Iniciação (opcional)", value=None)
                data_elevacao = st.date_input("Data de Elevação (opcional)", value=None)
                data_exaltacao = st.date_input("Data de Exaltação (opcional)", value=None)
                data_instalacao_posse = st.date_input("Data de Instalação/Posse (opcional)", value=None)
                observacoes = st.text_area("Observações (opcional)")
                redes_sociais = st.text_input("Redes Sociais (opcional) - ex: @usuario / link")

            submitted = st.form_submit_button("👤 Criar Usuário", use_container_width=True)
            if submitted:
                if not novo_username or not nova_senha or not confirmar_senha:
                    st.error("❌ Usuário e senha são obrigatórios!")
                elif nova_senha != confirmar_senha:
                    st.error("❌ As senhas não coincidem!")
                elif len(nova_senha) < 4:
                    st.error("❌ A senha deve ter pelo menos 4 caracteres!")
                else:
                    # Converter datas vazias para None (MySQL aceita NULL)
                    da = data_aniversario if data_aniversario else None
                    di = data_iniciacao if data_iniciacao else None
                    de = data_elevacao if data_elevacao else None
                    dx = data_exaltacao if data_exaltacao else None
                    dip = data_instalacao_posse if data_instalacao_posse else None

                    success, message = criar_usuario(
                        novo_username, nova_senha, permissao, email,
                        nome_completo=nome_completo or None,
                        telefone=telefone or None,
                        endereco=endereco or None,
                        data_aniversario=da,
                        data_iniciacao=di,
                        data_elevacao=de,
                        data_exaltacao=dx,
                        data_instalacao_posse=dip,
                        observacoes=observacoes or None,
                        redes_sociais=redes_sociais or None
                    )
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

    with tab2:
        st.subheader("✏️ Editar Permissões de Usuários")
        
        # Buscar usuários
        users = get_all_users()
        
        if not users:
            st.info("📭 Nenhum usuário cadastrado no sistema.")
        else:
            st.write(f"**Total de usuários encontrados:** {len(users)}")
            
            for i, user in enumerate(users):
                # Desempacotar os dados do usuário
                username = user[0]
                email = user[1]
                permissao_atual = user[2]
                created_at = user[3]
                nome_completo = user[4]
                telefone = user[5]
                endereco = user[6]
                
                # Criar container para cada usuário
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                    
                    with col1:
                        st.write(f"**{username}**")
                        if nome_completo:
                            st.write(f"👤 {nome_completo}")
                        if email:
                            st.write(f"📧 {email}")
                    
                    with col2:
                        st.write(f"**Permissão atual:**")
                        st.write(PERMISSOES.get(permissao_atual, 'Desconhecida'))
                    
                    with col3:
                        # Apenas permitir edição de outros usuários, não do próprio
                        if username != st.session_state.username:
                            nova_permissao = st.selectbox(
                                "Nova permissão:",
                                options=list(PERMISSOES.keys()),
                                index=list(PERMISSOES.keys()).index(permissao_atual) if permissao_atual in PERMISSOES else 0,
                                key=f"edit_perm_{username}_{i}"
                            )
                        else:
                            st.write("👤 **Você**")
                            nova_permissao = permissao_atual
                    
                    with col4:
                        if username != st.session_state.username:
                            if st.button("💾 Salvar", key=f"save_{username}_{i}", use_container_width=True):
                                if nova_permissao != permissao_atual:
                                    success, message = update_user_permission(username, nova_permissao)
                                    if success:
                                        st.success(f"✅ Permissão de {username} atualizada para {PERMISSOES[nova_permissao]}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {message}")
                                else:
                                    st.info("ℹ️ Nenhuma alteração realizada")
                        else:
                            st.write("")
                    
                    st.markdown("---")

    with tab3:
        st.subheader("🗑️ Excluir Usuários")
        
        # Buscar usuários
        users = get_all_users()
        
        if not users:
            st.info("📭 Nenhum usuário cadastrado no sistema.")
        else:
            st.warning("⚠️ **Atenção:** Esta ação não pode ser desfeita!")
            
            for i, user in enumerate(users):
                username = user[0]
                email = user[1]
                permissao = user[2]
                nome_completo = user[4]
                
                # Não permitir excluir o próprio usuário
                if username != st.session_state.username:
                    with st.container():
                        col1, col2, col3 = st.columns([3, 2, 1])
                        
                        with col1:
                            st.write(f"**{username}**")
                            if nome_completo:
                                st.write(f"👤 {nome_completo}")
                            if email:
                                st.write(f"📧 {email}")
                        
                        with col2:
                            st.write(f"**Permissão:** {PERMISSOES.get(permissao, 'Desconhecida')}")
                        
                        with col3:
                            if st.button("🗑️ Excluir", key=f"del_{username}_{i}", type="secondary", use_container_width=True):
                                # Confirmação adicional
                                if st.checkbox(f"✅ Confirmar exclusão de {username}", key=f"confirm_del_{username}_{i}"):
                                    success, message = delete_user(username)
                                    if success:
                                        st.success(f"✅ {message}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {message}")
                        
                        st.markdown("---")
                else:
                    with st.container():
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            st.write(f"**{username}** 👤 (Você)")
                        with col2:
                            st.write(f"**Permissão:** {PERMISSOES.get(permissao, 'Desconhecida')}")
                        with col3:
                            st.write("🔒 Não pode excluir")
                        st.markdown("---")

    # Estatísticas de usuários
    st.markdown("---")
    st.subheader("📊 Estatísticas de Usuários")
    
    users = get_all_users()
    if users:
        total_usuarios = len(users)
        admin_count = sum(1 for user in users if user[2] == 'admin')
        editor_count = sum(1 for user in users if user[2] == 'editor')
        visualizador_count = sum(1 for user in users if user[2] == 'visualizador')

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total de Usuários", total_usuarios)
        with col2:
            st.metric("Administradores", admin_count)
        with col3:
            st.metric("Editores", editor_count)
        with col4:
            st.metric("Visualizadores", visualizador_count)
    else:
        st.info("Nenhum usuário cadastrado.")

# ... (restante do código mantido igual para as outras páginas)

# ----------------------------
# PÁGINA: CONTAS
# ----------------------------
elif pagina == "📝 Contas":
    st.title("📝 Contas")
    contas = get_contas()
    if contas:
        st.subheader("📋 Contas Cadastradas")
        for i, conta in enumerate(contas, 1):
            st.write(f"{i}. **{conta}**")
    else:
        st.info("📭 Nenhuma conta cadastrada ainda.")

    if user_can_edit():
        st.subheader("➕ Adicionar Nova Conta")
        nova_conta = st.text_input("Nome da Nova Conta", placeholder="Ex: Salários, Aluguel, Vendas...")
        if st.button("✅ Adicionar Conta", use_container_width=True) and nova_conta:
            adicionar_conta(nova_conta)
            st.rerun()
    else:
        st.info("👀 Modo de Visualização - Você pode apenas visualizar as contas existentes.")

# ... (restante do código para as outras páginas permanece igual)

# RODAPÉ
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: #666; font-size: 0.9rem;'>
        <strong>CONSTITUCIONALISTAS-929</strong> - Livro Caixa | 
        Desenvolvido por Silmar Tolotto | 
        Usuário: {st.session_state.username} | 
        {datetime.now().strftime('%d/%m/%Y %H:%M')}
    </div>
    """, unsafe_allow_html=True
)
