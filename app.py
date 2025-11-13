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
from PIL import Image
import requests
from io import BytesIO

# Tentar importar pymysql, mas lidar com a ausência graciosamente
try:
    import pymysql
    from pymysql import Error
    PYMySQL_AVAILABLE = True
except ImportError:
    PYMySQL_AVAILABLE = False
    st.warning("⚠️ A biblioteca PyMySQL não está instalada. O sistema funcionará em modo de demonstração.")

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
# FUNÇÃO PARA CARREGAR E EXIBIR LOGO
# =============================================================================
def exibir_logo():
    """Exibe o logo da loja no sidebar ou header"""
    caminho_logo = carregar_imagem_logo("Logo_Loja.png")  # Tenta carregar logo.png primeiro
    
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
# CONEXÃO COM PLANETSCALE (OU MODO DEMONSTRAÇÃO)
# =============================================================================
def get_db_connection():
    """Cria conexão com o PlanetScale usando PyMySQL ou retorna None se não disponível"""
    if not PYMySQL_AVAILABLE:
        return None

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
    if not PYMySQL_AVAILABLE:
        st.warning("⚠️ PyMySQL não disponível - modo demonstração ativo")
        return

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
    if not PYMySQL_AVAILABLE:
        # Modo demonstração - usuários fixos
        usuarios_demo = {
            'admin': ('admin', 'admin'),
            'visual': ('visual', 'visualizador')
        }
        
        if username in usuarios_demo and password == 'demo123':
            return True, usuarios_demo[username]
        return False, "Usuário ou senha incorretos (modo demonstração: senha='demo123')"

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

    if not PYMySQL_AVAILABLE:
        return False, "Modo demonstração - não é possível criar usuários"

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

    if not PYMySQL_AVAILABLE:
        # Dados de demonstração
        return [
            ('admin', 'admin@loja.com', 'admin', datetime.now(), 'Administrador Principal', '(11) 99999-9999', 'Endereço principal', None, None, None, None, None, 'Usuário administrador', '@admin'),
            ('visual', 'visual@loja.com', 'visualizador', datetime.now(), 'Usuário Visualizador', '(11) 88888-8888', 'Endereço secundário', None, None, None, None, None, 'Usuário visualizador', '@visual')
        ]

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
    if not PYMySQL_AVAILABLE:
        # Dados de demonstração para agenda
        return [
            ('admin', 'admin@loja.com', 'admin', datetime.now(), 'João Silva', '(11) 99999-9999', 'Rua Principal, 123 - São Paulo', 
             date(1980, 5, 15), date(2010, 3, 20), date(2011, 6, 15), date(2012, 9, 10), date(2020, 1, 15), 
             'Membro fundador da loja', '@joaosilva'),
            ('visual', 'visual@loja.com', 'visualizador', datetime.now(), 'Maria Santos', '(11) 88888-8888', 'Av. Secundária, 456 - São Paulo',
             date(1985, 8, 25), date(2015, 4, 10), date(2016, 7, 20), date(2017, 10, 5), date(2021, 3, 20),
             'Membro ativo da comunidade', '@mariasantos')
        ]

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

# ... (continuam as outras funções do CRUD de usuários com verificações similares)

def get_contas():
    if not PYMySQL_AVAILABLE:
        return ["Caixa Principal", "Banco", "Investimentos", "Despesas Operacionais"]
    
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
    if not PYMySQL_AVAILABLE:
        return False, "Modo demonstração - não é possível adicionar contas"
    
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
    if not PYMySQL_AVAILABLE:
        # Dados de demonstração
        dados_demo = {
            'data': [date(2024, 1, 5), date(2024, 1, 10), date(2024, 1, 15)],
            'historico': ['Venda Loja', 'Compra Materiais', 'Serviços Prestados'],
            'complemento': ['Venda no balcão', 'Material de escritório', 'Serviço de consultoria'],
            'entrada': [1500.00, 0, 800.00],
            'saida': [0, 350.00, 0],
            'saldo': [1500.00, 1150.00, 1950.00]
        }
        return pd.DataFrame(dados_demo)
    
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
    if not PYMySQL_AVAILABLE:
        st.success("✅ Lançamento salvo com sucesso! (modo demonstração)")
        return True
    
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

# ... (as demais funções de banco de dados seguem o mesmo padrão de verificação)

def init_db():
    """Inicializa as demais tabelas do sistema"""
    if not PYMySQL_AVAILABLE:
        return

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

# =============================================================================
# FUNÇÃO PARA O GERADOR DE CONVITES EXTERNO
# =============================================================================

