# app_convites.py - SISTEMA DE CONVITES
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import io
import os
import pymysql
from pymysql import Error
import hashlib

# Configuração da página para convites
st.set_page_config(
    page_title="Sistema de Convites",
    page_icon="🎫",
    layout="wide"
)

# =============================================================================
# CONEXÃO COM BANCO DE DADOS
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
        st.error(f"❌ Erro MySQL: {e}")
        return None
    except Exception as e:
        st.error(f"❌ Erro de conexão: {e}")
        return None

# =============================================================================
# INICIALIZAÇÃO DO BANCO DE DADOS PARA CONVITES
# =============================================================================

def init_convites_db():
    """Inicializa as tabelas para o sistema de convites"""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()

        # Tabela de eventos para convites
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS eventos_convites (
                id INT AUTO_INCREMENT PRIMARY KEY,
                titulo VARCHAR(200) NOT NULL,
                descricao TEXT,
                data_evento DATE NOT NULL,
                hora_evento TIME,
                local_evento VARCHAR(300),
                tipo_evento VARCHAR(100),
                data_limite_confirmacao DATE,
                created_by VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de convidados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS convidados (
                id INT AUTO_INCREMENT PRIMARY KEY,
                evento_id INT,
                nome_convidado VARCHAR(200) NOT NULL,
                email VARCHAR(200),
                telefone VARCHAR(50),
                instituicao VARCHAR(200),
                cargo VARCHAR(100),
                quantidade_acompanhantes INT DEFAULT 0,
                status_confirmacao ENUM('Pendente', 'Confirmado', 'Cancelado') DEFAULT 'Pendente',
                data_confirmacao TIMESTAMP NULL,
                observacoes TEXT,
                codigo_confirmacao VARCHAR(50) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evento_id) REFERENCES eventos_convites(id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        return True

    except Error as e:
        st.error(f"❌ Erro ao criar tabelas de convites: {e}")
        return False
    finally:
        if conn:
            conn.close()

# =============================================================================
# FUNÇÕES CRUD PARA EVENTOS
# =============================================================================

def criar_evento(titulo, descricao, data_evento, hora_evento, local_evento, tipo_evento, data_limite_confirmacao):
    """Cria um novo evento para convites"""
    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO eventos_convites 
            (titulo, descricao, data_evento, hora_evento, local_evento, tipo_evento, data_limite_confirmacao, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (titulo, descricao, data_evento, hora_evento, local_evento, tipo_evento, data_limite_confirmacao, st.session_state.username))

        evento_id = cursor.lastrowid
        conn.commit()
        return True, f"Evento '{titulo}' criado com sucesso! ID: {evento_id}"

    except Error as e:
        return False, f"Erro ao criar evento: {e}"
    finally:
        if conn:
            conn.close()

def get_eventos_convites():
    """Busca todos os eventos de convites"""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM eventos_convites 
            ORDER BY data_evento DESC
        ''')
        return cursor.fetchall()
    except Error:
        return []
    finally:
        if conn:
            conn.close()

def get_evento_por_id(evento_id):
    """Busca um evento específico pelo ID"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM eventos_convites WHERE id = %s', (evento_id,))
        return cursor.fetchone()
    except Error:
        return None
    finally:
        if conn:
            conn.close()

# =============================================================================
# FUNÇÕES CRUD PARA CONVIDADOS
# =============================================================================

def adicionar_convidado(evento_id, nome_convidado, email, telefone, instituicao, cargo, quantidade_acompanhantes, observacoes):
    """Adiciona um convidado a um evento"""
    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        # Gerar código de confirmação único
        codigo_confirmacao = hashlib.md5(f"{evento_id}{nome_convidado}{datetime.now()}".encode()).hexdigest()[:10]

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO convidados 
            (evento_id, nome_convidado, email, telefone, instituicao, cargo, quantidade_acompanhantes, observacoes, codigo_confirmacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (evento_id, nome_convidado, email, telefone, instituicao, cargo, quantidade_acompanhantes, observacoes, codigo_confirmacao))

        conn.commit()
        return True, f"Convidado '{nome_convidado}' adicionado com sucesso!"

    except Error as e:
        return False, f"Erro ao adicionar convidado: {e}"
    finally:
        if conn:
            conn.close()

def get_convidados_por_evento(evento_id):
    """Busca todos os convidados de um evento"""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM convidados 
            WHERE evento_id = %s 
            ORDER BY nome_convidado
        ''', (evento_id,))
        return cursor.fetchall()
    except Error:
        return []
    finally:
        if conn:
            conn.close()

def atualizar_status_convidado(convidado_id, novo_status):
    """Atualiza o status de confirmação de um convidado"""
    conn = get_db_connection()
    if not conn:
        return False, "Erro de conexão"

    try:
        cursor = conn.cursor()
        data_confirmacao = datetime.now() if novo_status == 'Confirmado' else None
        
        cursor.execute('''
            UPDATE convidados 
            SET status_confirmacao = %s, data_confirmacao = %s 
            WHERE id = %s
        ''', (novo_status, data_confirmacao, convidado_id))

        conn.commit()
        return True, "Status atualizado com sucesso!"

    except Error as e:
        return False, f"Erro ao atualizar status: {e}"
    finally:
        if conn:
            conn.close()

# =============================================================================
# FUNÇÕES PARA RELATÓRIOS E ESTATÍSTICAS
# =============================================================================

def get_estatisticas_evento(evento_id):
    """Obtém estatísticas de um evento"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        
        # Total de convidados
        cursor.execute('SELECT COUNT(*) FROM convidados WHERE evento_id = %s', (evento_id,))
        total_convidados = cursor.fetchone()[0]
        
        # Por status
        cursor.execute('SELECT status_confirmacao, COUNT(*) FROM convidados WHERE evento_id = %s GROUP BY status_confirmacao', (evento_id,))
        status_counts = cursor.fetchall()
        
        # Total de acompanhantes
        cursor.execute('SELECT SUM(quantidade_acompanhantes) FROM convidados WHERE evento_id = %s AND status_confirmacao = "Confirmado"', (evento_id,))
        total_acompanhantes = cursor.fetchone()[0] or 0
        
        estatisticas = {
            'total_convidados': total_convidados,
            'status': dict(status_counts),
            'total_acompanhantes': total_acompanhantes,
            'total_confirmados': total_acompanhantes + dict(status_counts).get('Confirmado', 0)
        }
        
        return estatisticas

    except Error:
        return None
    finally:
        if conn:
            conn.close()

# =============================================================================
# FUNÇÕES PARA GERAR CONVITES (HTML/CSV)
# =============================================================================

def gerar_convite_html(evento, convidado):
    """Gera um convite em HTML"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Convite - {evento[1]}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                background-color: #f5f5f5;
            }}
            .convite {{
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                max-width: 600px;
                margin: 0 auto;
                border: 2px solid #2c3e50;
            }}
            .header {{
                text-align: center;
                border-bottom: 2px solid #2c3e50;
                padding-bottom: 20px;
                margin-bottom: 30px;
            }}
            .detalhes-evento {{
                margin: 20px 0;
            }}
            .detalhes-evento div {{
                margin: 10px 0;
            }}
            .codigo-confirmacao {{
                background: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                text-align: center;
                margin: 20px 0;
                font-family: monospace;
                font-size: 16px;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                font-size: 12px;
                color: #7f8c8d;
            }}
        </style>
    </head>
    <body>
        <div class="convite">
            <div class="header">
                <h1>🎫 CONVITE OFICIAL</h1>
                <h2>{evento[1]}</h2>
            </div>
            
            <div style="text-align: center; margin: 20px 0;">
                <p>Prezado(a) <strong>{convidado[2]}</strong>,</p>
                <p>É com grande satisfação que convidamos Vossa Senhoria para nosso evento:</p>
            </div>
            
            <div class="detalhes-evento">
                <div><strong>📅 Data:</strong> {evento[3].strftime('%d/%m/%Y')}</div>
                <div><strong>⏰ Hora:</strong> {evento[4] if evento[4] else 'A definir'}</div>
                <div><strong>📍 Local:</strong> {evento[5] if evento[5] else 'A definir'}</div>
                <div><strong>🎯 Tipo:</strong> {evento[6] if evento[6] else 'Evento'}</div>
            </div>
            
            <div style="margin: 20px 0;">
                <p><strong>Descrição:</strong></p>
                <p>{evento[2] if evento[2] else 'Detalhes serão informados em breve.'}</p>
            </div>
            
            <div class="codigo-confirmacao">
                <strong>Código de Confirmação:</strong><br>
                {convidado[11]}
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <p><em>Por favor, confirme sua presença até {evento[7].strftime('%d/%m/%Y') if evento[7] else 'a data do evento'}</em></p>
            </div>
            
            <div class="footer">
                <p>Administração de Loja © {datetime.now().year}</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

