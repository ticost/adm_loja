# app.py - SISTEMA COMPLETO LIVRO CAIXA COM AGENDA DE CONTATOS
import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
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
import base64
from PIL import Image

# Configuração da página
st.set_page_config(
    page_title="Administração de Loja",
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
# INICIALIZAÇÃO DO SESSION STATE
# =============================================================================
def init_session_state():
    """Inicializa todas as variáveis do session state"""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.permissao = None
    
    # Variáveis para gerenciamento de usuários
    if 'editing_user' not in st.session_state:
        st.session_state.editing_user = None
    if 'viewing_user' not in st.session_state:
        st.session_state.viewing_user = None
    
    # Variáveis para gerenciamento de eventos
    if 'editing_event' not in st.session_state:
        st.session_state.editing_event = None
    
    # Variáveis para gerenciamento de lançamentos
    if 'editing_lancamento' not in st.session_state:
        st.session_state.editing_lancamento = None
    
    # Variáveis para navegação
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "📊 Livro Caixa"

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

        # VERIFICAR E ADICIONAR CAMPOS OPCIONAIS - método mais compatível
        campos_adicionais = [
            ('nome_completo', 'VARCHAR(200)'),
            ('telefone', 'VARCHAR(50)'),
            ('endereco', 'TEXT'),
            ('data_aniversario', 'DATE'),
            ('data_iniciacao', 'DATE'),
            ('data_elevacao', 'DATE'),
            ('data_exaltacao', 'DATE'),
            ('data_instalacao_posse', 'DATE'),
            ('observacoes', 'TEXT'),
            ('redes_sociais', 'VARCHAR(500)')
        ]

        # Verificar quais colunas já existem
        cursor.execute("SHOW COLUMNS FROM usuarios")
        colunas_existentes = [coluna[0] for coluna in cursor.fetchall()]

        # Adicionar colunas que não existem
        for campo, tipo in campos_adicionais:
            if campo not in colunas_existentes:
                try:
                    cursor.execute(f'ALTER TABLE usuarios ADD COLUMN {campo} {tipo}')
                except Exception as e:
                    st.warning(f"⚠️ Não foi possível adicionar a coluna '{campo}': {e}")

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
    st.session_state.editing_user = None
    st.session_state.viewing_user = None
    st.session_state.editing_event = None
    st.session_state.editing_lancamento = None
    st.session_state.current_page = "📊 Livro Caixa"

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
            ORDER BY nome_completo, username
        ''')
        return cursor.fetchall()
    except Error:
        return []
    finally:
        if conn:
            conn.close()

def get_all_users_for_agenda():
    """Busca todos os usuários para a agenda de contatos (todos podem acessar)"""
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
            ORDER BY nome_completo, username
        ''')
        return cursor.fetchall()
    except Error:
        return []
    finally:
        if conn:
            conn.close()

