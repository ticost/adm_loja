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
# FUNÇÕES DE AUTENTICAÇÃO
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
# FUNÇÕES DE BANCO DE DADOS BÁSICAS
# =============================================================================

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
# FUNÇÕES DE INTERFACE DO LIVRO CAIXA
# =============================================================================

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
        
        # Exibir tabela simplificada
        for _, row in df_display.iterrows():
            col1, col2, col3, col4, col5 = st.columns([2, 3, 2, 2, 2])
            
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
            
            st.markdown("---")
    else:
        # Visualização em cards
        for _, lancamento in df_lancamentos.iterrows():
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                
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
                
                st.markdown("---")

def show_relatorios(mes, df_lancamentos):
    """Exibe relatórios e gráficos"""
    if df_lancamentos.empty:
        st.info("📭 Nenhum dado para exibir relatórios")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Resumo Financeiro")
        
        total_entrada = df_lancamentos['entrada'].sum()
        total_saida = df_lancamentos['saida'].sum()
        saldo_final = df_lancamentos['saldo'].iloc[-1] if len(df_lancamentos) > 0 else 0
        
        st.metric("Total Entradas", f"R$ {total_entrada:,.2f}")
        st.metric("Total Saídas", f"R$ {total_saida:,.2f}")
        st.metric("Saldo Final", f"R$ {saldo_final:,.2f}")
        st.metric("Número de Lançamentos", len(df_lancamentos))
    
    with col2:
        st.subheader("📊 Distribuição")
        
        # Gráfico simples de pizza
        if total_entrada + total_saida > 0:
            chart_data = pd.DataFrame({
                'Categoria': ['Entradas', 'Saídas'],
                'Valor': [total_entrada, total_saida]
            })
            st.bar_chart(chart_data.set_index('Categoria'))

def show_configuracoes_mes(mes):
    """Configurações administrativas do mês"""
    st.subheader("⚙️ Configurações do Mês")
    
    if not PYMySQL_AVAILABLE:
        st.info("🔶 Modo demonstração - configurações limitadas")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Exportar Dados do Mês", use_container_width=True):
            df_lancamentos = get_lancamentos_mes(mes)
            if not df_lancamentos.empty:
                csv_data = df_lancamentos.to_csv(index=False, encoding='utf-8')
                st.download_button(
                    label="💾 Download CSV",
                    data=csv_data,
                    file_name=f"lancamentos_{mes}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    with col2:
        if st.button("🔄 Limpar Dados", use_container_width=True):
            st.warning("⚠️ Funcionalidade não disponível em modo demonstração")

# =============================================================================
# FUNÇÕES DE CALENDÁRIO
# =============================================================================

def show_calendario():
    """Interface do Calendário"""
    st.header("📅 Calendário de Eventos")
    
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
    
    # Abas do calendário
    tab1, tab2 = st.tabs(["📅 Visualização Mensal", "➕ Novo Evento"])
    
    with tab1:
        show_calendario_mensal(ano, mes)
    
    with tab2:
        if user_can_edit():
            show_novo_evento()
        else:
            st.warning("⚠️ Você possui permissão apenas para visualização")

def show_calendario_mensal(ano, mes):
    """Exibe calendário mensal"""
    calendario = calendar.Calendar(firstweekday=6)  # Domingo como primeiro dia
    mes_calendario = calendario.monthdatescalendar(ano, mes)
    nomes_dias = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    
    # Cabeçalho dos dias
    cols = st.columns(7)
    for i, col in enumerate(cols):
        col.write(f"**{nomes_dias[i]}**")
    
    # Dias do mês
    for semana in mes_calendario:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            with cols[i]:
                # Verificar se o dia é do mês atual
                if dia.month == mes:
                    st.write(f"**{dia.day}**")
                else:
                    st.write(f"<span style='color: lightgray'>{dia.day}</span>", unsafe_allow_html=True)

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
                "", "Reunião", "Evento Social", "Feriado", "Compromisso", "Outro"
            ])
        
        submitted = st.form_submit_button("💾 Salvar Evento")
        
        if submitted:
            if not titulo:
                st.error("❌ O campo Título é obrigatório")
                return
            
            st.success("✅ Evento salvo com sucesso! (modo demonstração)")

# =============================================================================
# FUNÇÕES DE AGENDA DE CONTATOS
# =============================================================================

def visualizar_agenda_contatos():
    """Interface para visualização da agenda de contatos"""
    st.header("📒 Agenda de Contatos")
    
    users = get_all_users_for_agenda()
    
    if not users:
        st.info("📭 Nenhum usuário cadastrado no sistema")
        return
    
    st.success(f"📊 Total de contatos: {len(users)}")
    
    # Filtro de busca
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
    
    # Exibir contatos
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
            
            # INFORMAÇÕES DE CONTATO
            if email or telefone:
                st.write("**📞 Contato:**")
                if email:
                    st.write(f"📧 **E-mail:** {email}")
                if telefone:
                    st.write(f"📱 **Telefone:** {telefone}")
            
            # ENDEREÇO
            if endereco:
                st.write("**📍 Endereço:**")
                st.write(f"🏠 {endereco}")
            
            # DATAS IMPORTANTES
            st.write("**📅 Datas Importantes:**")
            col1, col2 = st.columns(2)
            
            with col1:
                if data_aniversario:
                    st.write(f"• 🎂 **Aniversário:** {data_aniversario.strftime('%d/%m/%Y')}")
                if data_iniciacao:
                    st.write(f"• 🕊️ **Iniciação:** {data_iniciacao.strftime('%d/%m/%Y')}")
            
            with col2:
                if data_exaltacao:
                    st.write(f"• ⭐ **Exaltação:** {data_exaltacao.strftime('%d/%m/%Y')}")
                if data_instalacao_posse:
                    st.write(f"• 👑 **Posse:** {data_instalacao_posse.strftime('%d/%m/%Y')}")
            
            # OBSERVAÇÕES
            if observacoes:
                st.write("**📝 Observações:**")
                st.write(observacoes)
            
            st.markdown("---")

# =============================================================================
# FUNÇÕES DE CONFIGURAÇÕES
# =============================================================================

def show_configuracoes():
    """Configurações do sistema"""
    st.header("⚙️ Configurações do Sistema")
    
    if not user_is_admin():
        st.warning("⚠️ Apenas administradores podem acessar as configurações do sistema")
        return
    
    tab1, tab2 = st.tabs(["💾 Backup", "🔧 Sistema"])
    
    with tab1:
        show_backup_section()
    
    with tab2:
        show_system_info()

def show_backup_section():
    """Seção de backup"""
    st.subheader("💾 Backup do Sistema")
    
    if not PYMySQL_AVAILABLE:
        st.info("🔶 Modo demonstração - backup não disponível")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Criar Backup", use_container_width=True):
            st.info("📦 Funcionalidade de backup em desenvolvimento")

def show_system_info():
    """Informações do sistema"""
    st.subheader("🔧 Informações do Sistema")
    
    st.write("**📊 Estatísticas:**")
    col1,