def exportar_convidados_csv(evento_id):
    """Exporta lista de convidados para CSV"""
    convidados = get_convidados_por_evento(evento_id)
    evento = get_evento_por_id(evento_id)
    
    if not convidados:
        return None
    
    dados = []
    for convidado in convidados:
        dados.append({
            'Nome': convidado[2],
            'Email': convidado[3] or '',
            'Telefone': convidado[4] or '',
            'Instituição': convidado[5] or '',
            'Cargo': convidado[6] or '',
            'Acompanhantes': convidado[7],
            'Status': convidado[8],
            'Data Confirmação': convidado[9].strftime('%d/%m/%Y %H:%M') if convidado[9] else '',
            'Código': convidado[11] or ''
        })
    
    df = pd.DataFrame(dados)
    return df.to_csv(index=False, encoding='utf-8-sig')

# =============================================================================
# INTERFACE PRINCIPAL DO SISTEMA DE CONVITES
# =============================================================================

def main():
    """Função principal do sistema de convites"""
    
    # Inicializar banco de dados
    if not init_convites_db():
        st.error("❌ Erro ao inicializar banco de dados de convites")
        return
    
    st.title("🎫 Sistema de Gestão de Convites")
    
    # Abas principais
    tab1, tab2, tab3 = st.tabs(["📅 Eventos", "👥 Convidados", "📊 Relatórios"])
    
    with tab1:
        show_gestao_eventos()
    
    with tab2:
        show_gestao_convidados()
    
    with tab3:
        show_relatorios()