def get_user_by_username(username):
    """Busca um usuário específico pelo username"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, email, permissao, created_at,
                   nome_completo, telefone, endereco,
                   data_aniversario, data_iniciacao, data_elevacao,
                   data_exaltacao, data_instalacao_posse, observacoes, redes_sociais
            FROM usuarios WHERE username = %s
        ''', (username,))
        return cursor.fetchone()
    except Error:
        return None
    finally:
        if conn:
            conn.close()

def update_user(username, email=None, permissao=None, nome_completo=None, 
                telefone=None, endereco=None, data_aniversario=None, 
                data_iniciacao=None, data_elevacao=None, data_exaltacao=None, 
                data_instalacao_posse=None, observacoes=None, redes_sociais=None):
    """Atualiza todos os campos de um usuário"""
    if not user_is_admin():
        return False, "Apenas administradores podem atualizar usuários"

    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        cursor = conn.cursor()
        
        # Construir a query dinamicamente baseada nos campos fornecidos
        fields = []
        values = []
        
        if email is not None:
            fields.append("email = %s")
            values.append(email)
        if permissao is not None:
            fields.append("permissao = %s")
            values.append(permissao)
        if nome_completo is not None:
            fields.append("nome_completo = %s")
            values.append(nome_completo)
        if telefone is not None:
            fields.append("telefone = %s")
            values.append(telefone)
        if endereco is not None:
            fields.append("endereco = %s")
            values.append(endereco)
        if data_aniversario is not None:
            fields.append("data_aniversario = %s")
            values.append(data_aniversario)
        if data_iniciacao is not None:
            fields.append("data_iniciacao = %s")
            values.append(data_iniciacao)
        if data_elevacao is not None:
            fields.append("data_elevacao = %s")
            values.append(data_elevacao)
        if data_exaltacao is not None:
            fields.append("data_exaltacao = %s")
            values.append(data_exaltacao)
        if data_instalacao_posse is not None:
            fields.append("data_instalacao_posse = %s")
            values.append(data_instalacao_posse)
        if observacoes is not None:
            fields.append("observacoes = %s")
            values.append(observacoes)
        if redes_sociais is not None:
            fields.append("redes_sociais = %s")
            values.append(redes_sociais)
        
        if not fields:
            return False, "Nenhum campo para atualizar"
        
        values.append(username)
        query = f"UPDATE usuarios SET {', '.join(fields)} WHERE username = %s"
        
        cursor.execute(query, values)
        conn.commit()
        return True, "Usuário atualizado com sucesso"
        
    except Error as e:
        return False, f"Erro ao atualizar usuário: {e}"
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
                mes VARCHAR(50) NOT NULL,
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
                created_by VARCHAR(100),
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

def get_lancamento_by_id(lancamento_id):
    """Busca um lançamento específico pelo ID"""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM lancamentos WHERE id = %s', (lancamento_id,))
        result = cursor.fetchone()
        return result
    except Error:
        return None
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
        st.success("✅ Lançamento atualizado com sucesso!")
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
        st.success("✅ Lançamento excluído com sucesso!")
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

def get_evento_by_id(evento_id):
    """Busca um evento específico pelo ID"""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM eventos_calendario WHERE id = %s', (evento_id,))
        result = cursor.fetchone()
        return result
    except Error:
        return None
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
                    df_usuarios = pd.read_sql("SELECT username, email, permissao, nome_completo, telefone, endereco, data_aniversario, data_iniciacao, data_elevacao, data_exaltacao, data_instalacao_posse, observacoes, redes_sociais, created_at FROM usuarios", conn)
                    if not df_usuarios.empty:
                        zip_file.writestr("usuarios.csv", df_usuarios.to_csv(index=False, encoding='utf-8'))
                finally:
                    conn.close()
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    except Exception as e:
        st.error(f"❌ Erro na exportação: {e}")
        return None

# =============================================================================
# FUNÇÕES DE BACKUP
# =============================================================================

def criar_backup_completo():
    """Cria um backup completo de todos os dados do sistema"""
    try:
        # Criar arquivo ZIP em memória
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            # Backup de lançamentos por mês
            meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            
            for mes in meses:
                df_mes = get_lancamentos_mes(mes)
                if not df_mes.empty:
                    csv_data = df_mes.to_csv(index=False, encoding='utf-8')
                    zip_file.writestr(f"backup_lancamentos_{mes}.csv", csv_data)
            
            # Backup de todas as tabelas
            conn = get_db_connection()
            if conn:
                try:
                    # Backup de contas
                    df_contas = pd.read_sql("SELECT * FROM contas", conn)
                    if not df_contas.empty:
                        zip_file.writestr("backup_contas.csv", df_contas.to_csv(index=False, encoding='utf-8'))
                    
                    # Backup de eventos
                    df_eventos = pd.read_sql("SELECT * FROM eventos_calendario", conn)
                    if not df_eventos.empty:
                        zip_file.writestr("backup_eventos.csv", df_eventos.to_csv(index=False, encoding='utf-8'))
                    
                    # Backup de usuários (sem senha)
                    df_usuarios = pd.read_sql('''
                        SELECT username, email, permissao, nome_completo, telefone, endereco, 
                               data_aniversario, data_iniciacao, data_elevacao, data_exaltacao, 
                               data_instalacao_posse, observacoes, redes_sociais, created_at 
                        FROM usuarios
                    ''', conn)
                    if not df_usuarios.empty:
                        zip_file.writestr("backup_usuarios.csv", df_usuarios.to_csv(index=False, encoding='utf-8'))
                    
                    # Backup de estrutura das tabelas
                    cursor = conn.cursor()
                    cursor.execute("SHOW TABLES")
                    tables = cursor.fetchall()
                    
                    estrutura_sql = ""
                    for table in tables:
                        table_name = table[0]
                        cursor.execute(f"SHOW CREATE TABLE {table_name}")
                        create_table = cursor.fetchone()
                        if create_table:
                            estrutura_sql += f"-- Estrutura da tabela {table_name}\n"
                            estrutura_sql += create_table[1] + ";\n\n"
                    
                    zip_file.writestr("estrutura_tabelas.sql", estrutura_sql)
                    
                finally:
                    conn.close()
            
            # Adicionar informações do backup
            info_backup = f"""
            BACKUP DO SISTEMA LIVRO CAIXA
            Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            Usuário: {st.session_state.username}
            Permissão: {st.session_state.permissao}
            
            Conteúdo do backup:
            - Lançamentos mensais
            - Contas cadastradas
            - Eventos do calendário
            - Usuários (sem senhas)
            - Estrutura das tabelas
            
            Este arquivo contém todos os dados do sistema para restauração.
            """
            zip_file.writestr("INFO_BACKUP.txt", info_backup)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
        
    except Exception as e:
        st.error(f"❌ Erro ao criar backup: {e}")
        return None

def criar_backup_incremental():
    """Cria backup apenas dos dados recentes (últimos 30 dias)"""
    try:
        zip_buffer = io.BytesIO()
        data_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            conn = get_db_connection()
            if conn:
                try:
                    # Backup de lançamentos recentes
                    query_lancamentos = f"""
                        SELECT * FROM lancamentos 
                        WHERE created_at >= '{data_limite}' 
                        ORDER BY data, id
                    """
                    df_lancamentos = pd.read_sql(query_lancamentos, conn)
                    if not df_lancamentos.empty:
                        zip_file.writestr("backup_incremental_lancamentos.csv", df_lancamentos.to_csv(index=False, encoding='utf-8'))
                    
                    # Backup de eventos recentes
                    query_eventos = f"""
                        SELECT * FROM eventos_calendario 
                        WHERE created_at >= '{data_limite}' 
                        ORDER BY data_evento, hora_evento
                    """
                    df_eventos = pd.read_sql(query_eventos, conn)
                    if not df_eventos.empty:
                        zip_file.writestr("backup_incremental_eventos.csv", df_eventos.to_csv(index=False, encoding='utf-8'))
                    
                finally:
                    conn.close()
            
            # Informações do backup incremental
            info_backup = f"""
            BACKUP INCREMENTAL - SISTEMA LIVRO CAIXA
            Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            Período: Últimos 30 dias (a partir de {data_limite})
            Usuário: {st.session_state.username}
            
            Conteúdo:
            - Lançamentos recentes
            - Eventos recentes
            """
            zip_file.writestr("INFO_BACKUP_INCREMENTAL.txt", info_backup)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
        
    except Exception as e:
        st.error(f"❌ Erro ao criar backup incremental: {e}")
        return None

# =============================================================================
# FUNÇÕES PARA EDIÇÃO DE LANÇAMENTOS E EVENTOS
# =============================================================================

def show_editar_lancamento(lancamento_id, mes):
    """Interface para editar um lançamento existente"""
    lancamento = get_lancamento_by_id(lancamento_id)
    
    if not lancamento:
        st.error("❌ Lançamento não encontrado")
        return
    
    st.subheader(f"✏️ Editando Lançamento - {lancamento[3]}")  # historico
    
    with st.form("editar_lancamento"):
        col1, col2 = st.columns(2)
        
        with col1:
            data = st.date_input("Data:", value=lancamento[2])  # data
            historico = st.text_input("Histórico:*", value=lancamento[3], placeholder="Descrição do lançamento")  # historico
            complemento = st.text_area("Complemento:", value=lancamento[4] or "", placeholder="Informações adicionais")  # complemento
        
        with col2:
            entrada = st.number_input("Valor de Entrada (R$):", min_value=0.0, value=float(lancamento[5]), step=0.01)  # entrada
            saida = st.number_input("Valor de Saída (R$):", min_value=0.0, value=float(lancamento[6]), step=0.01)  # saida
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            submitted = st.form_submit_button("💾 Salvar Alterações")
        
        with col_btn2:
            if st.form_submit_button("❌ Cancelar"):
                st.session_state.editing_lancamento = None
                st.rerun()
        
        if submitted:
            if not historico:
                st.error("❌ O campo Histórico é obrigatório")
                return
            
            if entrada == 0 and saida == 0:
                st.error("❌ Pelo menos um valor (entrada ou saída) deve ser diferente de zero")
                return
            
            if atualizar_lancamento(lancamento_id, mes, data, historico, complemento, entrada, saida):
                st.session_state.editing_lancamento = None
                st.rerun()

def show_editar_evento(evento_id):
    """Interface para editar um evento existente"""
    evento = get_evento_by_id(evento_id)
    
    if not evento:
        st.error("❌ Evento não encontrado")
        st.session_state.editing_event = None
        return
    
    st.subheader(f"✏️ Editando Evento: {evento[1]}")  # titulo
    
    with st.form("editar_evento"):
        col1, col2 = st.columns(2)
        
        with col1:
            titulo = st.text_input("Título do Evento:*", value=evento[1], placeholder="Nome do evento")  # titulo
            descricao = st.text_area("Descrição:", value=evento[2] or "", placeholder="Detalhes do evento")  # descricao
            data_evento = st.date_input("Data do Evento:*", value=evento[3])  # data_evento
        
        with col2:
            hora_evento = st.time_input("Hora do Evento:", value=evento[4] if evento[4] else time(19, 0))  # hora_evento
            tipo_evento = st.selectbox("Tipo de Evento:", [
                "", "Iniciação", "Elevação", "Exaltação", "Sessão Economica", 
                "Jantar Ritualistico", "Reunião", "Feriado", "Entrega", "Compromisso"
            ], index=1 if evento[5] else 0)  # tipo_evento
            cor_evento = st.color_picker("Cor do Evento:", value=evento[6] or "#FF4B4B")  # cor_evento
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            submitted = st.form_submit_button("💾 Salvar Alterações")
        
        with col_btn2:
            if st.form_submit_button("❌ Cancelar"):
                st.session_state.editing_event = None
                st.rerun()
        
        if submitted:
            if not titulo:
                st.error("❌ O campo Título é obrigatório")
                return
            
            if atualizar_evento(evento_id, titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento):
                st.session_state.editing_event = None
                st.rerun()

# =============================================================================
# FUNÇÕES PARA AGENDA DE CONTATOS - LAYOUT MOBILE COM TODAS INFORMAÇÕES
# =============================================================================

def gerar_html_agenda_contatos(users):
    """Gera HTML para impressão da agenda de contatos"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agenda de Contatos - Administração de Loja </title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                color: #333;
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
                border-bottom: 2px solid #333;
                padding-bottom: 10px;
            }}
            .header h1 {{
                color: #2c3e50;
                margin: 0;
            }}
            .header .subtitle {{
                color: #7f8c8d;
                font-size: 14px;
            }}
            .contact-card {{
                border: 1px solid #ddd;
                margin: 15px 0;
                padding: 15px;
                border-radius: 8px;
                page-break-inside: avoid;
                background-color: #f9f9f9;
            }}
            .contact-header {{
                background-color: #2c3e50;
                color: white;
                padding: 10px;
                margin: -15px -15px 15px -15px;
                border-radius: 8px 8px 0 0;
                font-weight: bold;
            }}
            .contact-row {{
                display: flex;
                margin-bottom: 8px;
            }}
            .contact-label {{
                font-weight: bold;
                min-width: 120px;
                color: #2c3e50;
            }}
            .contact-value {{
                flex: 1;
            }}
            .dates-section {{
                background-color: #ecf0f1;
                padding: 10px;
                border-radius: 5px;
                margin: 10px 0;
            }}
            .dates-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
            }}
            .date-item {{
                display: flex;
            }}
            .date-label {{
                font-weight: bold;
                min-width: 100px;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                font-size: 12px;
                color: #7f8c8d;
                border-top: 1px solid #ddd;
                padding-top: 10px;
            }}
            @media print {{
                body {{
                    margin: 0;
                    padding: 10px;
                }}
                .contact-card {{
                    break-inside: avoid;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📒 Agenda de Contatos</h1>
            <div class="subtitle">
                Administração de Loja | Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}
            </div>
        </div>
    """

    for user in users:
        username, email, permissao, created_at, nome_completo, telefone, endereco, \
        data_aniversario, data_iniciacao, data_elevacao, data_exaltacao, \
        data_instalacao_posse, observacoes, redes_sociais = user

        # Formatar dados
        nome_display = nome_completo or username
        telefone_display = telefone or "Não informado"
        email_display = email or "Não informado"
        endereco_display = endereco or "Não informado"
        observacoes_display = observacoes or "Nenhuma observação"
        redes_sociais_display = redes_sociais or "Não informado"
        
        # Formatar datas
        def formatar_data(data):
            if data:
                return data.strftime('%d/%m/%Y')
            return "Não informada"

        html_content += f"""
        <div class="contact-card">
            <div class="contact-header">
                👤 {nome_display} - {PERMISSOES.get(permissao, permissao)}
            </div>
            
            <div class="contact-row">
                <div class="contact-label">Usuário:</div>
                <div class="contact-value">{username}</div>
            </div>
            
            <div class="contact-row">
                <div class="contact-label">E-mail:</div>
                <div class="contact-value">{email_display}</div>
            </div>
            
            <div class="contact-row">
                <div class="contact-label">Telefone:</div>
                <div class="contact-value">{telefone_display}</div>
            </div>
            
            <div class="contact-row">
                <div class="contact-label">Endereço:</div>
                <div class="contact-value">{endereco_display}</div>
            </div>
            
            <div class="dates-section">
                <strong>📅 Datas Importantes:</strong>
                <div class="dates-grid">
                    <div class="date-item">
                        <span class="date-label">Aniversário:</span>
                        <span>{formatar_data(data_aniversario)}</span>
                    </div>
                    <div class="date-item">
                        <span class="date-label">Iniciação:</span>
                        <span>{formatar_data(data_iniciacao)}</span>
                    </div>
                    <div class="date-item">
                        <span class="date-label">Elevação:</span>
                        <span>{formatar_data(data_elevacao)}</span>
                    </div>
                    <div class="date-item">
                        <span class="date-label">Exaltação:</span>
                        <span>{formatar_data(data_exaltacao)}</span>
                    </div>
                    <div class="date-item">
                        <span class="date-label">Posse:</span>
                        <span>{formatar_data(data_instalacao_posse)}</span>
                    </div>
                </div>
            </div>
            
            <div class="contact-row">
                <div class="contact-label">Redes Sociais:</div>
                <div class="contact-value">{redes_sociais_display}</div>
            </div>
            
            <div class="contact-row">
                <div class="contact-label">Observações:</div>
                <div class="contact-value">{observacoes_display}</div>
            </div>
            
            <div class="contact-row">
                <div class="contact-label">Cadastrado em:</div>
                <div class="contact-value">{created_at.strftime('%d/%m/%Y')}</div>
            </div>
        </div>
        """

    html_content += f"""
        <div class="footer">
            Total de contatos: {len(users)} | Administração de Loja © {datetime.now().year}
        </div>
    </body>
    </html>
    """
    
    return html_content

def visualizar_agenda_contatos():
    """Interface para visualização da agenda de contatos - TODOS veem TODAS as informações"""
    st.header("📒 Agenda de Contatos")
    
    users = get_all_users_for_agenda()
    
    if not users:
        st.info("📭 Nenhum usuário cadastrado no sistema")
        return
    
    st.success(f"📊 Total de contatos: {len(users)}")
    
    # Filtros SIMPLES - uma linha para mobile
    busca = st.text_input("🔍 Buscar:", placeholder="Digite nome, usuário, e-mail...")
    
    # Aplicar filtro de busca
    users_filtrados = []
    for user in users:
        username, email, permissao, created_at, nome_completo, telefone, endereco, \
        data_aniversario, data_iniciacao, data_elevacao, data_exaltacao, \
        data_instalacao_posse, observacoes, redes_sociais = user
        
        if busca:
            busca_lower = busca.lower()
            if not ((nome_completo and busca_lower in nome_completo.lower()) or
                   busca_lower in username.lower() or
                   (email and busca_lower in email.lower()) or
                   (telefone and busca_lower in telefone)):
                continue
        
        users_filtrados.append(user)
    
    # Ordenar por nome
    users_filtrados.sort(key=lambda x: (x[4] or x[0]).lower())
    
    # Botão de atualização
    if st.button("🔄 Atualizar", use_container_width=True):
        st.rerun()
    
    # Opções de exportação (apenas para admin)
    if user_is_admin():
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🖨️ Gerar HTML", use_container_width=True):
                html_content = gerar_html_agenda_contatos(users_filtrados)
                st.download_button(
                    label="📥 Download HTML",
                    data=html_content,
                    file_name=f"agenda_contatos_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                    mime="text/html",
                    use_container_width=True
                )
        
        with col2:
            if st.button("📊 Exportar CSV", use_container_width=True):
                dados_exportacao = []
                for user in users_filtrados:
                    username, email, permissao, created_at, nome_completo, telefone, endereco, \
                    data_aniversario, data_iniciacao, data_elevacao, data_exaltacao, \
                    data_instalacao_posse, observacoes, redes_sociais = user
                    
                    dados_exportacao.append({
                        'Nome Completo': nome_completo or '',
                        'Usuário': username,
                        'E-mail': email or '',
                        'Permissão': PERMISSOES.get(permissao, permissao),
                        'Telefone': telefone or '',
                        'Endereço': endereco or '',
                        'Data Aniversário': data_aniversario.strftime('%d/%m/%Y') if data_aniversario else '',
                        'Data Iniciação': data_iniciacao.strftime('%d/%m/%Y') if data_iniciacao else '',
                        'Data Elevação': data_elevacao.strftime('%d/%m/%Y') if data_elevacao else '',
                        'Data Exaltação': data_exaltacao.strftime('%d/%m/%Y') if data_exaltacao else '',
                        'Data Posse': data_instalacao_posse.strftime('%d/%m/%Y') if data_instalacao_posse else '',
                        'Redes Sociais': redes_sociais or '',
                        'Observações': observacoes or '',
                        'Data Cadastro': created_at.strftime('%d/%m/%Y')
                    })
                
                df_export = pd.DataFrame(dados_exportacao)
                csv_data = df_export.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name=f"agenda_contatos_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    st.markdown("---")
    
    # EXIBIÇÃO MOBILE - Layout vertical com TODAS as informações visíveis
    for user in users_filtrados:
        username, email, permissao, created_at, nome_completo, telefone, endereco, \
        data_aniversario, data_iniciacao, data_elevacao, data_exaltacao, \
        data_instalacao_posse, observacoes, redes_sociais = user
        
        with st.container():
            # CABEÇALHO PRINCIPAL
            nome_display = nome_completo or username
            permissao_display = PERMISSOES.get(permissao, permissao)
            
            st.write(f"### 👤 {nome_display}")
            st.write(f"**Usuário:** {username} | **Permissão:** {permissao_display}")
            
            # INFORMAÇÕES DE CONTATO - SEMPRE VISÍVEIS
            if email or telefone:
                st.write("**📞 Contato:**")
                if email:
                    st.write(f"📧 **E-mail:** {email}")
                if telefone:
                    st.write(f"📱 **Telefone:** {telefone}")
            
            # ENDEREÇO E REDES SOCIAIS
            if endereco or redes_sociais:
                st.write("**📍 Informações Adicionais:**")
                if endereco:
                    st.write(f"🏠 **Endereço:** {endereco}")
                if redes_sociais:
                    st.write(f"🌐 **Redes Sociais:** {redes_sociais}")
            
            # DATAS IMPORTANTES
            st.write("**📅 Datas Importantes:**")
            col1, col2 = st.columns(2)
            datas_existem = False
            
            with col1:
                if data_aniversario:
                    st.write(f"• 🎂 **Aniversário:** {data_aniversario.strftime('%d/%m/%Y')}")
                    datas_existem = True
                if data_iniciacao:
                    st.write(f"• 🕊️ **Iniciação:** {data_iniciacao.strftime('%d/%m/%Y')}")
                    datas_existem = True
                if data_elevacao:
                    st.write(f"• ⬆️ **Elevação:** {data_elevacao.strftime('%d/%m/%Y')}")
                    datas_existem = True
            
            with col2:
                if data_exaltacao:
                    st.write(f"• ⭐ **Exaltação:** {data_exaltacao.strftime('%d/%m/%Y')}")
                    datas_existem = True
                if data_instalacao_posse:
                    st.write(f"• 👑 **Posse:** {data_instalacao_posse.strftime('%d/%m/%Y')}")
                    datas_existem = True
            
            if not datas_existem:
                st.write("*Nenhuma data importante cadastrada*")
            
            # OBSERVAÇÕES
            if observacoes:
                st.write("**📝 Observações:**")
                st.write(observacoes)
            
            # INFORMAÇÃO DE CADASTRO
            st.caption(f"📅 **Cadastrado em:** {created_at.strftime('%d/%m/%Y')}")
            
            # BOTÃO DE EDIÇÃO (apenas admin)
            if user_is_admin():
                if st.button("✏️ Editar Usuário", key=f"edit_{username}", use_container_width=True):
                    st.session_state.editing_user = username
                    st.rerun()
            
            st.markdown("---")

# =============================================================================
# INTERFACE PRINCIPAL
# =============================================================================

def main():
    """Função principal da aplicação"""
    
    # Inicializar session state
    init_session_state()
    
    # Inicializar banco de dados
    init_auth_db()
    init_db()
    
    # Logo e cabeçalho
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("📒 Administração de Loja")
        st.markdown("---")
    
    # Sistema de autenticação
    if not st.session_state.logged_in:
        show_login_section()
    else:
        show_main_application()

def show_login_section():
    """Exibe a seção de login"""
    st.header("🔐 Acesso ao Sistema")
    
    with st.form("login_form"):
        username = st.text_input("👤 Usuário")
        password = st.text_input("🔒 Senha", type="password")
        submit = st.form_submit_button("🚀 Entrar")
        
        if submit:
            if username and password:
                success, result = login_user(username, password)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.username = result[0]
                    st.session_state.permissao = result[1]
                    st.success(f"✅ Login realizado com sucesso! Bem-vindo, {result[0]}!")
                    st.rerun()
                else:
                    st.error(f"❌ {result}")
            else:
                st.warning("⚠️ Preencha todos os campos")

def show_main_application():
    """Exibe a aplicação principal após login"""
    
    # Sidebar com navegação
    with st.sidebar:
        # Adicione estas importações no início do arquivo, se ainda não existirem
import base64
from PIL import Image

# =============================================================================
# FUNÇÃO PARA CARREGAR E EXIBIR LOGO
# =============================================================================
def exibir_logo():
    """Exibe o logo da loja no sidebar ou header"""
    caminho_logo = carregar_imagem_logo("logo.png")  # Tenta carregar logo.png primeiro
    
    # Se não encontrar, tenta outros nomes comuns
    if not caminho_logo:
        caminho_logo = carregar_imagem_logo("logo.jpg")
    if not caminho_logo:
        caminho_logo = carregar_imagem_logo("logo.jpeg")
    if not caminho_logo:
        caminho_logo = carregar_imagem_logo("logo.webp")
    
    if caminho_logo:
        try:
            # Carregar e exibir a imagem
            image = Image.open(caminho_logo)
            
            # Redimensionar se for muito grande (max 300px de largura)
            largura, altura = image.size
            if largura > 300:
                nova_largura = 300
                nova_altura = int((nova_largura / largura) * altura)
                image = image.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)
            
            # Exibir no sidebar
            st.sidebar.image(image, use_column_width=True)
            
        except Exception as e:
            st.sidebar.warning(f"⚠️ Erro ao carregar logo: {e}")
    else:
        # Exibir placeholder se logo não for encontrado
        st.sidebar.markdown("""
        <div style='text-align: center; padding: 10px; border: 2px dashed #ccc; border-radius: 10px;'>
            <h3>🏪 Minha Loja</h3>
            <p>Logo não configurado</p>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# FUNÇÃO PARA FAZER UPLOAD DO LOGO (APENAS ADMIN)
# =============================================================================
def gerenciar_logo():
    """Permite ao admin fazer upload de um novo logo"""
    if not user_is_admin():
        return
    
    st.sidebar.markdown("---")
    with st.sidebar.expander("🖼️ Configurar Logo"):
        st.write("**Upload do Logo da Loja**")
        
        uploaded_file = st.file_uploader(
            "Escolha uma imagem para o logo:",
            type=['png', 'jpg', 'jpeg', 'webp'],
            key="logo_upload"
        )
        
        if uploaded_file is not None:
            try:
                # Verificar o tamanho do arquivo (max 5MB)
                if uploaded_file.size > 5 * 1024 * 1024:
                    st.error("❌ Arquivo muito grande. Tamanho máximo: 5MB")
                    return
                
                # Carregar e validar a imagem
                image = Image.open(uploaded_file)
                
                # Mostrar preview
                st.image(image, caption="Preview do Logo", width=200)
                
                # Salvar a imagem
                caminho_logo = "logo.png"
                image.save(caminho_logo, "PNG")
                
                st.success("✅ Logo salvo com sucesso!")
                st.info("🔄 Recarregue a página para ver as alterações")
                
            except Exception as e:
                st.error(f"❌ Erro ao processar imagem: {e}")

# =============================================================================
# MODIFICAÇÃO NA FUNÇÃO show_main_application()
# =============================================================================
def show_main_application():
    """Exibe a aplicação principal após login"""
    
    # Sidebar com navegação E LOGO
    with st.sidebar:
        # EXIBIR LOGO NO TOPO
        exibir_logo()
        
        st.header(f"👋 Olá, {st.session_state.username}!")
        st.write(f"**Permissão:** {PERMISSOES.get(st.session_state.permissao, st.session_state.permissao)}")
        st.markdown("---")
        
        # Resto do menu de navegação (mantido igual)
        menu_options = ["📊 Livro Caixa", "📅 Calendário"]
        
        if user_can_edit():
            menu_options.append("⚙️ Configurações")
        
        menu_options.append("📒 Agenda de Contatos")
        
        if user_is_admin():
            menu_options.append("👥 Gerenciar Usuários")
        
        selected_menu = st.radio("Navegação", menu_options, key="nav_menu")
        
        st.markdown("---")
        
        # Informações do sistema
        st.write("**💡 Dicas:**")
        st.write("- Use o Livro Caixa para registrar entradas e saídas")
        st.write("- O calendário ajuda no planejamento de eventos")
        st.write("- A agenda de contatos mostra informações dos membros")
        if user_is_admin():
            st.write("- Como admin, você pode gerenciar usuários")
        
        st.markdown("---")
        
        # GERENCIAR LOGO (apenas para admin)
        gerenciar_logo()
        
        st.markdown("---")
        
        # Logout
        if st.button("🚪 Sair", use_container_width=True):
            logout_user()
            st.rerun()
    
    # Resto da função mantido igual...
    if selected_menu == "📊 Livro Caixa":
        show_livro_caixa()
    elif selected_menu == "📅 Calendário":
        show_calendario()
    elif selected_menu == "⚙️ Configurações" and user_can_edit():
        show_configuracoes()
    elif selected_menu == "👥 Gerenciar Usuários" and user_is_admin():
        show_gerenciar_usuarios()
    elif selected_menu == "📒 Agenda de Contatos":
        visualizar_agenda_contatos()

# =============================================================================
# MODIFICAÇÃO NO CABEÇALHO PRINCIPAL
# =============================================================================
def main():
    """Função principal da aplicação"""
    
    # Inicializar session state
    init_session_state()
    
    # Inicializar banco de dados
    init_auth_db()
    init_db()
    
    # Logo e cabeçalho - LAYOUT MELHORADO
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Tenta carregar e exibir um logo pequeno no header também
        caminho_logo_header = carregar_imagem_logo("Logo_Loja.png")
        if caminho_logo_header:
            try:
                image = Image.open(caminho_logo_header)
                # Redimensionar para header (max 100px)
                largura, altura = image.size
                if largura > 100:
                    nova_largura = 100
                    nova_altura = int((nova_largura / largura) * altura)
                    image = image.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)
                
                st.image(image, use_column_width=False)
            except:
                # Se der erro, mostra apenas o título
                st.title("📒 Administração de Loja")
        else:
            st.title("📒 Administração de Loja")
        
        st.markdown("---")
    
    # Resto da função mantido igual...
    if not st.session_state.logged_in:
        show_login_section()
    else:
        show_main_application()
        st.header(f"👋 Olá, {st.session_state.username}!")
        st.write(f"**Permissão:** {PERMISSOES.get(st.session_state.permissao, st.session_state.permissao)}")
        st.markdown("---")
        
        # Menu de navegação - CONFIGURAÇÃO APENAS PARA ADMIN E EDITOR
        menu_options = ["📊 Livro Caixa", "📅 Calendário"]
        
        # Configurações apenas para admin e editor
        if user_can_edit():
            menu_options.append("⚙️ Configurações")
        
        # TODOS os usuários podem ver a agenda de contatos
        menu_options.append("📒 Agenda de Contatos")
        
        # Apenas admins podem gerenciar usuários
        if user_is_admin():
            menu_options.append("👥 Gerenciar Usuários")
        
        selected_menu = st.radio("Navegação", menu_options, key="nav_menu")
        
        st.markdown("---")
        
        # Informações do sistema
        st.write("**💡 Dicas:**")
        st.write("- Use o Livro Caixa para registrar entradas e saídas")
        st.write("- O calendário ajuda no planejamento de eventos")
        st.write("- A agenda de contatos mostra informações dos membros")
        if user_is_admin():
            st.write("- Como admin, você pode gerenciar usuários")
        
        st.markdown("---")
        
        # Logout
        if st.button("🚪 Sair", use_container_width=True):
            logout_user()
            st.rerun()
    
    # Conteúdo principal baseado na seleção do menu
    if selected_menu == "📊 Livro Caixa":
        show_livro_caixa()
    elif selected_menu == "📅 Calendário":
        show_calendario()
    elif selected_menu == "⚙️ Configurações" and user_can_edit():
        show_configuracoes()
    elif selected_menu == "👥 Gerenciar Usuários" and user_is_admin():
        show_gerenciar_usuarios()
    elif selected_menu == "📒 Agenda de Contatos":
        visualizar_agenda_contatos()

def show_livro_caixa():
    """Interface do Livro Caixa"""
    st.header("📊 Livro Caixa")
    
    # Verificar se está editando um lançamento
    if hasattr(st.session_state, 'editing_lancamento') and st.session_state.editing_lancamento:
        # Buscar o mês atual para passar como parâmetro
        meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                 "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_atual = meses[datetime.now().month-1]
        show_editar_lancamento(st.session_state.editing_lancamento, mes_atual)
        return
    
    # Seleção do mês
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        mes_selecionado = st.selectbox("Selecione o mês:", meses, index=datetime.now().month-1)
    
    # Buscar lançamentos do mês
    df_lancamentos = get_lancamentos_mes(mes_selecionado)
    
    # Estatísticas rápidas
    if not df_lancamentos.empty:
        total_entrada = df_lancamentos['entrada'].sum()
        total_saida = df_lancamentos['saida'].sum()
        saldo_final = df_lancamentos['saldo'].iloc[-1] if len(df_lancamentos) > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Entradas", f"R$ {total_entrada:,.2f}")
        with col2:
            st.metric("Total Saídas", f"R$ {total_saida:,.2f}")
        with col3:
            st.metric("Saldo Final", f"R$ {saldo_final:,.2f}")
        with col4:
            st.metric("Qtde Lançamentos", len(df_lancamentos))
    
    # Abas para diferentes funcionalidades
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Novo Lançamento", "📋 Lançamentos do Mês", "📈 Relatórios", "⚙️ Configurações"])
    
    with tab1:
        if user_can_edit():
            show_novo_lancamento(mes_selecionado)
        else:
            st.warning("⚠️ Você possui permissão apenas para visualização")
    
    with tab2:
        show_lancamentos_mes(mes_selecionado, df_lancamentos)
    
    with tab3:
        show_relatorios(mes_selecionado, df_lancamentos)
    
    with tab4:
        if user_is_admin():
            show_configuracoes_mes(mes_selecionado)
        else:
            st.warning("⚠️ Apenas administradores podem acessar as configurações")

def show_novo_lancamento(mes):
    """Formulário para novo lançamento"""
    with st.form("novo_lancamento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            data = st.date_input("Data:", value=datetime.now())
            historico = st.text_input("Histórico:*", placeholder="Descrição do lançamento")
            complemento = st.text_area("Complemento:", placeholder="Informações adicionais")
        
        with col2:
            entrada = st.number_input("Valor de Entrada (R$):", min_value=0.0, value=0.0, step=0.01)
            saida = st.number_input("Valor de Saída (R$):", min_value=0.0, value=0.0, step=0.01)
        
        submitted = st.form_submit_button("💾 Salvar Lançamento")
        
        if submitted:
            if not historico:
                st.error("❌ O campo Histórico é obrigatório")
                return
            
            if entrada == 0 and saida == 0:
                st.error("❌ Pelo menos um valor (entrada ou saída) deve ser diferente de zero")
                return
            
            # Calcular saldo
            df_existente = get_lancamentos_mes(mes)
            saldo_anterior = df_existente['saldo'].iloc[-1] if not df_existente.empty else 0
            saldo_atual = saldo_anterior + entrada - saida
            
            if salvar_lancamento(mes, data, historico, complemento, entrada, saida, saldo_atual):
                st.rerun()

def show_lancamentos_mes(mes, df_lancamentos):
    """Exibe os lançamentos do mês"""
    if df_lancamentos.empty:
        st.info("📭 Nenhum lançamento registrado para este mês")
        return
    
    # Opções de visualização
    col1, col2 = st.columns([3, 1])
    with col2:
        formato = st.radio("Formato:", ["Tabela", "Cards"], horizontal=True)
    
    if formato == "Tabela":
        # Preparar dados para exibição
        df_display = df_lancamentos.copy()
        df_display['data'] = pd.to_datetime(df_display['data']).dt.strftime('%d/%m/%Y')
        df_display['entrada'] = df_display['entrada'].apply(lambda x: f"R$ {x:,.2f}" if x > 0 else "")
        df_display['saida'] = df_display['saida'].apply(lambda x: f"R$ {x:,.2f}" if x > 0 else "")
        df_display['saldo'] = df_display['saldo'].apply(lambda x: f"R$ {x:,.2f}")
        
        # Exibir cabeçalhos da tabela
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 3, 2, 2, 2, 1, 1])
        with col1:
            st.write("**Data**")
        with col2:
            st.write("**Histórico**")
        with col3:
            st.write("**Entrada**")
        with col4:
            st.write("**Saída**")
        with col5:
            st.write("**Saldo**")
        with col6:
            st.write("**Editar**")
        with col7:
            st.write("**Excluir**")
        
        st.markdown("---")
        
        # Exibir cada linha com ações
        for _, row in df_display.iterrows():
            col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 3, 2, 2, 2, 1, 1])
            
            with col1:
                st.write(row['data'])
            with col2:
                st.write(f"**{row['historico']}**")
                if row['complemento']:
                    st.write(f"_{row['complemento']}_")
            with col3:
                st.write(row['entrada'])
            with col4:
                st.write(row['saida'])
            with col5:
                st.write(row['saldo'])
            with col6:
                if user_can_edit():
                    if st.button("✏️", key=f"edit_{row['id']}"):
                        st.session_state.editing_lancamento = row['id']
                        st.rerun()
            with col7:
                if user_can_edit():
                    if st.button("🗑️", key=f"del_{row['id']}"):
                        if excluir_lancamento(row['id'], mes):
                            st.rerun()
            
            st.markdown("---")
    else:
        # Visualização em cards
        for _, lancamento in df_lancamentos.iterrows():
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.write(f"**{lancamento['historico']}**")
                    if lancamento['complemento']:
                        st.write(f"_{lancamento['complemento']}_")
                    st.write(f"📅 {pd.to_datetime(lancamento['data']).strftime('%d/%m/%Y')}")
                
                with col2:
                    if lancamento['entrada'] > 0:
                        st.success(f"↗️ R$ {lancamento['entrada']:,.2f}")
                    if lancamento['saida'] > 0:
                        st.error(f"↘️ R$ {lancamento['saida']:,.2f}")
                
                with col3:
                    st.info(f"💰 R$ {lancamento['saldo']:,.2f}")
                
                with col4:
                    if user_can_edit():
                        col_edit, col_del = st.columns(2)
                        with col_edit:
                            if st.button("✏️", key=f"edit_card_{lancamento['id']}"):
                                st.session_state.editing_lancamento = lancamento['id']
                                st.rerun()
                        with col_del:
                            if st.button("🗑️", key=f"del_card_{lancamento['id']}"):
                                if excluir_lancamento(lancamento['id'], mes):
                                    st.rerun()
                
                st.markdown("---")

