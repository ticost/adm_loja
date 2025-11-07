# app.py - SISTEMA COMPLETO LIVRO CAIXA COM USUARIOS EXPANDIDOS E BACKUP
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
# PÁGINAS E INTERFACE (LOGIN, SIDEBAR, MENU)
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
    "💾 Exportar Dados",
    "💽 Criar Backup"
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
        - ✅ **Backup Completo**: Criação de backups completos do sistema
        """)
    with col2:
        st.subheader("💡 Dicas")
        st.markdown("Use as permissões para controlar quem edita e quem apenas visualiza.")

# ----------------------------
# PÁGINA: GERENCIAR USUÁRIOS (COM EDIÇÃO COMPLETA)
# ----------------------------
elif pagina == "👥 Gerenciar Usuários":
    st.title("👥 Gerenciar Usuários")

    if not user_is_admin():
        st.error("❌ Acesso restrito - Apenas administradores podem gerenciar usuários")
        st.stop()

    tab1, tab2, tab3, tab4 = st.tabs(["➕ Criar Usuário", "✏️ Editar Usuários", "👁️ Visualizar Usuários", "🗑️ Excluir Usuários"])

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
                
                # DATAS COM RANGE AMPLIADO
                data_aniversario = st.date_input(
                    "Data de Aniversário (opcional)", 
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31)
                )
                
                data_iniciacao = st.date_input(
                    "Data de Iniciação (opcional)", 
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31)
                )
                
                data_elevacao = st.date_input(
                    "Data de Elevação (opcional)", 
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31)
                )
                
                data_exaltacao = st.date_input(
                    "Data de Exaltação (opcional)", 
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31)
                )
                
                data_instalacao_posse = st.date_input(
                    "Data de Instalação/Posse (opcional)", 
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31)
                )
                
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
        st.subheader("✏️ Editar Usuários")
        
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
                nome_completo = user[4] or ""
                telefone = user[5] or ""
                endereco = user[6] or ""
                data_aniversario = user[7]
                data_iniciacao = user[8]
                data_elevacao = user[9]
                data_exaltacao = user[10]
                data_instalacao_posse = user[11]
                observacoes = user[12] or ""
                redes_sociais = user[13] or ""
                
                # Criar container para cada usuário
                with st.expander(f"✏️ Editar {username}", expanded=False):
                    with st.form(f"form_editar_{username}_{i}"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Editando usuário:** {username}")
                            novo_email = st.text_input("E-mail", value=email or "", key=f"email_{username}_{i}")
                            nova_permissao = st.selectbox(
                                "Permissão",
                                options=list(PERMISSOES.keys()),
                                index=list(PERMISSOES.keys()).index(permissao_atual) if permissao_atual in PERMISSOES else 0,
                                key=f"perm_{username}_{i}"
                            )
                            novo_nome_completo = st.text_input("Nome Completo", value=nome_completo, key=f"nome_{username}_{i}")
                            novo_telefone = st.text_input("Telefone", value=telefone, key=f"tel_{username}_{i}")
                            novo_endereco = st.text_area("Endereço", value=endereco, key=f"end_{username}_{i}")
                        
                        with col2:
                            nova_data_aniversario = st.date_input(
                                "Data de Aniversário",
                                value=data_aniversario,
                                min_value=date(1900, 1, 1),
                                max_value=date(2100, 12, 31),
                                key=f"aniv_{username}_{i}"
                            )
                            nova_data_iniciacao = st.date_input(
                                "Data de Iniciação",
                                value=data_iniciacao,
                                min_value=date(1900, 1, 1),
                                max_value=date(2100, 12, 31),
                                key=f"inic_{username}_{i}"
                            )
                            nova_data_elevacao = st.date_input(
                                "Data de Elevação",
                                value=data_elevacao,
                                min_value=date(1900, 1, 1),
                                max_value=date(2100, 12, 31),
                                key=f"elev_{username}_{i}"
                            )
                            nova_data_exaltacao = st.date_input(
                                "Data de Exaltação",
                                value=data_exaltacao,
                                min_value=date(1900, 1, 1),
                                max_value=date(2100, 12, 31),
                                key=f"exal_{username}_{i}"
                            )
                            nova_data_instalacao_posse = st.date_input(
                                "Data de Instalação/Posse",
                                value=data_instalacao_posse,
                                min_value=date(1900, 1, 1),
                                max_value=date(2100, 12, 31),
                                key=f"inst_{username}_{i}"
                            )
                            novas_observacoes = st.text_area("Observações", value=observacoes, key=f"obs_{username}_{i}")
                            novas_redes_sociais = st.text_input("Redes Sociais", value=redes_sociais, key=f"redes_{username}_{i}")
                        
                        # Botão de atualização
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.form_submit_button("💾 Atualizar Usuário", use_container_width=True):
                                if username != st.session_state.username:
                                    success, message = update_user(
                                        username=username,
                                        email=novo_email if novo_email != email else None,
                                        permissao=nova_permissao if nova_permissao != permissao_atual else None,
                                        nome_completo=novo_nome_completo if novo_nome_completo != nome_completo else None,
                                        telefone=novo_telefone if novo_telefone != telefone else None,
                                        endereco=novo_endereco if novo_endereco != endereco else None,
                                        data_aniversario=nova_data_aniversario if nova_data_aniversario != data_aniversario else None,
                                        data_iniciacao=nova_data_iniciacao if nova_data_iniciacao != data_iniciacao else None,
                                        data_elevacao=nova_data_elevacao if nova_data_elevacao != data_elevacao else None,
                                        data_exaltacao=nova_data_exaltacao if nova_data_exaltacao != data_exaltacao else None,
                                        data_instalacao_posse=nova_data_instalacao_posse if nova_data_instalacao_posse != data_instalacao_posse else None,
                                        observacoes=novas_observacoes if novas_observacoes != observacoes else None,
                                        redes_sociais=novas_redes_sociais if novas_redes_sociais != redes_sociais else None
                                    )
                                    if success:
                                        st.success(f"✅ Usuário {username} atualizado com sucesso!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {message}")
                                else:
                                    st.warning("⚠️ Você não pode editar seu próprio usuário aqui. Use a opção 'Alterar Senha' na sidebar.")
                        
                        with col_btn2:
                            if st.form_submit_button("🔄 Redefinir Senha", use_container_width=True):
                                if username != st.session_state.username:
                                    nova_senha = "123456"  # Senha padrão
                                    success, message = change_password(username, nova_senha)
                                    if success:
                                        st.success(f"✅ Senha de {username} redefinida para '123456'")
                                    else:
                                        st.error(f"❌ {message}")
                                else:
                                    st.warning("⚠️ Você não pode redefinir sua própria senha aqui. Use a opção 'Alterar Senha' na sidebar.")

    with tab3:
        st.subheader("👁️ Visualizar Usuários")
        
        # Buscar usuários
        users = get_all_users()
        
        if not users:
            st.info("📭 Nenhum usuário cadastrado no sistema.")
        else:
            # Criar DataFrame para exibição
            df_usuarios = pd.DataFrame(users, columns=[
                "Username", "Email", "Permissão", "Data Criação",
                "Nome Completo", "Telefone", "Endereço",
                "Data Aniversário", "Data Iniciação", "Data Elevação",
                "Data Exaltação", "Data Instalação/Posse", "Observações", "Redes Sociais"
            ])
            
            # Formatar datas
            date_columns = ["Data Criação", "Data Aniversário", "Data Iniciação", "Data Elevação", "Data Exaltação", "Data Instalação/Posse"]
            for col in date_columns:
                if col in df_usuarios.columns:
                    df_usuarios[col] = pd.to_datetime(df_usuarios[col], errors='coerce').dt.strftime('%d/%m/%Y')
            
            # Exibir tabela
            st.dataframe(df_usuarios, use_container_width=True, hide_index=True)
            
            # Estatísticas
            st.subheader("📊 Estatísticas de Usuários")
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

    with tab4:
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

# ----------------------------
# PÁGINA: LANÇAMENTOS
# ----------------------------
elif pagina == "📥 Lançamentos":
    st.title("📥 Lançamentos do Caixa")
    meses = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    col1, col2 = st.columns([1, 3])
    with col1:
        mes_selecionado = st.selectbox("Selecione o Mês", meses)
    with col2:
        st.info(f"Trabalhando no mês de {mes_selecionado}")
        if not user_can_edit():
            st.warning("Modo de Visualização - Você pode apenas visualizar os lançamentos.")

    df_mes = get_lancamentos_mes(mes_selecionado)

    if user_can_edit():
        st.subheader("➕ Adicionar Lançamento")
        with st.form("form_lancamento", clear_on_submit=True):
            col3, col4, col5 = st.columns([2, 2, 1])
            with col3:
                data = st.date_input(
                    "Data", 
                    datetime.now().date(),
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31)
                )
                historico = st.text_input("Histórico", placeholder="Descrição do lançamento...")
            with col4:
                complemento = st.text_input("Complemento", placeholder="Informações adicionais...")
                tipo_movimento = st.selectbox("Tipo de Movimento", ["Entrada", "Saída"])
            with col5:
                if tipo_movimento == "Entrada":
                    entrada = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f")
                    saida = 0.0
                else:
                    saida = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f")
                    entrada = 0.0
            submitted = st.form_submit_button("💾 Salvar Lançamento", use_container_width=True)
            if submitted and historico:
                if df_mes.empty:
                    saldo = entrada - saida
                else:
                    if 'saldo' in df_mes.columns and len(df_mes) > 0:
                        saldo_anterior = df_mes.iloc[-1]['saldo']
                    else:
                        saldo_anterior = 0.0
                    saldo = saldo_anterior + entrada - saida
                salvar_lancamento(mes_selecionado, data, historico, complemento, entrada, saida, saldo)
                st.rerun()
    else:
        st.info("Para adicionar ou editar lançamentos, solicite permissão de edição ao administrador.")

    st.subheader(f"📋 Lançamentos - {mes_selecionado}")
    if not df_mes.empty:
        colunas_mapeadas = {
            'id': 'ID',
            'data': 'DATA',
            'historico': 'HISTÓRICO',
            'complemento': 'COMPLEMENTO',
            'entrada': 'ENTRADA',
            'saida': 'SAÍDA',
            'saldo': 'SALDO'
        }
        colunas_existentes = [col for col in colunas_mapeadas.keys() if col in df_mes.columns]
        if colunas_existentes:
            df_exibir = df_mes[colunas_existentes].copy()
            df_exibir.columns = [colunas_mapeadas[col] for col in colunas_existentes]
            df_exibir_display = df_exibir.copy()
            if 'DATA' in df_exibir_display.columns:
                df_exibir_display['DATA'] = pd.to_datetime(df_exibir_display['DATA']).dt.strftime('%d/%m/%Y')
            if 'ENTRADA' in df_exibir_display.columns:
                df_exibir_display['ENTRADA'] = df_exibir_display['ENTRADA'].apply(lambda x: f"R$ {x:,.2f}" if x > 0 else "")
            if 'SAÍDA' in df_exibir_display.columns:
                df_exibir_display['SAÍDA'] = df_exibir_display['SAÍDA'].apply(lambda x: f"R$ {x:,.2f}" if x > 0 else "")
            if 'SALDO' in df_exibir_display.columns:
                df_exibir_display['SALDO'] = df_exibir_display['SALDO'].apply(lambda x: f"R$ {x:,.2f}")
            st.dataframe(df_exibir_display, use_container_width=True, hide_index=True)

            st.subheader("📥 Download do Mês")
            csv_data = download_csv_mes(mes_selecionado)
            if csv_data:
                st.download_button(
                    label=f"💾 Baixar {mes_selecionado} em CSV",
                    data=csv_data,
                    file_name=f"livro_caixa_{mes_selecionado}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            if user_can_edit():
                st.subheader("✏️ Gerenciar Lançamentos")
                if 'ID' in df_exibir.columns:
                    lancamentos_opcoes = []
                    for idx, row in df_exibir.iterrows():
                        valor = row['ENTRADA'] if row['ENTRADA'] > 0 else row['SAÍDA']
                        descricao = f"{row['DATA']} - {row['HISTÓRICO']} - R$ {valor:,.2f}"
                        lancamentos_opcoes.append((row['ID'], descricao))
                    if lancamentos_opcoes:
                        lancamento_selecionado = st.selectbox(
                            "Selecione o lançamento para editar/excluir:",
                            options=lancamentos_opcoes,
                            format_func=lambda x: x[1]
                        )
                        if lancamento_selecionado:
                            lancamento_id = lancamento_selecionado[0]
                            lancamento_data = df_exibir[df_exibir['ID'] == lancamento_id].iloc[0]
                            col_edit, col_del = st.columns([3, 1])
                            with col_edit:
                                with st.form("form_editar_lancamento"):
                                    st.write("Editar Lançamento:")
                                    col6, col7, col8 = st.columns([2, 2, 1])
                                    with col6:
                                        try:
                                            data_editar = st.date_input(
                                                "Data",
                                                value=datetime.strptime(str(lancamento_data['DATA']), '%Y-%m-%d').date()
                                                if isinstance(lancamento_data['DATA'], str)
                                                else lancamento_data['DATA'].date(),
                                                min_value=date(1900, 1, 1),
                                                max_value=date(2100, 12, 31)
                                            )
                                        except Exception:
                                            data_editar = st.date_input(
                                                "Data", 
                                                value=datetime.now().date(),
                                                min_value=date(1900, 1, 1),
                                                max_value=date(2100, 12, 31)
                                            )
                                        historico_editar = st.text_input("Histórico", value=lancamento_data['HISTÓRICO'])
                                    with col7:
                                        complemento_editar = st.text_input("Complemento", value=lancamento_data['COMPLEMENTO'] if pd.notna(lancamento_data['COMPLEMENTO']) else "")
                                        if lancamento_data['ENTRADA'] > 0:
                                            entrada_editar = st.number_input("Valor Entrada (R$)", value=float(lancamento_data['ENTRADA']), min_value=0.0, step=0.01, format="%.2f")
                                            saida_editar = 0.0
                                        else:
                                            saida_editar = st.number_input("Valor Saída (R$)", value=float(lancamento_data['SAÍDA']), min_value=0.0, step=0.01, format="%.2f")
                                            entrada_editar = 0.0
                                    with col8:
                                        submitted_editar = st.form_submit_button("💾 Atualizar", use_container_width=True)
                                    if submitted_editar and historico_editar:
                                        if atualizar_lancamento(lancamento_id, mes_selecionado, data_editar, historico_editar, complemento_editar, entrada_editar, saida_editar):
                                            st.success("✅ Lançamento atualizado com sucesso!")
                                            st.rerun()
                            with col_del:
                                st.write("Excluir:")
                                if st.button("🗑️ Excluir", use_container_width=True, type="secondary"):
                                    if st.checkbox("✅ Confirmar exclusão"):
                                        if excluir_lancamento(lancamento_id, mes_selecionado):
                                            st.success("✅ Lançamento excluído com sucesso!")
                                            st.rerun()
            # Estatísticas do mês
            st.subheader("📊 Estatísticas do Mês")
            col9, col10, col11 = st.columns(3)
            total_entradas = df_mes['entrada'].sum() if 'entrada' in df_mes.columns else 0.0
            total_saidas = df_mes['saida'].sum() if 'saida' in df_mes.columns else 0.0
            if 'saldo' in df_mes.columns and len(df_mes) > 0:
                saldo_atual = df_mes.iloc[-1]['saldo']
            else:
                saldo_atual = 0.0
            with col9:
                st.metric("💰 Total de Entradas", f"R$ {total_entradas:,.2f}")
            with col10:
                st.metric("💸 Total de Saídas", f"R$ {total_saidas:,.2f}")
            with col11:
                st.metric("🏦 Saldo Atual", f"R$ {saldo_atual:,.2f}")
        else:
            st.warning("⚠️ Estrutura de dados incompatível.")
            st.dataframe(df_mes, use_container_width=True)
    else:
        st.info(f"📭 Nenhum lançamento encontrado para {mes_selecionado}")
    if user_can_edit():
        if st.button(f"🗑️ Limpar TODOS os Lançamentos de {mes_selecionado}", use_container_width=True, type="secondary"):
            if st.checkbox("✅ Confirmar exclusão de TODOS os lançamentos"):
                limpar_lancamentos_mes(mes_selecionado)
                st.rerun()

# ----------------------------
# PÁGINA: CALENDÁRIO
# ----------------------------
elif pagina == "📅 Calendário":
    st.title("📅 Calendário Programável")
    hoje = date.today()
    if 'calendario_ano' not in st.session_state:
        st.session_state.calendario_ano = hoje.year
    if 'calendario_mes' not in st.session_state:
        st.session_state.calendario_mes = hoje.month
    col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 2, 1, 1])
    with col_nav1:
        if st.button("⏮️ Mês Anterior", use_container_width=True):
            if st.session_state.calendario_mes == 1:
                st.session_state.calendario_ano -= 1
                st.session_state.calendario_mes = 12
            else:
                st.session_state.calendario_mes -= 1
            st.rerun()
    with col_nav2:
        st.subheader(f"{calendar.month_name[st.session_state.calendario_mes]} de {st.session_state.calendario_ano}")
    with col_nav3:
        if st.button("⏭️ Próximo Mês", use_container_width=True):
            if st.session_state.calendario_mes == 12:
                st.session_state.calendario_ano += 1
                st.session_state.calendario_mes = 1
            else:
                st.session_state.calendario_mes += 1
            st.rerun()
    with col_nav4:
        if st.button("📅 Hoje", use_container_width=True):
            st.session_state.calendario_ano = hoje.year
            st.session_state.calendario_mes = hoje.month
            st.rerun()
    eventos_mes = get_eventos_mes(st.session_state.calendario_ano, st.session_state.calendario_mes)
    calendario = gerar_calendario(st.session_state.calendario_ano, st.session_state.calendario_mes)
    st.markdown("---")
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    cols = st.columns(7)
    for i, dia in enumerate(dias_semana):
        with cols[i]:
            st.markdown(f'<div style="text-align: center; font-weight: bold; padding: 10px; background-color: #f0f2f6; border-radius: 5px;">{dia}</div>', unsafe_allow_html=True)
    for semana in calendario:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            with cols[i]:
                if dia:
                    eventos_dia = eventos_mes[eventos_mes['data_evento'] == dia.strftime('%Y-%m-%d')]
                    tem_eventos = len(eventos_dia) > 0
                    estilo_dia = "background-color: #e6f3ff; border: 2px solid #1f77b4;" if dia == hoje else "border: 1px solid #ddd;"
                    st.markdown(
                        f'<div style="{estilo_dia} padding: 10px; margin: 2px; border-radius: 5px; text-align: center; min-height: 80px;">'
                        f'<strong>{dia.day}</strong>'
                        f"{'<br><span style=\"color: red; font-size: 12px;\">●</span>' if tem_eventos else ''}"
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    if st.button(f"Selecionar", key=f"dia_{dia}", use_container_width=True):
                        st.session_state.dia_selecionado = dia
                else:
                    st.markdown('<div style="padding: 10px; margin: 2px; border-radius: 5px; min-height: 80px;"></div>', unsafe_allow_html=True)
    st.markdown("---")
    col_esq, col_dir = st.columns([1, 1])
    with col_esq:
        st.subheader("➕ Adicionar Evento")
        with st.form("form_evento", clear_on_submit=True):
            titulo = st.text_input("Título do Evento", placeholder="Reunião, Pagamento, Compromisso...")
            descricao = st.text_area("Descrição", placeholder="Detalhes do evento...")
            col_data, col_hora = st.columns(2)
            with col_data:
                data_evento = st.date_input(
                    "Data do Evento", 
                    value=st.session_state.get('dia_selecionado', hoje),
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31)
                )
            with col_hora:
                hora_evento = st.time_input("Hora do Evento", value=datetime.now().time())
            tipo_evento = st.selectbox("Tipo de Evento", options=["Reunião", "Pagamento", "Compromisso", "Lembrete", "Outro"])
            cor_evento = st.color_picker("Cor do Evento", value="#1f77b4")
            submitted = st.form_submit_button("💾 Salvar Evento", use_container_width=True)
            if submitted and titulo:
                if salvar_evento(titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento):
                    st.rerun()
            elif submitted and not titulo:
                st.warning("Por favor, insira um título para o evento.")
    with col_dir:
        st.subheader("📋 Eventos do Mês")
        if not eventos_mes.empty:
            for _, evento in eventos_mes.iterrows():
                hora_exibicao = ""
                if evento['hora_evento']:
                    try:
                        if isinstance(evento['hora_evento'], str):
                            hora_obj = datetime.strptime(evento['hora_evento'], '%H:%M:%S').time()
                            hora_exibicao = hora_obj.strftime('%H:%M')
                        else:
                            hora_exibicao = str(evento['hora_evento'])
                    except:
                        hora_exibicao = str(evento['hora_evento'])
                display_text = f"📅 {evento['titulo']} - {evento['data_evento']}"
                if hora_exibicao:
                    display_text += f" {hora_exibicao}"
                with st.expander(display_text):
                    st.write(f"**Descrição:** {evento['descricao']}")
                    if hora_exibicao:
                        st.write(f"**Hora:** {hora_exibicao}")
                    st.write(f"**Tipo:** {evento['tipo_evento']}")
                    st.write(f"**Criado por:** {evento['created_by']}")
                    pode_gerenciar = (user_is_admin() or evento['created_by'] == st.session_state.username)
                    if pode_gerenciar:
                        col_edit_ev, col_del_ev = st.columns(2)
                        with col_edit_ev:
                            if st.button("✏️ Editar", key=f"edit_{evento['id']}", use_container_width=True):
                                st.session_state.editando_evento = evento['id']
                                st.rerun()
                        with col_del_ev:
                            if st.button("🗑️ Excluir", key=f"del_{evento['id']}", use_container_width=True):
                                if excluir_evento(evento['id']):
                                    st.rerun()
                    else:
                        st.info("Apenas o criador do evento ou administrador pode editá-lo.")
    if 'editando_evento' in st.session_state:
        st.markdown("---")
        st.subheader("✏️ Editar Evento")
        evento_id = st.session_state.editando_evento
        evento_data = eventos_mes[eventos_mes['id'] == evento_id].iloc[0]
        pode_editar = (user_is_admin() or evento_data['created_by'] == st.session_state.username)
        if pode_editar:
            hora_evento_existente = evento_data['hora_evento']
            if isinstance(hora_evento_existente, str):
                try:
                    hora_evento_existente = datetime.strptime(hora_evento_existente, '%H:%M:%S').time()
                except:
                    hora_evento_existente = datetime.now().time()
            with st.form("form_editar_evento"):
                titulo_edit = st.text_input("Título do Evento", value=evento_data['titulo'])
                descricao_edit = st.text_area("Descrição", value=evento_data['descricao'])
                col_data_edit, col_hora_edit = st.columns(2)
                with col_data_edit:
                    data_evento_edit = st.date_input(
                        "Data do Evento",
                        value=datetime.strptime(evento_data['data_evento'], '%Y-%m-%d').date(),
                        min_value=date(1900, 1, 1),
                        max_value=date(2100, 12, 31)
                    )
                with col_hora_edit:
                    hora_evento_edit = st.time_input("Hora do Evento", value=hora_evento_existente)
                tipo_evento_edit = st.selectbox("Tipo de Evento",
                                                options=["Reunião", "Pagamento", "Compromisso", "Lembrete", "Outro"],
                                                index=["Reunião", "Pagamento", "Compromisso", "Lembrete", "Outro"].index(evento_data['tipo_evento']) if evento_data['tipo_evento'] in ["Reunião", "Pagamento", "Compromisso", "Lembrete", "Outro"] else 0)
                cor_evento_edit = st.color_picker("Cor do Evento", value=evento_data['cor_evento'])
                col_salvar, col_cancelar = st.columns(2)
                with col_salvar:
                    submitted_edit = st.form_submit_button("💾 Atualizar Evento", use_container_width=True)
                with col_cancelar:
                    if st.form_submit_button("❌ Cancelar", use_container_width=True):
                        del st.session_state.editando_evento
                        st.rerun()
                if submitted_edit and titulo_edit:
                    if atualizar_evento(evento_id, titulo_edit, descricao_edit, data_evento_edit, hora_evento_edit, tipo_evento_edit, cor_evento_edit):
                        del st.session_state.editando_evento
                        st.rerun()
                elif submitted_edit and not titulo_edit:
                    st.warning("Por favor, insira um título para o evento.")
        else:
            st.error("Você não tem permissão para editar este evento.")
            if st.button("⬅️ Voltar"):
                del st.session_state.editando_evento
                st.rerun()

# ----------------------------
# PÁGINA: BALANÇO FINANCEIRO
# ----------------------------
elif pagina == "📈 Balanço Financeiro":
    st.title("📈 Balanço Financeiro")
    total_entradas_anual = 0.0
    total_saidas_anual = 0.0
    dados_mensais = []
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    with st.spinner("📊 Calculando balanço..."):
        for mes in meses:
            df_mes = get_lancamentos_mes(mes)
            if not df_mes.empty:
                entradas_mes = df_mes['entrada'].sum() if 'entrada' in df_mes.columns else 0.0
                saidas_mes = df_mes['saida'].sum() if 'saida' in df_mes.columns else 0.0
                if 'saldo' in df_mes.columns and len(df_mes) > 0:
                    saldo_mes = df_mes.iloc[-1]['saldo']
                else:
                    saldo_mes = 0.0
                total_entradas_anual += entradas_mes
                total_saidas_anual += saidas_mes
                dados_mensais.append({
                    'Mês': mes,
                    'Entradas': entradas_mes,
                    'Saídas': saidas_mes,
                    'Saldo': saldo_mes
                })
    saldo_final_anual = total_entradas_anual - total_saidas_anual
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📥 Débitos")
        st.metric("Total de Entradas Anual", f"R$ {total_entradas_anual:,.2f}")
        st.subheader("Resumo por Mês")
        for dados in dados_mensais:
            with st.expander(f"{dados['Mês']}"):
                st.write(f"Entradas: R$ {dados['Entradas']:,.2f}")
                st.write(f"Saídas: R$ {dados['Saídas']:,.2f}")
                st.write(f"Saldo: R$ {dados['Saldo']:,.2f}")
    with col2:
        st.subheader("📤 Créditos")
        st.metric("Total de Saídas Anual", f"R$ {total_saidas_anual:,.2f}")
        st.metric("Saldo Final Anual", f"R$ {saldo_final_anual:,.2f}", delta=f"R$ {saldo_final_anual:,.2f}")
        if dados_mensais:
            st.subheader("📊 Resumo Visual")
            df_grafico = pd.DataFrame(dados_mensais)
            st.bar_chart(df_grafico.set_index('Mês')[['Entradas', 'Saídas']], use_container_width=True)

# ----------------------------
# PÁGINA: EXPORTAR DADOS
# ----------------------------
elif pagina == "💾 Exportar Dados":
    st.title("💾 Exportar Dados")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📤 Exportar Dados")
        st.info("Os arquivos CSV podem ser abertos diretamente no Excel")
        st.subheader("📥 Download por Mês")
        meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                 "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_download = st.selectbox("Selecione o mês para download:", meses)
        csv_data = download_csv_mes(mes_download)
        if csv_data:
            st.download_button(
                label=f"💾 Baixar {mes_download} em CSV",
                data=csv_data,
                file_name=f"livro_caixa_{mes_download}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.warning(f"📭 Nenhum dado encontrado para {mes_download}")
        st.markdown("---")
        st.subheader("📦 Exportação Completa")
        if st.button("📦 Exportar Todos os Dados", use_container_width=True):
            with st.spinner("Gerando arquivo ZIP..."):
                output = exportar_para_csv()
                if output is not None:
                    st.download_button(
                        label="💾 Baixar Arquivo ZIP Completo",
                        data=output,
                        file_name=f"livro_caixa_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    st.success("✅ Arquivo ZIP gerado com sucesso!")
                else:
                    st.error("❌ Erro ao gerar arquivo de exportação")
    with col2:
        st.subheader("📊 Informações do Sistema")
        conn = get_db_connection()
        try:
            if conn:
                total_lancamentos = pd.read_sql("SELECT COUNT(*) as total FROM lancamentos", conn).iloc[0]['total']
                total_contas = pd.read_sql("SELECT COUNT(*) as total FROM contas", conn).iloc[0]['total']
                meses_com_dados = pd.read_sql("SELECT COUNT(DISTINCT mes) as total FROM lancamentos", conn).iloc[0]['total']
                total_eventos = pd.read_sql("SELECT COUNT(*) as total FROM eventos_calendario", conn).iloc[0]['total']
                total_usuarios = pd.read_sql("SELECT COUNT(*) as total FROM usuarios", conn).iloc[0]['total']
            else:
                total_lancamentos = 0
                total_contas = 0
                meses_com_dados = 0
                total_eventos = 0
                total_usuarios = 0
        except:
            total_lancamentos = 0
            total_contas = 0
            meses_com_dados = 0
            total_eventos = 0
            total_usuarios = 0
        finally:
            if conn:
                conn.close()
        st.metric("Total de Lançamentos", total_lancamentos)
        st.metric("Total de Contas", total_contas)
        st.metric("Meses com Dados", meses_com_dados)
        st.metric("Total de Eventos", total_eventos)
        st.metric("Total de Usuários", total_usuarios)
        st.info("""
        Informações:
        - Banco de Dados: PlanetScale (MySQL)
        - Dados: Persistidos na nuvem
        - Exportação: CSV compatível com Excel
        - Segurança: Acesso por login
        """)

# ----------------------------
# PÁGINA: CRIAR BACKUP
# ----------------------------
elif pagina == "💽 Criar Backup":
    st.title("💽 Criar Backup do Sistema")
    
    st.info("""
    **📦 Sistema de Backup Completo**
    
    Esta funcionalidade permite criar backups completos de todos os dados do sistema,
    incluindo lançamentos, contas, eventos e informações de usuários (sem senhas).
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔒 Backup Completo")
        st.write("Cria um backup completo de todos os dados do sistema.")
        
        if st.button("📦 Criar Backup Completo", use_container_width=True):
            with st.spinner("Criando backup completo..."):
                backup_data = criar_backup_completo()
                if backup_data is not None:
                    st.download_button(
                        label="💾 Download Backup Completo",
                        data=backup_data,
                        file_name=f"backup_completo_livro_caixa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    st.success("✅ Backup completo criado com sucesso!")
                else:
                    st.error("❌ Erro ao criar backup completo")
    
    with col2:
        st.subheader("🔄 Backup Incremental")
        st.write("Cria backup apenas dos dados dos últimos 30 dias.")
        
        if st.button("🔄 Criar Backup Incremental", use_container_width=True):
            with st.spinner("Criando backup incremental..."):
                backup_data = criar_backup_incremental()
                if backup_data is not None:
                    st.download_button(
                        label="💾 Download Backup Incremental",
                        data=backup_data,
                        file_name=f"backup_incremental_livro_caixa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    st.success("✅ Backup incremental criado com sucesso!")
                else:
                    st.error("❌ Erro ao criar backup incremental")
    
    st.markdown("---")
    st.subheader("📋 Conteúdo dos Backups")
    
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.write("**Backup Completo inclui:**")
        st.markdown("""
        - ✅ Todos os lançamentos (organizados por mês)
        - ✅ Contas cadastradas
        - ✅ Eventos do calendário
        - ✅ Usuários (sem informações de senha)
        - ✅ Estrutura das tabelas (SQL)
        - ✅ Informações do sistema
        """)
    
    with col_info2:
        st.write("**Backup Incremental inclui:**")
        st.markdown("""
        - ✅ Lançamentos dos últimos 30 dias
        - ✅ Eventos dos últimos 30 dias
        - ✅ Informações do backup
        """)
    
    st.markdown("---")
    st.subheader("⚠️ Recomendações")
    st.warning("""
    - **Frequência:** Recomenda-se criar backups completos mensalmente
    - **Armazenamento:** Mantenha os backups em local seguro
    - **Teste:** Periodicamente, verifique se os backups estão íntegros
    - **Segurança:** Os backups não incluem senhas por motivos de segurança
    """)

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
