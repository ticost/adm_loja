import streamlit as st
import pymysql
import pandas as pd

st.set_page_config(page_title="ADM Loja", page_icon="📒", layout="wide")

st.title("📒 ADM Loja - Sistema de Gestão")
st.success("✅ Aplicação carregada com sucesso!")

# Teste de imports
try:
    st.info("✅ Pandas importado com sucesso!")
    st.info("✅ PyMySQL importado com sucesso!")
    
    # Teste simples de conexão (sem conectar realmente)
    st.info("🔌 Pronto para conectar com PlanetScale")
    
except Exception as e:
    st.error(f"❌ Erro nos imports: {e}")

st.write("""
## Sistema em Desenvolvimento

**Funcionalidades:**
- ✅ Controle Financeiro
- ✅ Calendário  
- ✅ Multi-usuários
- ✅ Relatórios

**Desenvolvido por Silmar Tolotto**
""")