def show_relatorios(mes, df_lancamentos):
    """Exibe relatórios e gráficos"""
    if df_lancamentos.empty:
        st.info("📭 Nenhum dado para exibir relatórios")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Gráfico de Entradas vs Saídas")
        
        # Preparar dados para gráfico
        df_diario = df_lancamentos.copy()
        df_diario['data'] = pd.to_datetime(df_diario['data'])
        df_diario = df_diario.groupby('data').agg({
            'entrada': 'sum',
            'saida': 'sum'
        }).reset_index()
        
        chart_data = pd.DataFrame({
            'Data': df_diario['data'],
            'Entradas': df_diario['entrada'],
            'Saídas': df_diario['saida']
        })
        
        st.line_chart(chart_data, x='Data', y=['Entradas', 'Saídas'])
    
    with col2:
        st.subheader("🥧 Distribuição por Categoria")
        
        # Agrupar por histórico (simplificado)
        df_categorias = df_lancamentos.groupby('historico').agg({
            'entrada': 'sum',
            'saida': 'sum'
        }).reset_index()
        
        # Criar gráfico de pizza para saídas
        saidas_por_categoria = df_categorias[df_categorias['saida'] > 0]
        if not saidas_por_categoria.empty:
            st.bar_chart(saidas_por_categoria.set_index('historico')['saida'])
        else:
            st.info("Não há saídas para exibir")