def show_gerador_convites_externo():
    """Redireciona para o aplicativo de convites externo"""
    st.header("🎉 Gerador de Convites")
    
    # Verificação de permissão
    if not user_can_edit():
        st.warning("⚠️ Você precisa de permissão de edição para acessar o gerador de convites")
        return
    
    st.info("""
    **📋 Sobre o Gerador de Convites:**
    - Gere convites personalizados para eventos da loja
    - Use modelos pré-definidos ou faça upload do seu próprio
    - Customize textos, fontes e cores
    - Exporte em formato PDF para impressão
    """)
    
    # Opções para abrir o gerador de convites
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🛠️ Acessar Gerador de Convites")
        st.markdown("""
        Clique no botão abaixo para abrir o Gerador de Convites em uma nova aba/página.
        
        **Funcionalidades disponíveis:**
        - Upload de modelos de convite
        - Personalização de textos
        - Configuração de fontes e cores
        - Geração de PDF
        """)
        
        # Botão para abrir o app_convites.py
        if st.button("🚀 Abrir Gerador de Convites", use_container_width=True):
            st.success("✅ Redirecionando para o Gerador de Convites...")
            st.info("🔗 Se o redirecionamento automático não funcionar, use o link abaixo:")
            st.markdown('[📎 Acessar Gerador de Convites](./app_convites)', unsafe_allow_html=True)
    
    with col2:
        st.subheader("📘 Instruções Rápidas")
        st.markdown("""
        **Como usar:**
        1. Faça upload do modelo do convite (JPG/PNG)
        2. Configure os textos nas posições indicadas
        3. Ajuste tamanhos e cores das fontes
        4. Visualize a prévia
        5. Gere e baixe o PDF
        
        **Posições dos textos:**
        - Texto 1: Nome do Venerável Mestre
        - Texto 2: Descrição da sessão
        - Texto 3: Nome do candidato 1
        - Texto 4: Nome do candidato 2
        - Texto 5: Data e hora do evento
        """)
    
    st.markdown("---")
    
    # Informações adicionais
    st.subheader("ℹ️ Informações Importantes")
    
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.markdown("""
        **📝 Requisitos do Modelo:**
        - Formato: JPG ou PNG
        - Proporção recomendada: A4 paisagem
        - Resolução: Mínimo 842x595 pixels
        - Deixe áreas em branco para os textos
        """)
    
    with col_info2:
        st.markdown("""
        **💡 Dicas:**
        - Use modelos com boa resolução
        - Teste diferentes tamanhos de fonte
        - Verifique sempre a pré-visualização
        - Para impressão, use papel de qualidade
        """)

# =============================================================================
# INTERFACE PRINCIPAL
# =============================================================================

def main():
    """Função principal da aplicação"""
    
    # Inicializar session state
    init_session_state()
    
    # Mostrar aviso se PyMySQL não estiver disponível
    if not PYMySQL_AVAILABLE:
        st.warning("""
        ⚠️ **Modo Demonstração Ativo**
        
        O PyMySQL não está instalado. O sistema funcionará com dados de demonstração.
        
        Para usar o sistema completo com banco de dados real, instale:
        ```bash
        pip install pymysql
        ```
        
        E configure os secrets do PlanetScale no Streamlit Cloud.
        """)
    
    # Inicializar banco de dados (se disponível)
    if PYMySQL_AVAILABLE:
        init_auth_db()
        init_db()
    
    # Logo e cabeçalho
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Tenta carregar e exibir um logo pequeno no header também
        caminho_logo_header = carregar_imagem_logo("logo.png")
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
                st.title("📒 Administração de Loja")
        else:
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
    
    if not PYMySQL_AVAILABLE:
        st.info("""
        **Modo Demonstração - Credenciais:**
        - **Usuário:** `admin` ou `visual`
        - **Senha:** `demo123`
        """)
    
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
    
    # Sidebar com navegação E LOGO
    with st.sidebar:
        # EXIBIR LOGO NO TOPO
        exibir_logo()
        
        st.header(f"👋 Olá, {st.session_state.username}!")
        st.write(f"**Permissão:** {PERMISSOES.get(st.session_state.permissao, st.session_state.permissao)}")
        
        if not PYMySQL_AVAILABLE:
            st.warning("🔶 Modo Demonstração")
        
        st.markdown("---")
        
        # MENU DE NAVEGAÇÃO ATUALIZADO - ADICIONANDO GERADOR DE CONVITES
        menu_options = ["📊 Livro Caixa", "📅 Calendário"]
        
        if user_can_edit():
            menu_options.append("⚙️ Configurações")
        
        menu_options.append("📒 Agenda de Contatos")
        
        # ADIÇÃO DO GERADOR DE CONVITES - disponível para quem pode editar
        if user_can_edit():
            menu_options.append("🎉 Gerador de Convites")
        
        if user_is_admin():
            menu_options.append("👥 Gerenciar Usuários")
        
        selected_menu = st.radio("Navegação", menu_options, key="nav_menu")
        
        st.markdown("---")
        
        # Informações do sistema ATUALIZADAS
        st.write("**💡 Dicas:**")
        st.write("- Use o Livro Caixa para registrar entradas e saídas")
        st.write("- O calendário ajuda no planejamento de eventos")
        st.write("- A agenda de contatos mostra informações dos membros")
        if user_can_edit():
            st.write("- Use o Gerador de Convites para criar convites personalizados")
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
    
    # NAVEGAÇÃO PRINCIPAL ATUALIZADA
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
    elif selected_menu == "🎉 Gerador de Convites" and user_can_edit():
        show_gerador_convites_externo()

# ... (as demais funções de interface permanecem iguais)

def show_livro_caixa():
    """Interface do Livro Caixa"""
    st.header("📊 Livro Caixa")
    
    if not PYMySQL_AVAILABLE:
        st.info("📊 **Modo Demonstração** - Dados fictícios para teste")
    
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

# ... (continuam as outras funções de interface)

# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    main()