def show_gestao_eventos():
    """Interface para gestão de eventos"""
    st.header("📅 Gestão de Eventos")
    
    # Formulário para novo evento
    with st.expander("➕ Criar Novo Evento", expanded=True):
        with st.form("novo_evento"):
            col1, col2 = st.columns(2)
            
            with col1:
                titulo = st.text_input("Título do Evento:*", placeholder="Nome do evento")
                descricao = st.text_area("Descrição:", placeholder="Detalhes do evento")
                data_evento = st.date_input("Data do Evento:*", min_value=date.today())
                hora_evento = st.time_input("Hora do Evento:", value=None)
            
            with col2:
                local_evento = st.text_input("Local do Evento:", placeholder="Endereço ou local")
                tipo_evento = st.selectbox("Tipo de Evento:", [
                    "Iniciação", "Elevação", "Exaltação", "Sessão Econômica", 
                    "Jantar Ritualístico", "Reunião", "Festa", "Cerimônia", "Outro"
                ])
                data_limite = st.date_input("Data Limite para Confirmação:", min_value=date.today())
            
            submitted = st.form_submit_button("💾 Criar Evento")
            
            if submitted:
                if not titulo:
                    st.error("❌ O título do evento é obrigatório")
                else:
                    success, message = criar_evento(
                        titulo, descricao, data_evento, hora_evento, 
                        local_evento, tipo_evento, data_limite
                    )
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
    
    # Lista de eventos existentes
    st.subheader("📋 Eventos Cadastrados")
    eventos = get_eventos_convites()
    
    if not eventos:
        st.info("📭 Nenhum evento cadastrado")
        return
    
    for evento in eventos:
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"### {evento[1]}")
                st.write(f"**Data:** {evento[3].strftime('%d/%m/%Y')} | **Local:** {evento[5] or 'Não definido'}")
                st.write(f"**Tipo:** {evento[6]} | **Criado por:** {evento[8]}")
                if evento[2]:
                    st.write(f"**Descrição:** {evento[2]}")
            
            with col2:
                if st.button("👥 Gerenciar", key=f"ger_{evento[0]}"):
                    st.session_state.evento_selecionado = evento[0]
                    st.rerun()
            
            with col3:
                if st.button("📊 Estatísticas", key=f"est_{evento[0]}"):
                    st.session_state.evento_estatisticas = evento[0]
                    st.rerun()
            
            st.markdown("---")