def show_configuracoes_mes(mes):
    """Configurações administrativas do mês"""
    st.subheader("⚙️ Configurações do Mês")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Exportar CSV do Mês", use_container_width=True):
            csv_data = download_csv_mes(mes)
            if csv_data:
                st.download_button(
                    label="💾 Download CSV",
                    data=csv_data,
                    file_name=f"lancamentos_{mes}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    with col2:
        if st.button("🗑️ Limpar Todos os Lançamentos", use_container_width=True):
            if st.checkbox("⚠️ Confirmar exclusão de TODOS os lançamentos deste mês"):
                if limpar_lancamentos_mes(mes):
                    st.rerun()

def show_calendario():
    """Interface do Calendário"""
    st.header("📅 Calendário de Eventos")
    
    # Verificar se está editando um evento
    if hasattr(st.session_state, 'editing_event') and st.session_state.editing_event:
        show_editar_evento(st.session_state.editing_event)
        return
    
    # Seleção de mês/ano
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        ano_atual = datetime.now().year
        mes_atual = datetime.now().month
        ano = st.number_input("Ano:", min_value=2000, max_value=2100, value=ano_atual)
        mes = st.selectbox("Mês:", list(range(1, 13)), format_func=lambda x: [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ][x-1], index=mes_atual-1)
    
    # Buscar eventos do mês
    df_eventos = get_eventos_mes(ano, mes)
    
    # Abas do calendário
    tab1, tab2, tab3 = st.tabs(["📅 Visualização Mensal", "📋 Lista de Eventos", "➕ Novo Evento"])
    
    with tab1:
        show_calendario_mensal(ano, mes, df_eventos)
    
    with tab2:
        show_lista_eventos(df_eventos)
    
    with tab3:
        if user_can_edit():
            show_novo_evento()
        else:
            st.warning("⚠️ Você possui permissão apenas para visualização")

def show_calendario_mensal(ano, mes, df_eventos):
    """Exibe calendário mensal"""
    calendario = gerar_calendario(ano, mes)
    nomes_dias = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    
    # Cabeçalho dos dias
    cols = st.columns(7)
    for i, col in enumerate(cols):
        col.write(f"**{nomes_dias[i]}**")
    
    # Dias do mês
    for semana in calendario:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            with cols[i]:
                # Verificar se o dia é do mês atual
                if dia.month == mes:
                    # Verificar se há eventos neste dia
                    eventos_dia = df_eventos[
                        pd.to_datetime(df_eventos['data_evento']).dt.date == dia
                    ] if not df_eventos.empty else []
                    
                    num_eventos = len(eventos_dia)
                    estilo = "🔴" if num_eventos > 0 else ""
                    
                    st.write(f"**{dia.day}** {estilo}")
                    
                    if num_eventos > 0:
                        with st.expander(f"{num_eventos} evento(s)"):
                            for _, evento in eventos_dia.iterrows():
                                st.write(f"• {evento['titulo']}")
                                if evento['hora_evento']:
                                    st.write(f"  ⏰ {evento['hora_evento']}")
                else:
                    st.write(f"<span style='color: lightgray'>{dia.day}</span>", unsafe_allow_html=True)

def show_lista_eventos(df_eventos):
    """Exibe lista de eventos"""
    if df_eventos.empty:
        st.info("📭 Nenhum evento agendado para este período")
        return
    
    for _, evento in df_eventos.iterrows():
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            
            with col1:
                st.write(f"**{evento['titulo']}**")
                if evento['descricao']:
                    st.write(f"_{evento['descricao']}_")
                st.write(f"📅 {pd.to_datetime(evento['data_evento']).strftime('%d/%m/%Y')}")
                if evento['hora_evento']:
                    st.write(f"⏰ {evento['hora_evento']}")
            
            with col2:
                if evento['tipo_evento']:
                    st.info(f"🏷️ {evento['tipo_evento']}")
            
            with col3:
                if user_can_edit():
                    if st.button("✏️ Editar", key=f"edit_{evento['id']}"):
                        st.session_state.editing_event = evento['id']
                        st.rerun()
            
            with col4:
                if user_can_edit():
                    if st.button("🗑️ Excluir", key=f"del_{evento['id']}"):
                        if excluir_evento(evento['id']):
                            st.rerun()
            
            st.markdown("---")

def show_novo_evento():
    """Formulário para novo evento"""
    with st.form("novo_evento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            titulo = st.text_input("Título do Evento:*", placeholder="Nome do evento")
            descricao = st.text_area("Descrição:", placeholder="Detalhes do evento")
            data_evento = st.date_input("Data do Evento:*", value=datetime.now())
        
        with col2:
            hora_evento = st.time_input("Hora do Evento:", value=time(19, 0))
            tipo_evento = st.selectbox("Tipo de Evento:", [
                "", "Iniciação", "Elevação", "Exaltação", "Sessão Economica", "Jantar Ritualistico", " etc"
            ])
            cor_evento = st.color_picker("Cor do Evento:", "#FF4B4B")
        
        submitted = st.form_submit_button("💾 Salvar Evento")
        
        if submitted:
            if not titulo:
                st.error("❌ O campo Título é obrigatório")
                return
            
            if salvar_evento(titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento):
                st.rerun()

def show_configuracoes():
    """Configurações do sistema"""
    st.header("⚙️ Configurações do Sistema")
    
    if not user_is_admin():
        st.warning("⚠️ Apenas administradores podem acessar as configurações do sistema")
        return
    
    tab1, tab2, tab3 = st.tabs(["💾 Backup", "📤 Exportação", "🔧 Sistema"])
    
    with tab1:
        show_backup_section()
    
    with tab2:
        show_export_section()
    
    with tab3:
        show_system_info()

def show_backup_section():
    """Seção de backup"""
    st.subheader("💾 Backup do Sistema")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Criar Backup Completo", use_container_width=True):
            with st.spinner("Criando backup completo..."):
                backup_data = criar_backup_completo()
                if backup_data:
                    st.success("✅ Backup completo criado com sucesso!")
                    st.download_button(
                        label="📥 Download Backup Completo",
                        data=backup_data,
                        file_name=f"backup_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
    
    with col2:
        if st.button("📈 Backup Incremental", use_container_width=True):
            with st.spinner("Criando backup incremental..."):
                backup_data = criar_backup_incremental()
                if backup_data:
                    st.success("✅ Backup incremental criado com sucesso!")
                    st.download_button(
                        label="📥 Download Backup Incremental",
                        data=backup_data,
                        file_name=f"backup_incremental_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
    
    st.info("""
    **💡 Sobre os backups:**
    - **Backup Completo:** Contém todos os dados do sistema
    - **Backup Incremental:** Contém apenas dados dos últimos 30 dias
    - Recomendamos fazer backups regulares para garantir a segurança dos dados
    """)

def show_export_section():
    """Seção de exportação"""
    st.subheader("📤 Exportação de Dados")
    
    if st.button("📊 Exportar Todos os Dados para CSV", use_container_width=True):
        with st.spinner("Exportando dados..."):
            zip_data = exportar_para_csv()
            if zip_data:
                st.success("✅ Exportação concluída com sucesso!")
                st.download_button(
                    label="📥 Download Exportação Completa",
                    data=zip_data,
                    file_name=f"exportacao_completa_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )

def show_system_info():
    """Informações do sistema"""
    st.subheader("🔧 Informações do Sistema")
    
    # Estatísticas do sistema
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Contar registros
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            total_usuarios = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM lancamentos")
            total_lancamentos = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM eventos_calendario")
            total_eventos = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM contas")
            total_contas = cursor.fetchone()[0]
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total de Usuários", total_usuarios)
            with col2:
                st.metric("Total de Lançamentos", total_lancamentos)
            with col3:
                st.metric("Total de Eventos", total_eventos)
            with col4:
                st.metric("Total de Contas", total_contas)
                
        except Error as e:
            st.error(f"❌ Erro ao buscar estatísticas: {e}")
        finally:
            conn.close()

def show_gerenciar_usuarios():
    """Interface para gerenciamento de usuários"""
    st.header("👥 Gerenciamento de Usuários")
    
    if not user_is_admin():
        st.warning("⚠️ Apenas administradores podem gerenciar usuários")
        return
    
    tab1, tab2, tab3 = st.tabs(["➕ Novo Usuário", "📋 Usuários Cadastrados", "🔧 Editar Usuário"])
    
    with tab1:
        show_novo_usuario()
    
    with tab2:
        show_usuarios_cadastrados()
    
    with tab3:
        # Verificar de forma segura se há usuário sendo editado
        if hasattr(st.session_state, 'editing_user') and st.session_state.editing_user:
            show_editar_usuario(st.session_state.editing_user)
        else:
            st.info("👆 Selecione um usuário para editar na aba 'Usuários Cadastrados'")

def show_novo_usuario():
    """Formulário para novo usuário"""
    with st.form("novo_usuario", clear_on_submit=True):
        st.subheader("👤 Novo Usuário")
        
        col1, col2 = st.columns(2)
        
        with col1:
            username = st.text_input("Usuário:*", placeholder="Nome de usuário para login")
            password = st.text_input("Senha:*", type="password", placeholder="Senha para acesso")
            confirm_password = st.text_input("Confirmar Senha:*", type="password", placeholder="Digite novamente a senha")
            permissao = st.selectbox("Permissão:*", list(PERMISSOES.keys()), format_func=lambda x: PERMISSOES[x])
            email = st.text_input("E-mail:", placeholder="email@exemplo.com")
        
        with col2:
            nome_completo = st.text_input("Nome Completo:", placeholder="Nome completo do usuário")
            telefone = st.text_input("Telefone:", placeholder="(00) 00000-0000")
            endereco = st.text_area("Endereço:", placeholder="Endereço completo")
            data_aniversario = st.date_input("Data de Aniversário:", value=None)
        
        # Campos adicionais em expansores
        with st.expander("📅 Datas Maçônicas (Opcional)"):
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                data_iniciacao = st.date_input("Data de Iniciação:", value=None)
                data_elevacao = st.date_input("Data de Elevação:", value=None)
            with col_d2:
                data_exaltacao = st.date_input("Data de Exaltação:", value=None)
                data_instalacao_posse = st.date_input("Data de Instalação/Posse:", value=None)
        
        with st.expander("📝 Observações e Redes Sociais"):
            observacoes = st.text_area("Observações:", placeholder="Observações adicionais sobre o usuário")
            redes_sociais = st.text_input("Redes Sociais:", placeholder="Links ou @ das redes sociais")
        
        submitted = st.form_submit_button("💾 Criar Usuário")
        
        if submitted:
            # Validações
            if not username or not password:
                st.error("❌ Usuário e senha são obrigatórios")
                return
            
            if password != confirm_password:
                st.error("❌ As senhas não coincidem")
                return
            
            if len(password) < 6:
                st.error("❌ A senha deve ter pelo menos 6 caracteres")
                return
            
            # Criar usuário
            success, message = criar_usuario(
                username=username,
                password=password,
                permissao=permissao,
                email=email or None,
                nome_completo=nome_completo or None,
                telefone=telefone or None,
                endereco=endereco or None,
                data_aniversario=data_aniversario or None,
                data_iniciacao=data_iniciacao or None,
                data_elevacao=data_elevacao or None,
                data_exaltacao=data_exaltacao or None,
                data_instalacao_posse=data_instalacao_posse or None,
                observacoes=observacoes or None,
                redes_sociais=redes_sociais or None
            )
            
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(f"❌ {message}")

def show_usuarios_cadastrados():
    """Lista de usuários cadastrados"""
    st.subheader("📋 Usuários do Sistema")
    
    users = get_all_users()
    
    if not users:
        st.info("📭 Nenhum usuário cadastrado no sistema")
        return
    
    for user in users:
        username, email, permissao, created_at, nome_completo, telefone, endereco, \
        data_aniversario, data_iniciacao, data_elevacao, data_exaltacao, \
        data_instalacao_posse, observacoes, redes_sociais = user
        
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                nome_display = nome_completo or username
                st.write(f"**{nome_display}**")
                st.write(f"👤 {username} | 📧 {email or 'Não informado'} | 🏷️ {PERMISSOES.get(permissao, permissao)}")
                if telefone:
                    st.write(f"📞 {telefone}")
                if data_aniversario:
                    st.write(f"🎂 {data_aniversario.strftime('%d/%m/%Y')}")
            
            with col2:
                if st.button("✏️ Editar", key=f"edit_{username}"):
                    st.session_state.editing_user = username
                    st.rerun()
            
            with col3:
                if username != st.session_state.username:  # Não permitir excluir a si mesmo
                    if st.button("🗑️ Excluir", key=f"del_{username}"):
                        if delete_user(username):
                            st.rerun()
                else:
                    st.write("👆 Você")
            
            st.markdown("---")

def show_editar_usuario(username):
    """Formulário para editar usuário"""
    st.subheader(f"✏️ Editando Usuário: {username}")
    
    user_data = get_user_by_username(username)
    if not user_data:
        st.error("❌ Usuário não encontrado")
        st.session_state.editing_user = None
        return
    
    # Extrair dados do usuário
    (username, email, permissao, created_at, nome_completo, telefone, endereco,
     data_aniversario, data_iniciacao, data_elevacao, data_exaltacao,
     data_instalacao_posse, observacoes, redes_sociais) = user_data
    
    with st.form("editar_usuario"):
        col1, col2 = st.columns(2)
        
        with col1:
            novo_email = st.text_input("E-mail:", value=email or "", placeholder="email@exemplo.com")
            nova_permissao = st.selectbox(
                "Permissão:",
                list(PERMISSOES.keys()),
                index=list(PERMISSOES.keys()).index(permissao) if permissao in PERMISSOES else 0,
                format_func=lambda x: PERMISSOES[x]
            )
            novo_nome_completo = st.text_input("Nome Completo:", value=nome_completo or "", placeholder="Nome completo")
            novo_telefone = st.text_input("Telefone:", value=telefone or "", placeholder="(00) 00000-0000")
            novo_endereco = st.text_area("Endereço:", value=endereco or "", placeholder="Endereço completo")
            nova_data_aniversario = st.date_input(
                "Data de Aniversário:",
                value=data_aniversario if data_aniversario else None
            )
        
        with col2:
            # Campos de datas maçônicas
            nova_data_iniciacao = st.date_input(
                "Data de Iniciação:",
                value=data_iniciacao if data_iniciacao else None
            )
            nova_data_elevacao = st.date_input(
                "Data de Elevação:",
                value=data_elevacao if data_elevacao else None
            )
            nova_data_exaltacao = st.date_input(
                "Data de Exaltação:",
                value=data_exaltacao if data_exaltacao else None
            )
            nova_data_instalacao_posse = st.date_input(
                "Data de Instalação/Posse:",
                value=data_instalacao_posse if data_instalacao_posse else None
            )
        
        novas_observacoes = st.text_area("Observações:", value=observacoes or "", placeholder="Observações adicionais")
        novas_redes_sociais = st.text_input("Redes Sociais:", value=redes_sociais or "", placeholder="Links ou @ das redes sociais")
        
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        
        with col_btn1:
            submitted = st.form_submit_button("💾 Salvar Alterações")
        
        with col_btn2:
            if st.form_submit_button("🔄 Redefinir Senha"):
                # Para redefinir senha, vamos usar um modal simples
                nova_senha = st.text_input("Nova Senha:", type="password", key="nova_senha")
                if nova_senha:
                    if change_password(username, nova_senha):
                        st.success("✅ Senha alterada com sucesso!")
        
        with col_btn3:
            if st.form_submit_button("❌ Cancelar"):
                st.session_state.editing_user = None
                st.rerun()
        
        if submitted:
            success, message = update_user(
                username=username,
                email=novo_email or None,
                permissao=nova_permissao,
                nome_completo=novo_nome_completo or None,
                telefone=novo_telefone or None,
                endereco=novo_endereco or None,
                data_aniversario=nova_data_aniversario,
                data_iniciacao=nova_data_iniciacao,
                data_elevacao=nova_data_elevacao,
                data_exaltacao=nova_data_exaltacao,
                data_instalacao_posse=nova_data_instalacao_posse,
                observacoes=novas_observacoes or None,
                redes_sociais=novas_redes_sociais or None
            )
            
            if success:
                st.success(message)
                st.session_state.editing_user = None
                st.rerun()
            else:
                st.error(f"❌ {message}")

# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    main()
