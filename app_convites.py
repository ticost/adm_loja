# app_convites.py
import streamlit as st
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont
import io
import os

# Configuração da página
st.set_page_config(
    page_title="Sistema de Convites",
    page_icon="🎫",
    layout="wide"
)

# =============================================================================
# FUNÇÃO PRINCIPAL DO SISTEMA DE CONVITES
# =============================================================================

def main():
    """Função principal do sistema de convites"""
    st.title("🎉 Gerador de Convites — Times-Roman (fixo), alinhamento à esquerda")

    # === Sidebar instruções ===
    with st.sidebar:
        st.header("📘 Instruções")
        st.markdown("""
    Preencha apenas o conteúdo e o tamanho da fonte dos textos.
    Posições X/Y e alinhamento são fixos. Fonte: Times-Roman.

    Posições padrão (não alterar):
    - Texto 1: X=300, Y=240, Fonte=18 — Venerável Mestre  
    - Texto 2: X=300, Y=300, Fonte=13 — Tipo de sessão  
    - Texto 3: X=350, Y=330, Fonte=23 — Nome da pessoa 1ª  
    - Texto 4: X=350, Y=390, Fonte=23 — Nome da pessoa 2ª  
    - Texto 5: X=268, Y=465, Fonte=10 — Data e hora de início
        """)

    # === Upload do modelo ===
    uploaded_file = st.file_uploader("📤 Faça upload do modelo do convite (JPG/PNG)", type=["jpg", "jpeg", "png"])

    # === Posições fixas ===
    posicoes_padrao = [
        {"x": 300, "y": 240, "tamanho_default": 18},
        {"x": 300, "y": 300, "tamanho_default": 13},
        {"x": 350, "y": 330, "tamanho_default": 23},
        {"x": 350, "y": 390, "tamanho_default": 23},
        {"x": 268, "y": 465, "tamanho_default": 10},
    ]

    # === Função para carregar fonte PIL (para medir texto na prévia e calcular altura) ===
    def carregar_fonte_pil(tamanho):
        caminhos = [
            "C:/Windows/Fonts/times.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
            "/Library/Fonts/Times New Roman.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        ]
        for p in caminhos:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, tamanho)
                except:
                    pass
        # Fallback para fonte padrão se Times não for encontrada
        try:
            return ImageFont.truetype("arial.ttf", tamanho)
        except:
            return ImageFont.load_default()

    if uploaded_file:
        try:
            # Carregar modelo e ajustar para A4 paisagem (842x595)
            modelo = Image.open(uploaded_file).convert("RGBA")
            modelo = modelo.resize((842, 595))

            st.subheader("🖼️ Modelo carregado")
            st.image(modelo, use_column_width=True)

            st.write("---")
            st.subheader("✏️ Preencha os textos (Times-Roman, alinhamento à esquerda)")

            textos_config = []
            
            # Texto 1 - Venerável Mestre
            st.markdown(f"**Texto 1 - Venerável Mestre**")
            conteudo = st.text_input(f"Conteúdo do texto 1 - Venerável Mestre", value="", key=f"conteudo_0")
            colx, coly, colfont = st.columns([1, 1, 2])
            with colx:
                st.number_input(f"Posição X (fixa)", value=posicoes_padrao[0]["x"], disabled=True, key=f"x_0")
            with coly:
                st.number_input(f"Posição Y (fixa)", value=posicoes_padrao[0]["y"], disabled=True, key=f"y_0")
            with colfont:
                tamanho = st.number_input(
                    f"Tamanho da fonte do texto 1 - Venerável Mestre",
                    min_value=6,
                    max_value=120,
                    value=posicoes_padrao[0]["tamanho_default"],
                    key=f"tamanho_0"
                )
            cor = st.color_picker(f"Cor do texto 1 - Venerável Mestre", "#000000", key=f"cor_0")
            st.write("---")

            textos_config.append({
                "conteudo": conteudo,
                "x": posicoes_padrao[0]["x"],
                "y": posicoes_padrao[0]["y"],
                "tamanho": tamanho,
                "cor": cor
            })

            # Texto 2 - Tipo de sessão
            st.markdown(f"**Texto 2 - Tipo de sessão**")
            conteudo = st.text_input(f"Conteúdo do texto 2 - Tipo de sessão", value="", key=f"conteudo_1")
            colx, coly, colfont = st.columns([1, 1, 2])
            with colx:
                st.number_input(f"Posição X (fixa)", value=posicoes_padrao[1]["x"], disabled=True, key=f"x_1")
            with coly:
                st.number_input(f"Posição Y (fixa)", value=posicoes_padrao[1]["y"], disabled=True, key=f"y_1")
            with colfont:
                tamanho = st.number_input(
                    f"Tamanho da fonte do texto 2 - Tipo de sessão",
                    min_value=6,
                    max_value=120,
                    value=posicoes_padrao[1]["tamanho_default"],
                    key=f"tamanho_1"
                )
            cor = st.color_picker(f"Cor do texto 2 - Tipo de sessão", "#000000", key=f"cor_1")
            st.write("---")

            textos_config.append({
                "conteudo": conteudo,
                "x": posicoes_padrao[1]["x"],
                "y": posicoes_padrao[1]["y"],
                "tamanho": tamanho,
                "cor": cor
            })

            # Texto 3 - Nome da pessoa 1ª
            st.markdown(f"**Texto 3 - Nome da pessoa 1ª**")
            conteudo = st.text_input(f"Conteúdo do texto 3 - Nome da pessoa 1ª", value="", key=f"conteudo_2")
            colx, coly, colfont = st.columns([1, 1, 2])
            with colx:
                st.number_input(f"Posição X (fixa)", value=posicoes_padrao[2]["x"], disabled=True, key=f"x_2")
            with coly:
                st.number_input(f"Posição Y (fixa)", value=posicoes_padrao[2]["y"], disabled=True, key=f"y_2")
            with colfont:
                tamanho = st.number_input(
                    f"Tamanho da fonte do texto 3 - Nome da pessoa 1ª",
                    min_value=6,
                    max_value=120,
                    value=posicoes_padrao[2]["tamanho_default"],
                    key=f"tamanho_2"
                )
            cor = st.color_picker(f"Cor do texto 3 - Nome da pessoa 1ª", "#000000", key=f"cor_2")
            st.write("---")

            textos_config.append({
                "conteudo": conteudo,
                "x": posicoes_padrao[2]["x"],
                "y": posicoes_padrao[2]["y"],
                "tamanho": tamanho,
                "cor": cor
            })

            # Texto 4 - Nome da pessoa 2ª
            st.markdown(f"**Texto 4 - Nome da pessoa 2ª**")
            conteudo = st.text_input(f"Conteúdo do texto 4 - Nome da pessoa 2ª", value="", key=f"conteudo_3")
            colx, coly, colfont = st.columns([1, 1, 2])
            with colx:
                st.number_input(f"Posição X (fixa)", value=posicoes_padrao[3]["x"], disabled=True, key=f"x_3")
            with coly:
                st.number_input(f"Posição Y (fixa)", value=posicoes_padrao[3]["y"], disabled=True, key=f"y_3")
            with colfont:
                tamanho = st.number_input(
                    f"Tamanho da fonte do texto 4 - Nome da pessoa 2ª",
                    min_value=6,
                    max_value=120,
                    value=posicoes_padrao[3]["tamanho_default"],
                    key=f"tamanho_3"
                )
            cor = st.color_picker(f"Cor do texto 4 - Nome da pessoa 2ª", "#000000", key=f"cor_3")
            st.write("---")

            textos_config.append({
                "conteudo": conteudo,
                "x": posicoes_padrao[3]["x"],
                "y": posicoes_padrao[3]["y"],
                "tamanho": tamanho,
                "cor": cor
            })

            # Texto 5 - Inserir a data e hora de início
            st.markdown(f"**Texto 5 - Data e hora de início**")
            conteudo = st.text_input(f"Conteúdo do texto 5 - Data e hora de início", value="", key=f"conteudo_4")
            colx, coly, colfont = st.columns([1, 1, 2])
            with colx:
                st.number_input(f"Posição X (fixa)", value=posicoes_padrao[4]["x"], disabled=True, key=f"x_4")
            with coly:
                st.number_input(f"Posição Y (fixa)", value=posicoes_padrao[4]["y"], disabled=True, key=f"y_4")
            with colfont:
                tamanho = st.number_input(
                    f"Tamanho da fonte do texto 5 - Data e hora de início",
                    min_value=6,
                    max_value=120,
                    value=posicoes_padrao[4]["tamanho_default"],
                    key=f"tamanho_4"
                )
            cor = st.color_picker(f"Cor do texto 5 - Data e hora de início", "#000000", key=f"cor_4")
            st.write("---")

            textos_config.append({
                "conteudo": conteudo,
                "x": posicoes_padrao[4]["x"],
                "y": posicoes_padrao[4]["y"],
                "tamanho": tamanho,
                "cor": cor
            })

            # --- Pré-visualização opcional com texto ---
            mostrar_texto = st.checkbox("👁️ Mostrar textos na pré-visualização (opcional)", value=True)
            if mostrar_texto:
                preview = modelo.copy()
                draw = ImageDraw.Draw(preview)
                for t in textos_config:
                    if t["conteudo"].strip():
                        pil_font = carregar_fonte_pil(t["tamanho"])
                        cor_rgb = tuple(int(t["cor"].lstrip("#")[i:i+2], 16) for i in (0,2,4))
                        # alinhamento esquerda (posições fixas já definidas)
                        draw.text((t["x"], t["y"]), t["conteudo"], font=pil_font, fill=cor_rgb)
                st.image(preview, caption="Pré-visualização com texto (somente visual)", use_column_width=True)
            else:
                st.image(modelo, caption="Pré-visualização do modelo (sem texto)", use_column_width=True)

            # --- Gerar PDF (texto aplicado apenas no PDF, com conversão de coordenadas) ---
            if st.button("📄 Gerar PDF"):
                try:
                    buffer = io.BytesIO()
                    c = canvas.Canvas(buffer, pagesize=landscape(A4))
                    largura_pagina, altura_pagina = landscape(A4)  # em pontos (aprox 842x595)

                    # Inserir imagem de fundo (modelo) sem texto
                    img_temp = io.BytesIO()
                    modelo.save(img_temp, format="PNG")
                    img_temp.seek(0)
                    c.drawImage(ImageReader(img_temp), 0, 0, width=largura_pagina, height=altura_pagina)

                    # Adicionar textos no PDF — converter Y de topo->baseline:
                    for t in textos_config:
                        if not t["conteudo"].strip():
                            continue
                        
                        # Converter coordenada Y (PIL top-based) -> ReportLab baseline-based
                        # ReportLab origin is bottom-left, PIL origin is top-left:
                        # Usando aproximação mais simples para evitar problemas de medição
                        y_pdf = altura_pagina - t["y"] - (t["tamanho"] * 0.7)

                        # aplicar cor e fonte (Times-Roman) — alinhamento à esquerda
                        r, g, b = tuple(int(t["cor"].lstrip("#")[i:i+2], 16) for i in (0,2,4))
                        c.setFillColorRGB(r/255.0, g/255.0, b/255.0)
                        c.setFont("Times-Roman", t["tamanho"])
                        c.drawString(t["x"], y_pdf, t["conteudo"])

                    c.showPage()
                    c.save()
                    buffer.seek(0)

                    st.success("✅ Convite gerado com sucesso — alinhamento corrigido!")
                    st.download_button(
                        "📥 Baixar PDF", 
                        data=buffer, 
                        file_name="convite_timesroman.pdf", 
                        mime="application/pdf"
                    )

                except Exception as e:
                    st.error(f"❌ Erro ao gerar PDF: {str(e)}")
                    st.info("💡 Verifique se todos os campos estão preenchidos corretamente.")

        except Exception as e:
            st.error(f"❌ Erro ao processar imagem: {str(e)}")
            st.info("💡 Tente usar uma imagem com formato JPG ou PNG válido.")

    else:
        st.info("📎 Faça upload do modelo do convite (JPG/PNG) para começar.")

# =============================================================================
# EXECUÇÃO
# =============================================================================

if __name__ == "__main__":
    main()