def show_gestao_convidados():
    """Interface para gestão de convidados"""
    st.header("👥 Gestão de Convidados")
    
    # Selecionar evento
    eventos = get_eventos_convites()
    if not eventos:
        st.info("📭 Crie um evento primeiro para adicionar convidados")
        return
    
    evento_options = {f"{evento[1]} ({evento[3].strftime('%d/%m/%Y')})": evento[0] for evento in eventos}
    evento_selecionado_nome = st.selectbox("Selecione o Evento:", list(evento_options.keys()))
    evento_id = evento_options[evento_selecionado_nome]
    
    # Formulário para adicionar convidado
    with st.expander("➕ Adicionar Convidado", expanded=True):
        with st.form("novo_convidado"):
            col1, col2 = st.columns(2)
            
            with col1:
                nome_convidado = st.text_input("Nome Completo:*", placeholder="Nome do convidado")
                email = st.text_input("E-mail:", placeholder="email@exemplo.com")
                telefone = st.text_input("Telefone:", placeholder="(00) 00000-0000")
            
            with col2:
                instituicao = st.text_input("Instituição:", placeholder="Loja, empresa, etc.")
                cargo = st.text_input("Cargo/Função:", placeholder="Cargo ou grau")
                quantidade_acompanhantes = st.number_input("Acompanhantes:", min_value=0, value=0)
            
            observacoes = st.text_area("Observações:", placeholder="Informações adicionais")
            
            submitted = st.form_submit_button("💾 Adicionar Convidado")
            
            if submitted:
                if not nome_convidado:
                    st.error("❌ O nome do convidado é obrigatório")
                else:
                    success, message = adicionar_convidado(
                        evento_id, nome_convidado, email, telefone, 
                        instituicao, cargo, quantidade_acompanhantes, observacoes
                    )
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
    
    # Lista de convidados do evento
    st.subheader(f"📋 Convidados do Evento")
    convidados = get_convidados_por_evento(evento_id)
    
    if not convidados:
        st.info("📭 Nenhum convidado adicionado a este evento")
        return
    
    # Estatísticas rápidas
    stats = get_estatisticas_evento(evento_id)
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Convidados", stats['total_convidados'])
        with col2:
            st.metric("Confirmados", stats['status'].get('Confirmado', 0))
        with col3:
            st.metric("Pendentes", stats['status'].get('Pendente', 0))
        with col4:
            st.metric("Total Pessoas", stats['total_confirmados'])
    
    # Tabela de convidados
    for convidado in convidados:
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                status_color = {
                    'Pendente': '⚪',
                    'Confirmado': '🟢', 
                    'Cancelado': '🔴'
                }
                st.write(f"**{convidado[2]}** {status_color.get(convidado[8], '⚪')}")
                st.write(f"📧 {convidado[3] or 'Sem e-mail'} | 📞 {convidado[4] or 'Sem telefone'}")
                if convidado[5]:
                    st.write(f"🏢 {convidado[5]} {f'| {convidado[6]}' if convidado[6] else ''}")
                if convidado[7] > 0:
                    st.write(f"👥 {convidado[7]} acompanhante(s)")
            
            with col2:
                # Seletor de status
                novo_status = st.selectbox(
                    "Status:",
                    ["Pendente", "Confirmado", "Cancelado"],
                    index=["Pendente", "Confirmado", "Cancelado"].index(convidado[8]),
                    key=f"status_{convidado[0]}"
                )
                if novo_status != convidado[8]:
                    if st.button("💾", key=f"save_{convidado[0]}"):
                        success, message = atualizar_status_convidado(convidado[0], novo_status)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
            
            with col3:
                # Gerar convite individual
                evento = get_evento_por_id(evento_id)
                html_convite = gerar_convite_html(evento, convidado)
                st.download_button(
                    label="🎫 Convite",
                    data=html_convite,
                    file_name=f"convite_{convidado[2]}_{evento[1]}.html",
                    mime="text/html",
                    key=f"convite_{convidado[0]}"
                )
            
            st.markdown("---")

def show_relatorios():
    """Interface para relatórios e exportação"""
    st.header("📊 Relatórios e Exportação")
    
    eventos = get_eventos_convites()
    if not eventos:
        st.info("📭 Nenhum evento cadastrado")
        return
    
    evento_options = {f"{evento[1]} ({evento[3].strftime('%d/%m/%Y')})": evento[0] for evento in eventos}
    evento_selecionado_nome = st.selectbox("Selecione o Evento para Relatório:", list(evento_options.keys()))
    evento_id = evento_options[evento_selecionado_nome]
    
    # Estatísticas detalhadas
    stats = get_estatisticas_evento(evento_id)
    if stats:
        st.subheader("📈 Estatísticas do Evento")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Distribuição por Status:**")
            for status, count in stats['status'].items():
                st.write(f"- {status}: {count}")
        
        with col2:
            st.write("**Totais:**")
            st.write(f"- Total de Convidados: {stats['total_convidados']}")
            st.write(f"- Total Confirmados: {stats['status'].get('Confirmado', 0)}")
            st.write(f"- Acompanhantes: {stats['total_acompanhantes']}")
            st.write(f"- Total de Pessoas: {stats['total_confirmados']}")
    
    # Exportação
    st.subheader("📤 Exportar Dados")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Exportar lista de convidados
        if st.button("📊 Exportar Lista de Convidados (CSV)"):
            csv_data = exportar_convidados_csv(evento_id)
            if csv_data:
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name=f"convidados_{evento_selecionado_nome}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.error("❌ Nenhum dado para exportar")
    
    with col2:
        # Exportar convites em lote
        if st.button("🎫 Gerar Convites em Lote"):
            convidados = get_convidados_por_evento(evento_id)
            evento = get_evento_por_id(evento_id)
            
            if convidados:
                st.success(f"✅ {len(convidados)} convites prontos para download")
                
                for convidado in convidados:
                    html_convite = gerar_convite_html(evento, convidado)
                    st.download_button(
                        label=f"📥 {convidado[2]}",
                        data=html_convite,
                        file_name=f"convite_{convidado[2]}.html",
                        mime="text/html",
                        key=f"batch_{convidado[0]}"
                    )
            else:
                st.error("❌ Nenhum convidado para gerar convites")

# =============================================================================
# EXECUÇÃO
# =============================================================================

if __name__ == "__main__":
    main()
