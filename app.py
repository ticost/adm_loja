# app.py - SISTEMA COMPLETO LIVRO CAIXA
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
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
    try:
        # Tenta diferentes caminhos possíveis
        caminhos_tentativos = [
            nome_arquivo,
            f"imagens/{nome_arquivo}",
            f"assets/{nome_arquivo}",
            f"static/{nome_arquivo}",
            f"../{nome_arquivo}",
            f"./{nome_arquivo}"
        ]
        
        for caminho in caminhos_tentativos:
            if os.path.exists(caminho):
                st.sidebar.image(caminho, use_column_width=True)
                return True
        
        # Se não encontrou, mostra placeholder
        st.sidebar.markdown("""
        <div style="text-align: center; padding: 20px; border: 2px dashed #ccc; border-radius: 10px;">
            <div style="font-size: 48px;">🏢</div>
            <div style="color: #666;">Logo da Loja</div>
        </div>
        """, unsafe_allow_html=True)
        return False
        
    except Exception as e:
        st.sidebar.info("💡 Para usar seu logo, adicione o arquivo 'Logo_Loja.png' na raiz do projeto")
        return False

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
        error_code = e.args[0]
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
# FUNÇÕES DE AUTENTICAÇÃO
# =============================================================================

# reset_db.py - APENAS PARA RESET EMERGENCIAL
import streamlit as st
import pymysql
import hashlib

