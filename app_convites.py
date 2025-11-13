# app_convites.py
import streamlit as st
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont
import io
import os

st.set_page_config(page_title="Gerador de Convites (Times-Roman)", layout="wide")
st.title("🎉 Gerador de Convites — Times-Roman (fixo), alinhamento à esquerda")

# === Sidebar instruções ===
with st.sidebar:
    st.header("📘 Instruções")
    st.markdown("""
Preencha apenas o conteúdo e o tamanho da fonte dos textos.
Posições X/Y e alinhamento são fixos. Fonte: Times-Roman.

Posições padrão (não alterar):
- Texto 1: X=300, Y=240, Fonte=18 — Nome do VM  
- Texto 2: X=300, Y=300, Fonte=13 — Descrição da sessão  
- Texto 3: X=350, Y=330, Fonte=23 — Nome candidato 1  
- Texto 4: X=350, Y=390, Fonte=23 — Nome candidato 2  
- Texto 5: X=268, Y=465, Fonte=10 — Data e hora
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
        "/Library/Fonts/Times New Roman.ttf"
    ]
    for p in caminhos:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, tamanho)
            except:
                pass
    return ImageFont.load_default()

if uploaded_file:
    # Carregar modelo e ajustar para A4 paisagem (842x595)
    modelo = Image.open(uploaded_file).convert("RGBA")
    modelo = modelo.resize((842, 595))

    st.subheader("🖼️ Modelo carregado")
    st.image(modelo, use_column_width=True)

    st.write("---")
    st.subheader("✏️ Preencha os textos (Times-Roman, alinhamento à esquerda)")

    textos_config = []
    for i in range(5):
        st.markdown(f"**Texto {i+1}**")
        conteudo = st.text_input(f"Conteúdo do texto {i+1}", value="", key=f"conteudo_{i}")
        colx, coly, colfont = st.columns([1, 1, 2])
        with colx:
            st.number_input(f"Posição X (fixa)", value=posicoes_padrao[i]["x"], disabled=True, key=f"x_{i}")
        with coly:
            st.number_input(f"Posição Y (fixa)", value=posicoes_padrao[i]["y"], disabled=True, key=f"y_{i}")
        with colfont:
            tamanho = st.number_input(
                f"Tamanho da fonte do texto {i+1}",
                min_value=6,
                max_value=120,
                value=posicoes_padrao[i]["tamanho_default"],
                key=f"tamanho_{i}"
            )
        cor = st.color_picker(f"Cor do texto {i+1}", "#000000", key=f"cor_{i}")
        st.write("---")

        textos_config.append({
            "conteudo": conteudo,
            "x": posicoes_padrao[i]["x"],
            "y": posicoes_padrao[i]["y"],
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
            # medir altura do texto usando PIL (mesma fonte/tamanho da prévia)
            pil_font = carregar_fonte_pil(t["tamanho"])
            try:
                # getbbox retorna (x0,y0,x1,y1)
                bbox = pil_font.getbbox(t["conteudo"])
                text_height = bbox[3] - bbox[1]
            except Exception:
                # fallback simples: usar tamanho de fonte como aproximação
                text_height = t["tamanho"]

            # converter coordenada Y (PIL top-based) -> ReportLab baseline-based
            # ReportLab origin is bottom-left, PIL origin is top-left:
            y_pdf = altura_pagina - t["y"] - text_height

            # aplicar cor e fonte (Times-Roman) — alinhamento à esquerda
            r, g, b = tuple(int(t["cor"].lstrip("#")[i:i+2], 16) for i in (0,2,4))
            c.setFillColorRGB(r/255.0, g/255.0, b/255.0)
            c.setFont("Times-Roman", t["tamanho"])
            c.drawString(t["x"], y_pdf, t["conteudo"])

        c.showPage()
        c.save()
        buffer.seek(0)

        st.success("✅ Convite gerado com sucesso — alinhamento corrigido!")
        st.download_button("📥 Baixar PDF", data=buffer, file_name="convite_timesroman.pdf", mime="application/pdf")

else:
    st.info("📎 Faça upload do modelo do convite (JPG/PNG) para começar.")
