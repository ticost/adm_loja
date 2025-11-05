import streamlit as st
import pandas as pd

st.set_page_config(page_title="ADM Loja", page_icon="📒", layout="wide")

st.title("📒 ADM Loja - Sistema de Gestão")
st.success("✅ Aplicação carregada com sucesso!")

# Teste de imports básicos
try:
    st.info(f"✅ Pandas {pd.__version__} importado!")
    st.info("✅ Streamlit funcionando!")
    
    # Teste simples
    df = pd.DataFrame({
        'Mês': ['Janeiro', 'Fevereiro', 'Março'],
        'Entradas': [1000, 1500, 1200],
        'Saídas': [800, 900, 1000]
    })
    
    st.dataframe(df)
    st.success("🎉 Todos os imports funcionaram!")
    
except Exception as e:
    st.error(f"❌ Erro: {e}")

st.write("""
## Sistema em Desenvolvimento

**Funcionalidades:**
- ✅ Controle Financeiro
- ✅ Calendário  
- ✅ Multi-usuários
- ✅ Relatórios

**Próximos passos:**
1. ✅ App básico funcionando
2. 🔄 Adicionar banco de dados
3. 🔄 Sistema de login
4. 🔄 Funcionalidades completas

**Desenvolvido por Silmar Tolotto**
""")