def reset_database():
    st.title("🔄 Reset Emergencial do Banco")
    
    if "planetscale" not in st.secrets:
        st.error("❌ Secrets não encontrados")
        return
    
    if st.button("🚨 RESETAR BANCO COMPLETO", type="secondary"):
        if st.checkbox("✅ CONFIRMAR: Esta ação apagará TODOS os dados!"):
            try:
                conn = pymysql.connect(
                    host=st.secrets["planetscale"]["host"],
                    user=st.secrets["planetscale"]["user"],
                    password=st.secrets["planetscale"]["password"],
                    database=st.secrets["planetscale"]["database"],
                    ssl={'ca': '/etc/ssl/certs/ca-certificates.crt'}
                )
                
                cursor = conn.cursor()
                
                # Remover tabelas
                cursor.execute('DROP TABLE IF EXISTS eventos_calendario')
                cursor.execute('DROP TABLE IF EXISTS lancamentos')
                cursor.execute('DROP TABLE IF EXISTS contas')
                cursor.execute('DROP TABLE IF EXISTS usuarios')
                
                # Recriar tabelas corretamente
                # Tabela de usuários
                cursor.execute('''
                    CREATE TABLE usuarios (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        permissao ENUM('admin', 'editor', 'visualizador') NOT NULL DEFAULT 'visualizador',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Tabela de contas
                cursor.execute('''
                    CREATE TABLE contas (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        nome VARCHAR(100) UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Tabela de lançamentos
                cursor.execute('''
                    CREATE TABLE lancamentos (
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
                
                # Tabela de eventos
                cursor.execute('''
                    CREATE TABLE eventos_calendario (
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
                
                # Inserir usuários padrão
                password_hash_admin = hashlib.sha256('admin123'.encode()).hexdigest()
                cursor.execute(
                    'INSERT INTO usuarios (username, password_hash, permissao) VALUES (%s, %s, %s)', 
                    ('admin', password_hash_admin, 'admin')
                )
                
                password_hash_visual = hashlib.sha256('visual123'.encode()).hexdigest()
                cursor.execute(
                    'INSERT INTO usuarios (username, password_hash, permissao) VALUES (%s, %s, %s)', 
                    ('visual', password_hash_visual, 'visualizador')
                )
                
                conn.commit()
                conn.close()
                
                st.success("🎉 Banco resetado com sucesso!")
                st.info("👤 Usuários criados: admin/admin123 e visual/visual123")
                
            except Exception as e:
                st.error(f"❌ Erro no reset: {e}")

reset_database()

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

def get_all_users():
    """Busca todos os usuários (apenas admin)"""
    if not user_is_admin():
        return []
    
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT username, permissao, created_at FROM usuarios ORDER BY created_at')
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
    """Exclui usuário"""
    if not user_is_admin():
        return False, "Apenas administradores podem excluir usuários"
    
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
# FUNÇÕES DO SISTEMA PRINCIPAL
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
    """Busca todas as contas"""
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
    """Adiciona nova conta"""
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
    """Busca lançamentos do mês"""
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = 'SELECT * FROM lancamentos WHERE mes = %s ORDER BY data, id'
        df = pd.read_sql(query, conn, params=[mes])
        return df
    except Error:
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def salvar_lancamento(mes, data, historico, complemento, entrada, saida, saldo):
    """Salva novo lançamento"""
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
    """Atualiza lançamento existente"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Primeiro busca o lançamento atual para calcular novo saldo
        cursor.execute('SELECT * FROM lancamentos WHERE id = %s', (lancamento_id,))
        lancamento_antigo = cursor.fetchone()
        
        if not lancamento_antigo:
            st.error("❌ Lançamento não encontrado")
            return False
        
        # Atualiza o lançamento
        cursor.execute('''
            UPDATE lancamentos 
            SET data = %s, historico = %s, complemento = %s, entrada = %s, saida = %s
            WHERE id = %s
        ''', (data, historico, complemento, entrada, saida, lancamento_id))
        
        # Recalcula todos os saldos do mês
        cursor.execute('SELECT * FROM lancamentos WHERE mes = %s ORDER BY data, id', (mes,))
        lancamentos = cursor.fetchall()
        
        saldo_atual = 0.0
        for lanc in lancamentos:
            entrada_val = float(lanc[5]) if lanc[5] else 0.0
            saida_val = float(lanc[6]) if lanc[6] else 0.0
            saldo_atual += entrada_val - saida_val
            
            cursor.execute(
                'UPDATE lancamentos SET saldo = %s WHERE id = %s',
                (saldo_atual, lanc[0])
            )
        
        conn.commit()
        return True
    except Error as e:
        st.error(f"❌ Erro ao atualizar lançamento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def excluir_lancamento(lancamento_id, mes):
    """Exclui lançamento"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Exclui o lançamento
        cursor.execute('DELETE FROM lancamentos WHERE id = %s', (lancamento_id,))
        
        # Recalcula saldos dos lançamentos restantes
        cursor.execute('SELECT * FROM lancamentos WHERE mes = %s ORDER BY data, id', (mes,))
        lancamentos = cursor.fetchall()
        
        saldo_atual = 0.0
        for lanc in lancamentos:
            entrada_val = float(lanc[5]) if lanc[5] else 0.0
            saida_val = float(lanc[6]) if lanc[6] else 0.0
            saldo_atual += entrada_val - saida_val
            
            cursor.execute(
                'UPDATE lancamentos SET saldo = %s WHERE id = %s',
                (saldo_atual, lanc[0])
            )
        
        conn.commit()
        return True
    except Error as e:
        st.error(f"❌ Erro ao excluir lançamento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def limpar_lancamentos_mes(mes):
    """Limpa todos os lançamentos do mês"""
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
    """Busca eventos do mês"""
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
    except Error:
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def gerar_calendario(ano, mes):
    """Gera matriz do calendário"""
    cal = calendar.Calendar(firstweekday=6)  # Domingo como primeiro dia
    return cal.monthdatescalendar(ano, mes)

def salvar_evento(titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento):
    """Salva novo evento"""
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
    """Atualiza evento existente"""
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
    """Exclui evento"""
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
        st.error(f"❌ Erro ao excluir evento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def download_csv_mes(mes):
    """Gera CSV do mês"""
    df = get_lancamentos_mes(mes)
    if df.empty:
        return None
    
    return df.to_csv(index=False, encoding='utf-8')

def exportar_para_csv():
    """Exporta todos os dados para ZIP"""
    try:
        # Criar arquivo ZIP em memória
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            # Exportar lançamentos por mês
            meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            
            for mes in meses:
                df_mes = get_lancamentos_mes(mes)
                if not df_mes.empty:
                    csv_data = df_mes.to_csv(index=False, encoding='utf-8')
                    zip_file.writestr(f"lancamentos_{mes}.csv", csv_data)
            
            # Exportar contas
            conn = get_db_connection()
            if conn:
                try:
                    df_contas = pd.read_sql("SELECT * FROM contas", conn)
                    if not df_contas.empty:
                        csv_contas = df_contas.to_csv(index=False, encoding='utf-8')
                        zip_file.writestr("contas.csv", csv_contas)
                    
                    # Exportar eventos
                    df_eventos = pd.read_sql("SELECT * FROM eventos_calendario", conn)
                    if not df_eventos.empty:
                        csv_eventos = df_eventos.to_csv(index=False, encoding='utf-8')
                        zip_file.writestr("eventos.csv", csv_eventos)
                finally:
                    conn.close()
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    except Exception as e:
        st.error(f"❌ Erro na exportação: {e}")
        return None

# =============================================================================
# PÁGINA DE CONFIGURAÇÃO
# =============================================================================

def pagina_configuracao():
    st.title("⚙️ Configuração do Sistema")
    
    st.error("""
    ## ❌ Secrets não configurados
    
    Para usar o sistema, configure os Secrets no Streamlit Cloud.
    """)
    
    with st.expander("📋 Passos para configurar:", expanded=True):
        st.markdown("""
        1. **Acesse** [share.streamlit.io](https://share.streamlit.io)
        2. **Vá no seu app** → **Clique em 'Settings' (⚙️)**
        3. **Vá na aba "Secrets"**
        4. **Cole este conteúdo EXATAMENTE:**
        """)
        
        # SUAS CREDENCIAIS REAIS
        secrets_content = '''[planetscale]
host = "aws.connect.psdb.cloud"
user = "swyqb2mjfdr8mp6n9xap"
password = "pscale_pw_a1DZV8LeMzT4QmtBVzuPu4QDc4B4klcxUaplE0wKI6c"
database = "adm_loja"'''
        
        st.code(secrets_content, language='toml')
        
        st.markdown("""
        5. **Clique em Save**
        6. **Aguarde o app reiniciar automaticamente**
        """)
    
    # Testar configuração atual
    st.markdown("---")
    st.subheader("🧪 Testar Configuração Atual")
    
    if st.button("🔍 Verificar Secrets"):
        if "planetscale" in st.secrets:
            secrets = st.secrets["planetscale"]
            st.success("✅ Secrets encontrados!")
            st.write("**Configuração atual:**")
            for key, value in secrets.items():
                if key == "password":
                    st.write(f"- **{key}:** `{value[:10]}...`")
                else:
                    st.write(f"- **{key}:** `{value}`")
            
            # Testar conexão
            if st.button("🔗 Testar Conexão"):
                conn = get_db_connection()
                if conn:
                    st.success("🎉 Conexão bem-sucedida! O sistema está funcionando.")
                    
                    # Mostrar tabelas existentes
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SHOW TABLES")
                        tables = cursor.fetchall()
                        
                        st.write("**Tabelas no banco:**")
                        for table in tables:
                            st.write(f"- `{table[0]}`")
                            
                    except Exception as e:
                        st.error(f"Erro ao listar tabelas: {e}")
                    finally:
                        conn.close()
        else:
            st.error("❌ Nenhum secret 'planetscale' encontrado.")

# =============================================================================
# VERIFICAÇÃO INICIAL
# =============================================================================

# Verificar se os secrets estão configurados
if "planetscale" not in st.secrets:
    pagina_configuracao()
    st.stop()

# Se chegou aqui, os secrets existem - testar conexão
conn = get_db_connection()
if not conn:
    st.error("❌ Falha na conexão. Verifique as configurações.")
    pagina_configuracao()
    st.stop()
else:
    conn.close()

# =============================================================================
# INICIALIZAÇÃO DO SISTEMA
# =============================================================================

# Verificar se o usuário está logado
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.permissao = None

# Inicializar bancos de dados
init_db()
init_auth_db()

# =============================================================================
# PÁGINA DE LOGIN
# =============================================================================

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

# =============================================================================
# APLICAÇÃO PRINCIPAL (APENAS PARA USUÁRIOS LOGADOS)
# =============================================================================

# Sidebar com logo e informações do usuário
with st.sidebar:
    # Carrega a imagem do logo
    logo_carregado = carregar_imagem_logo("Logo_Loja.png")
    
    st.title("📒 Livro Caixa")
    
    # Informações do usuário logado
    st.sidebar.markdown("---")
    st.sidebar.success(f"👤 **Usuário:** {st.session_state.username}")
    st.sidebar.info(f"🔐 **Permissão:** {PERMISSOES.get(st.session_state.permissao, 'Desconhecida')}")
    
    # Botão de logout
    if st.sidebar.button("🚪 Sair", use_container_width=True):
        logout_user()
        st.rerun()
    
    # Alterar senha
    with st.sidebar.expander("🔑 Alterar Senha"):
        with st.form("change_password_form"):
            new_password = st.text_input("Nova Senha", type="password")
            confirm_password = st.text_input("Confirmar Senha", type="password")
            
            if st.form_submit_button("💾 Alterar Senha"):
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
    
    # Gerenciar usuários (apenas para admin)
    if user_is_admin():
        with st.sidebar.expander("👥 Gerenciar Usuários"):
            st.subheader("Usuários do Sistema")
            
            # Listar usuários existentes
            users = get_all_users()
            if users:
                st.write("**Usuários cadastrados:**")
                for i, (username, permissao, created_at) in enumerate(users, 1):
                    st.write(f"{i}. **{username}** - {PERMISSOES.get(permissao, 'Desconhecida')} - Criado em: {created_at}")
                
                st.markdown("---")
                
                # Editar permissões de usuário
                st.subheader("Editar Permissões")
                user_to_edit = st.selectbox(
                    "Selecione o usuário para editar:",
                    [user[0] for user in users if user[0] != 'admin']  # Não permitir editar admin
                )
                
                if user_to_edit:
                    # Buscar permissão atual do usuário
                    permissao_atual = next((user[1] for user in users if user[0] == user_to_edit), 'visualizador')
                    
                    nova_permissao = st.selectbox(
                        "Nova permissão:",
                        options=list(PERMISSOES.keys()),
                        index=list(PERMISSOES.keys()).index(permissao_atual),
                        format_func=lambda x: PERMISSOES[x]
                    )
                    
                    if st.button("💾 Atualizar Permissão", use_container_width=True):
                        if nova_permissao != permissao_atual:
                            success, message = update_user_permission(user_to_edit, nova_permissao)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                
                st.markdown("---")
                
                # Excluir usuário
                st.subheader("Excluir Usuário")
                user_to_delete = st.selectbox(
                    "Selecione o usuário para excluir:",
                    [user[0] for user in users if user[0] != st.session_state.username]
                )
                
                if user_to_delete:
                    if st.button("🗑️ Excluir Usuário", use_container_width=True):
                        if st.checkbox("✅ Confirmar exclusão do usuário"):
                            success, message = delete_user(user_to_delete)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
            else:
                st.info("Nenhum usuário cadastrado.")
    
    st.markdown("---")
    
    pagina = st.radio(
        "**Navegação:**",
        ["📋 Ajuda", "📝 Contas", "📥 Lançamentos", "📅 Calendário", "📈 Balanço Financeiro", "💾 Exportar Dados"],
        label_visibility="collapsed"
    )

# =============================================================================
# PÁGINA: AJUDA
# =============================================================================

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
        
        **📝 Nota:** Não se esqueça do saldo inicial em janeiro!
        """)
        
        st.markdown("---")
        st.subheader("🎯 Como Usar:")
        
        st.markdown("""
        1. **📝 Contas**: Configure suas contas personalizadas
        2. **📥 Lançamentos**: Adicione entradas e saídas por mês
        3. **📅 Calendário**: Agende eventos importantes
        4. **✏️ Editar**: Modifique ou exclua lançamentos existentes
        5. **📈 Balanço**: Veja relatórios e gráficos
        6. **📤 Exportar**: Faça backup dos dados
        """)
    
    with col2:
        st.subheader("💡 Dicas Importantes")
        
        st.markdown("""
        **💰 Movimentações:**
        - **Deposito em banco** → **Saída** do caixa
        - **Retirada do banco** → **Entrada** do caixa
        - **Pagamento** → **Saída** do caixa
        - **Recebimento** → **Entrada** do caixa
        
        **📅 Calendário:**
        - Agende pagamentos importantes
        - Marque reuniões e compromissos
        - Defina lembretes financeiros
        - Organize sua agenda
        """)
        
        # Informações sobre gerenciamento de usuários
        if user_is_admin():
            st.subheader("👥 Admin")
            st.markdown("""
            **Privilégios de administrador:**
            - Criar novos usuários
            - Excluir usuários
            - Ver todos os usuários
            - Gerenciar todo o sistema
            """)
        
        st.subheader("🔐 Sistema de Permissões")
        st.markdown("""
        **📊 Níveis de Permissão:**
        
        - **👑 Administrador**: Acesso completo a todas as funcionalidades
        - **✏️ Editor**: Pode adicionar, editar e excluir lançamentos e contas
        - **👀 Visualizador**: Apenas visualização de dados e relatórios
        """)

# =============================================================================
# PÁGINA: CONTAS
# =============================================================================

elif pagina == "📝 Contas":
    st.title("📝 Contas")
    
    # Buscar contas do banco
    contas = get_contas()
    
    if contas:
        st.subheader("📋 Contas Cadastradas")
        for i, conta in enumerate(contas, 1):
            st.write(f"{i}. **{conta}**")
    else:
        st.info("📭 Nenhuma conta cadastrada ainda.")
    
    # Apenas usuários com permissão de edição podem adicionar contas
    if user_can_edit():
        st.subheader("➕ Adicionar Nova Conta")
        
        nova_conta = st.text_input("**Nome da Nova Conta**", placeholder="Ex: Salários, Aluguel, Vendas...")
        
        if st.button("✅ Adicionar Conta", use_container_width=True) and nova_conta:
            adicionar_conta(nova_conta)
            st.rerun()
    else:
        st.info("👀 **Modo de Visualização** - Você pode apenas visualizar as contas existentes.")

# =============================================================================
# PÁGINA: LANÇAMENTOS
# =============================================================================

elif pagina == "📥 Lançamentos":
    st.title("📥 Lançamentos do Caixa")
    
    meses = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    
    # Layout responsivo para seleção de mês
    col1, col2 = st.columns([1, 3])
    
    with col1:
        mes_selecionado = st.selectbox("**Selecione o Mês**", meses)
    
    with col2:
        st.info(f"💼 Trabalhando no mês de **{mes_selecionado}**")
        if not user_can_edit():
            st.warning("👀 **Modo de Visualização** - Você pode apenas visualizar os lançamentos.")
    
    # Buscar lançamentos do banco
    df_mes = get_lancamentos_mes(mes_selecionado)
    
    # Apenas usuários com permissão de edição podem adicionar lançamentos
    if user_can_edit():
        st.subheader("➕ Adicionar Lançamento")
        
        # Layout responsivo para o formulário
        with st.form("form_lancamento", clear_on_submit=True):
            col3, col4, col5 = st.columns([2, 2, 1])
            
            with col3:
                data = st.date_input("**Data**", datetime.now().date())
                historico = st.text_input("**Histórico**", placeholder="Descrição do lançamento...")
            
            with col4:
                complemento = st.text_input("**Complemento**", placeholder="Informações adicionais...")
                tipo_movimento = st.selectbox("**Tipo de Movimento**", ["Entrada", "Saída"])
            
            with col5:
                if tipo_movimento == "Entrada":
                    entrada = st.number_input("**Valor (R$)**", min_value=0.0, step=0.01, format="%.2f")
                    saida = 0.0
                else:
                    saida = st.number_input("**Valor (R$)**", min_value=0.0, step=0.01, format="%.2f")
                    entrada = 0.0
            
            submitted = st.form_submit_button("💾 Salvar Lançamento", use_container_width=True)
            
            if submitted and historico:
                # Calcular saldo
                if df_mes.empty:
                    saldo = entrada - saida
                else:
                    # Verifica se a coluna saldo existe e tem dados
                    if 'saldo' in df_mes.columns and len(df_mes) > 0:
                        saldo_anterior = df_mes.iloc[-1]['saldo']
                    else:
                        saldo_anterior = 0.0
                    saldo = saldo_anterior + entrada - saida
                
                # Salvar no banco
                salvar_lancamento(mes_selecionado, data, historico, complemento, entrada, saida, saldo)
                st.rerun()
    else:
        st.info("💡 Para adicionar ou editar lançamentos, solicite permissão de edição ao administrador.")
    
    # Exibir lançamentos do mês com opção de edição
    st.subheader(f"📋 Lançamentos - {mes_selecionado}")
    
    if not df_mes.empty:
        # Mapear colunas do banco para os nomes exibidos
        colunas_mapeadas = {
            'id': 'ID',
            'data': 'DATA',
            'historico': 'HISTÓRICO', 
            'complemento': 'COMPLEMENTO',
            'entrada': 'ENTRADA',
            'saida': 'SAÍDA',
            'saldo': 'SALDO'
        }
        
        # Filtrar apenas colunas que existem no DataFrame
        colunas_existentes = [col for col in colunas_mapeadas.keys() if col in df_mes.columns]
        
        if colunas_existentes:
            df_exibir = df_mes[colunas_existentes].copy()
            
            # Renomear colunas para exibição
            df_exibir.columns = [colunas_mapeadas[col] for col in colunas_existentes]
            
            # Formatar colunas para exibição
            df_exibir_display = df_exibir.copy()
            if 'DATA' in df_exibir_display.columns:
                df_exibir_display['DATA'] = pd.to_datetime(df_exibir_display['DATA']).dt.strftime('%d/%m/%Y')
            if 'ENTRADA' in df_exibir_display.columns:
                df_exibir_display['ENTRADA'] = df_exibir_display['ENTRADA'].apply(lambda x: f"R$ {x:,.2f}" if x > 0 else "")
            if 'SAÍDA' in df_exibir_display.columns:
                df_exibir_display['SAÍDA'] = df_exibir_display['SAÍDA'].apply(lambda x: f"R$ {x:,.2f}" if x > 0 else "")
            if 'SALDO' in df_exibir_display.columns:
                df_exibir_display['SALDO'] = df_exibir_display['SALDO'].apply(lambda x: f"R$ {x:,.2f}")
            
            # Exibir tabela responsiva
            st.dataframe(df_exibir_display, use_container_width=True, hide_index=True)
            
            # Download CSV individual do mês
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
            
            # Apenas usuários com permissão de edição podem gerenciar lançamentos
            if user_can_edit():
                # Seção de Edição de Lançamentos
                st.subheader("✏️ Gerenciar Lançamentos")
                
                # Selecionar lançamento para editar
                if 'ID' in df_exibir.columns:
                    lancamentos_opcoes = []
                    for idx, row in df_exibir.iterrows():
                        valor = row['ENTRADA'] if row['ENTRADA'] > 0 else row['SAÍDA']
                        descricao = f"{row['DATA']} - {row['HISTÓRICO']} - R$ {valor:,.2f}"
                        lancamentos_opcoes.append((row['ID'], descricao))
                    
                    if lancamentos_opcoes:
                        lancamento_selecionado = st.selectbox(
                            "**Selecione o lançamento para editar/excluir:**",
                            options=lancamentos_opcoes,
                            format_func=lambda x: x[1]
                        )
                        
                        if lancamento_selecionado:
                            lancamento_id = lancamento_selecionado[0]
                            lancamento_data = df_exibir[df_exibir['ID'] == lancamento_id].iloc[0]
                            
                            col_edit, col_del = st.columns([3, 1])
                            
                            with col_edit:
                                # Formulário de edição
                                with st.form("form_editar_lancamento"):
                                    st.write("**Editar Lançamento:**")
                                    col6, col7, col8 = st.columns([2, 2, 1])
                                    
                                    with col6:
                                        data_editar = st.date_input("**Data**", 
                                                                  value=datetime.strptime(str(lancamento_data['DATA']), '%Y-%m-%d').date() 
                                                                  if isinstance(lancamento_data['DATA'], str) 
                                                                  else lancamento_data['DATA'].date())
                                        historico_editar = st.text_input("**Histórico**", value=lancamento_data['HISTÓRICO'])
                                    
                                    with col7:
                                        complemento_editar = st.text_input("**Complemento**", value=lancamento_data['COMPLEMENTO'] 
                                                                          if pd.notna(lancamento_data['COMPLEMENTO']) else "")
                                        
                                        # Determinar tipo de movimento baseado nos valores
                                        if lancamento_data['ENTRADA'] > 0:
                                            tipo_movimento_editar = "Entrada"
                                            entrada_editar = st.number_input("**Valor Entrada (R$)**", 
                                                                            value=float(lancamento_data['ENTRADA']), 
                                                                            min_value=0.0, step=0.01, format="%.2f")
                                            saida_editar = 0.0
                                        else:
                                            tipo_movimento_editar = "Saída"
                                            saida_editar = st.number_input("**Valor Saída (R$)**", 
                                                                          value=float(lancamento_data['SAÍDA']), 
                                                                          min_value=0.0, step=0.01, format="%.2f")
                                            entrada_editar = 0.0
                                    
                                    with col8:
                                        st.write("")  # Espaçamento
                                        st.write("")  # Espaçamento
                                        submitted_editar = st.form_submit_button("💾 Atualizar", use_container_width=True)
                                    
                                    if submitted_editar and historico_editar:
                                        # Atualizar lançamento no banco
                                        if atualizar_lancamento(lancamento_id, mes_selecionado, data_editar, historico_editar, 
                                                              complemento_editar, entrada_editar, saida_editar):
                                            st.success("✅ Lançamento atualizado com sucesso!")
                                            st.rerun()
                            
                            with col_del:
                                st.write("**Excluir:**")
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
    
    # Botão para limpar lançamentos do mês (apenas editores)
    if user_can_edit():
        if st.button(f"🗑️ Limpar TODOS os Lançamentos de {mes_selecionado}", use_container_width=True, type="secondary"):
            if st.checkbox("✅ Confirmar exclusão de TODOS os lançamentos"):
                limpar_lancamentos_mes(mes_selecionado)
                st.rerun()

# =============================================================================
# PÁGINA: CALENDÁRIO
# =============================================================================

elif pagina == "📅 Calendário":
    st.title("📅 Calendário Programável")
    
    # Configurações iniciais
    hoje = date.today()
    
    if 'calendario_ano' not in st.session_state:
        st.session_state.calendario_ano = hoje.year
    if 'calendario_mes' not in st.session_state:
        st.session_state.calendario_mes = hoje.month
    
    # Controles de navegação
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
    
    # Buscar eventos do mês
    eventos_mes = get_eventos_mes(st.session_state.calendario_ano, st.session_state.calendario_mes)
    
    # Gerar calendário
    calendario = gerar_calendario(st.session_state.calendario_ano, st.session_state.calendario_mes)
    
    # Exibir calendário
    st.markdown("---")
    
    # Cabeçalho dos dias da semana
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    cols = st.columns(7)
    for i, dia in enumerate(dias_semana):
        with cols[i]:
            st.markdown(f'<div style="text-align: center; font-weight: bold; padding: 10px; background-color: #f0f2f6; border-radius: 5px;">{dia}</div>', unsafe_allow_html=True)
    
    # Dias do calendário
    for semana in calendario:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            with cols[i]:
                if dia:
                    # Verificar se há eventos neste dia
                    eventos_dia = eventos_mes[eventos_mes['data_evento'] == dia.strftime('%Y-%m-%d')]
                    tem_eventos = len(eventos_dia) > 0
                    
                    # Destacar o dia atual
                    estilo_dia = "background-color: #e6f3ff; border: 2px solid #1f77b4;" if dia == hoje else "border: 1px solid #ddd;"
                    
                    # Exibir o dia
                    st.markdown(
                        f'<div style="{estilo_dia} padding: 10px; margin: 2px; border-radius: 5px; text-align: center; min-height: 80px;">'
                        f'<strong>{dia.day}</strong>'
                        f'{"<br><span style=\"color: red; font-size: 12px;\">●</span>" if tem_eventos else ""}'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    
                    # Adicionar interação para clicar no dia
                    if st.button(f"Selecionar", key=f"dia_{dia}", use_container_width=True):
                        st.session_state.dia_selecionado = dia
                else:
                    st.markdown('<div style="padding: 10px; margin: 2px; border-radius: 5px; min-height: 80px;"></div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Seção para adicionar/visualizar eventos
    col_esq, col_dir = st.columns([1, 1])
    
    with col_esq:
        st.subheader("➕ Adicionar Evento")
        
        # PERMISSÃO MODIFICADA: Todos os usuários logados podem adicionar eventos
        with st.form("form_evento", clear_on_submit=True):
            titulo = st.text_input("**Título do Evento**", placeholder="Reunião, Pagamento, Compromisso...")
            descricao = st.text_area("**Descrição**", placeholder="Detalhes do evento...")
            
            col_data, col_hora = st.columns(2)
            with col_data:
                data_evento = st.date_input("**Data do Evento**", value=st.session_state.get('dia_selecionado', hoje))
            with col_hora:
                hora_evento = st.time_input("**Hora do Evento**", value=datetime.now().time())
            
            tipo_evento = st.selectbox("**Tipo de Evento**", 
                                     options=["Reunião", "Pagamento", "Compromisso", "Lembrete", "Outro"])
            
            cor_evento = st.color_picker("**Cor do Evento**", value="#1f77b4")
            
            submitted = st.form_submit_button("💾 Salvar Evento", use_container_width=True)
            
            if submitted and titulo:
                if salvar_evento(titulo, descricao, data_evento, hora_evento, tipo_evento, cor_evento):
                    st.rerun()
            elif submitted and not titulo:
                st.warning("⚠️ Por favor, insira um título para o evento.")
    
    with col_dir:
        st.subheader("📋 Eventos do Mês")
        
        if not eventos_mes.empty:
            for _, evento in eventos_mes.iterrows():
                # Formatar a hora para exibição
                hora_exibicao = ""
                if evento['hora_evento']:
                    try:
                        # Se for string, converter para objeto time e formatar
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
                    
                    # PERMISSÃO MODIFICADA: Apenas o usuário que criou o evento ou admin pode editá-lo/excluí-lo
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
                        st.info("ℹ️ Apenas o criador do evento ou administrador pode editá-lo.")
        else:
            st.info("📭 Nenhum evento agendado para este mês.")
    
    # Edição de evento
    if 'editando_evento' in st.session_state:
        st.markdown("---")
        st.subheader("✏️ Editar Evento")
        
        # Buscar dados do evento
        evento_id = st.session_state.editando_evento
        evento_data = eventos_mes[eventos_mes['id'] == evento_id].iloc[0]
        
        # Verificar permissão para editar
        pode_editar = (user_is_admin() or evento_data['created_by'] == st.session_state.username)
        
        if pode_editar:
            # Converter a hora do evento para o formato correto
            hora_evento_existente = evento_data['hora_evento']
            if isinstance(hora_evento_existente, str):
                try:
                    hora_evento_existente = datetime.strptime(hora_evento_existente, '%H:%M:%S').time()
                except:
                    # Se não conseguir converter, usar hora padrão
                    hora_evento_existente = datetime.now().time()
            
            with st.form("form_editar_evento"):
                titulo_edit = st.text_input("**Título do Evento**", value=evento_data['titulo'])
                descricao_edit = st.text_area("**Descrição**", value=evento_data['descricao'])
                
                col_data_edit, col_hora_edit = st.columns(2)
                with col_data_edit:
                    data_evento_edit = st.date_input("**Data do Evento**", 
                                                   value=datetime.strptime(evento_data['data_evento'], '%Y-%m-%d').date())
                with col_hora_edit:
                    hora_evento_edit = st.time_input("**Hora do Evento**", 
                                                   value=hora_evento_existente)
                
                tipo_evento_edit = st.selectbox("**Tipo de Evento**", 
                                              options=["Reunião", "Pagamento", "Compromisso", "Lembrete", "Outro"],
                                              index=["Reunião", "Pagamento", "Compromisso", "Lembrete", "Outro"].index(evento_data['tipo_evento']))
                
                cor_evento_edit = st.color_picker("**Cor do Evento**", value=evento_data['cor_evento'])
                
                col_salvar, col_cancelar = st.columns(2)
                with col_salvar:
                    submitted_edit = st.form_submit_button("💾 Atualizar Evento", use_container_width=True)
                with col_cancelar:
                    if st.form_submit_button("❌ Cancelar", use_container_width=True):
                        del st.session_state.editando_evento
                        st.rerun()
                
                if submitted_edit and titulo_edit:
                    if atualizar_evento(evento_id, titulo_edit, descricao_edit, data_evento_edit, 
                                      hora_evento_edit, tipo_evento_edit, cor_evento_edit):
                        del st.session_state.editando_evento
                        st.rerun()
                elif submitted_edit and not titulo_edit:
                    st.warning("⚠️ Por favor, insira um título para o evento.")
        else:
            st.error("❌ Você não tem permissão para editar este evento.")
            if st.button("⬅️ Voltar", use_container_width=True):
                del st.session_state.editando_evento
                st.rerun()

# =============================================================================
# PÁGINA: BALANÇO FINANCEIRO
# =============================================================================

elif pagina == "📈 Balanço Financeiro":
    st.title("📈 Balanço Financeiro")
    
    # Calcular totais anuais
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
    
    # Layout responsivo
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📥 Débitos")
        st.metric("**Total de Entradas Anual**", f"R$ {total_entradas_anual:,.2f}")
        
        st.subheader("📅 Resumo por Mês")
        for dados in dados_mensais:
            with st.expander(f"📁 {dados['Mês']}"):
                st.write(f"**Entradas:** R$ {dados['Entradas']:,.2f}")
                st.write(f"**Saídas:** R$ {dados['Saídas']:,.2f}")
                st.write(f"**Saldo:** R$ {dados['Saldo']:,.2f}")
    
    with col2:
        st.subheader("📤 Créditos")
        st.metric("**Total de Saídas Anual**", f"R$ {total_saidas_anual:,.2f}")
        st.metric("**Saldo Final Anual**", f"R$ {saldo_final_anual:,.2f}", 
                 delta=f"R$ {saldo_final_anual:,.2f}")
        
        # Gráfico simples de barras
        if dados_mensais:
            st.subheader("📊 Resumo Visual")
            df_grafico = pd.DataFrame(dados_mensais)
            st.bar_chart(df_grafico.set_index('Mês')[['Entradas', 'Saídas']], use_container_width=True)

# =============================================================================
# PÁGINA: EXPORTAR DADOS
# =============================================================================

elif pagina == "💾 Exportar Dados":
    st.title("💾 Exportar Dados")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📤 Exportar Dados")
        
        st.info("💡 Os arquivos CSV podem ser abertos diretamente no Excel")
        
        # Download de CSV individual por mês
        st.subheader("📥 Download por Mês")
        meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        
        mes_download = st.selectbox("**Selecione o mês para download:**", meses)
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
        
        # Exportação completa
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
        
        # Estatísticas do banco
        conn = get_db_connection()
        
        try:
            if conn:
                total_lancamentos = pd.read_sql("SELECT COUNT(*) as total FROM lancamentos", conn).iloc[0]['total']
                total_contas = pd.read_sql("SELECT COUNT(*) as total FROM contas", conn).iloc[0]['total']
                meses_com_dados = pd.read_sql("SELECT COUNT(DISTINCT mes) as total FROM lancamentos", conn).iloc[0]['total']
                total_eventos = pd.read_sql("SELECT COUNT(*) as total FROM eventos_calendario", conn).iloc[0]['total']
            else:
                total_lancamentos = 0
                total_contas = 0
                meses_com_dados = 0
                total_eventos = 0
        except:
            total_lancamentos = 0
            total_contas = 0
            meses_com_dados = 0
            total_eventos = 0
        finally:
            if conn:
                conn.close()
        
        st.metric("📝 Total de Lançamentos", total_lancamentos)
        st.metric("📋 Total de Contas", total_contas)
        st.metric("📅 Meses com Dados", meses_com_dados)
        st.metric("📅 Total de Eventos", total_eventos)
        
        st.info("""
        **ℹ️ Informações do Sistema:**
        - **Banco de Dados:** PlanetScale (MySQL)
        - **Host:** aws.connect.psdb.cloud
        - **Dados:** Persistidos na nuvem
        - **Exportação:** CSV compatível com Excel
        - **Segurança:** Acesso por login
        - **Usuários:** Múltiplos usuários suportados
        - **Calendário:** Eventos programáveis
        """)

# =============================================================================
# RODAPÉ
# =============================================================================

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; font-size: 0.9rem;'>
        <strong>CONSTITUCIONALISTAS-929</strong> - Livro Caixa | 
        Desenvolvido por Silmar Tolotto | 
        Usuário: {username} | 
        {date}
    </div>
    """.format(username=st.session_state.username, date=datetime.now().strftime('%d/%m/%Y %H:%M')),
    unsafe_allow_html=True
)
# CORREÇÃO TEMPORÁRIA - Adicione antes do sistema de login
def corrigir_tabela_usuarios():
    """Corrige a tabela de usuários se necessário"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Verificar se a tabela existe e tem problemas
        cursor.execute('''
            SELECT COLUMN_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'usuarios' AND COLUMN_NAME = 'permissao'
        ''')
        result = cursor.fetchone()
        
        if result and 'enum' in result[0].lower():
            st.info("✅ Tabela de usuários parece estar correta")
        else:
            st.warning("🔄 Corrigindo tabela de usuários...")
            # Recriar tabela se necessário
            cursor.execute('DROP TABLE IF EXISTS usuarios')
            cursor.execute('''
                CREATE TABLE usuarios (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    permissao ENUM('admin', 'editor', 'visualizador') NOT NULL DEFAULT 'visualizador',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            st.success("✅ Tabela corrigida!")
            
    except Exception as e:
        st.error(f"Erro ao verificar tabela: {e}")
    finally:
        if conn:
            conn.close()

# Chamar a correção temporária
if st.session_state.get('logged_in') is None:
    corrigir_tabela_usuarios()
