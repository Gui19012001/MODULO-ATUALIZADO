import streamlit as st
import pandas as pd
import datetime
import pytz
import base64
from supabase import create_client
import os
from dotenv import load_dotenv
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go

# =============================
# Carregar variáveis de ambiente
# =============================
env_path = Path(__file__).parent / "teste.env"  # Ajuste se necessário
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =============================
# Configurações iniciais
# =============================
TZ = pytz.timezone("America/Sao_Paulo")
itens = ["Etiqueta", "Tambor + Parafuso", "Solda", "Pintura", "Borracha ABS"]
usuarios = {"joao": "1234", "maria": "abcd", "admin": "admin"}

# =============================
# Funções do Supabase
# =============================
def carregar_checklists():
    response = supabase.table("checklists").select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)
    return df

def salvar_checklist(serie, resultados, usuario, foto_etiqueta=None, reinspecao=False):
    existe = supabase.table("checklists").select("numero_serie").eq("numero_serie", serie).execute()
    if not reinspecao and existe.data:
        st.error("⚠️ INVÁLIDO! DUPLICIDADE – Este Nº de Série já foi inspecionado.")
        return None

    reprovado = any(info['status'] == "Não Conforme" for info in resultados.values())
    data_hora = datetime.datetime.now(TZ)

    foto_base64 = None
    if foto_etiqueta is not None:
        try:
            foto_bytes = foto_etiqueta.getvalue()
            foto_base64 = base64.b64encode(foto_bytes).decode()
        except Exception as e:
            st.error(f"Erro ao processar a foto: {e}")
            foto_base64 = None

    for item, info in resultados.items():
        supabase.table("checklists").insert({
            "numero_serie": serie,
            "item": item,
            "status": info['status'],
            "observacoes": info['obs'],
            "inspetor": usuario,
            "data_hora": data_hora.isoformat(),
            "produto_reprovado": "Sim" if reprovado else "Não",
            "reinspecao": "Sim" if reinspecao else "Não",
            "foto_etiqueta": foto_base64 if item == "Etiqueta" else None
        }).execute()

    st.success(f"Checklist salvo no Supabase para o Nº de Série {serie}")
    return True

def carregar_apontamentos():
    response = supabase.table("apontamentos").select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)
    return df

def salvar_apontamento(serie):
    hoje = datetime.datetime.now(TZ).date()
    response = supabase.table("apontamentos")\
        .select("*")\
        .eq("numero_serie", serie)\
        .gte("data_hora", datetime.datetime.combine(hoje, datetime.time.min).isoformat())\
        .lte("data_hora", datetime.datetime.combine(hoje, datetime.time.max).isoformat())\
        .execute()

    if response.data:
        return False  # Já registrado hoje

    data_hora = datetime.datetime.now(TZ).isoformat()
    res = supabase.table("apontamentos").insert({
        "numero_serie": serie,
        "data_hora": data_hora
    }).execute()

    if res.data and not getattr(res, "error", None):
        return True
    else:
        st.error(f"Erro ao inserir apontamento: {getattr(res, 'error', 'Desconhecido')}")
        return False

# =============================
# Funções do App
# =============================
def login():
    st.sidebar.title("Login")
    if 'logado' not in st.session_state:
        st.session_state['logado'] = False
        st.session_state['usuario'] = None

    if not st.session_state['logado']:
        usuario = st.sidebar.text_input("Usuário")
        senha = st.sidebar.text_input("Senha", type="password")
        if st.sidebar.button("Entrar"):
            if usuario in usuarios and usuarios[usuario] == senha:
                st.session_state['logado'] = True
                st.session_state['usuario'] = usuario
                st.sidebar.success(f"Bem vindo, {usuario}!")
            else:
                st.sidebar.error("Usuário ou senha incorretos.")
        st.stop()
    else:
        st.sidebar.write(f"Logado como: {st.session_state['usuario']}")
        if st.sidebar.button("Sair"):
            st.session_state['logado'] = False
            st.session_state['usuario'] = None
            st.experimental_set_query_params()  # substituindo experimental_rerun

# =============================
# Checklist
# =============================
def checklist_qualidade():
    st.markdown("## ✔️ Checklist de Qualidade")

    hoje = datetime.datetime.now(TZ).date()
    df_apont = carregar_apontamentos()
    if not df_apont.empty:
        start_of_day = TZ.localize(datetime.datetime.combine(hoje, datetime.time.min))
        end_of_day = TZ.localize(datetime.datetime.combine(hoje, datetime.time.max))
        df_hoje = df_apont[
            (df_apont["data_hora"] >= start_of_day) &
            (df_apont["data_hora"] <= end_of_day)
        ]
    else:
        df_hoje = pd.DataFrame()

    df_checks = carregar_checklists()
    if not df_hoje.empty:
        codigos_hoje = df_hoje["numero_serie"].unique()
        codigos_com_checklist = df_checks["numero_serie"].unique() if not df_checks.empty else []
        codigos_disponiveis = [c for c in codigos_hoje if c not in codigos_com_checklist]
    else:
        codigos_disponiveis = []

    if len(codigos_disponiveis) == 0:
        st.info("Nenhum código disponível para inspeção. Todos já foram inspecionados.")
        return

    if "codigo_atual" not in st.session_state:
        st.session_state["codigo_atual"] = codigos_disponiveis[0]

    numero_serie = st.selectbox(
        "Selecione o Número de Série para Inspeção",
        codigos_disponiveis,
        index=codigos_disponiveis.index(st.session_state["codigo_atual"])
    )

    with st.form(key=f"form_checklist_{numero_serie}"):
        resultados = {}
        for item in itens:
            st.markdown(f"### {item}")
            status = st.radio(f"Status - {item}", ["Conforme", "Não Conforme", "N/A"], index=2, key=f"{numero_serie}_{item}")
            obs = st.text_area(f"Observações - {item}", key=f"obs_{numero_serie}_{item}")
            resultados[item] = {"status": status, "obs": obs}

        submit_button = st.form_submit_button("Salvar Checklist")

        if submit_button:
            if all(r['status'] == "N/A" for r in resultados.values()):
                st.error("Checklist inválido: todos os itens estão como N/A.")
            else:
                salvar_checklist(numero_serie, resultados, st.session_state['usuario'])
                st.success(f"Checklist do Nº de Série {numero_serie} salvo com sucesso!")

                codigos_disponiveis = [c for c in codigos_disponiveis if c != numero_serie]
                if codigos_disponiveis:
                    st.session_state["codigo_atual"] = codigos_disponiveis[0]
                    st.experimental_set_query_params(updated=str(datetime.datetime.now()))
                else:
                    st.info("Todos os códigos foram inspecionados hoje.")

# =============================
# Reinspeção
# =============================
def reinspecao():
    df = carregar_checklists()

    if not df.empty:
        ultimos = df.sort_values("data_hora").groupby("numero_serie").tail(1)
        reprovados = ultimos[
            (ultimos["produto_reprovado"] == "Sim") & (ultimos["reinspecao"] == "Não")
        ]["numero_serie"].unique()
    else:
        reprovados = []

    if len(reprovados) > 0:
        st.markdown("## 🔄 Reinspeção de Produtos Reprovados")
        serie_sel = st.selectbox("Selecione o Nº de Série reprovado", reprovados)

        if serie_sel:
            with st.form(key=f"form_reinspecao_{serie_sel}"):
                resultados = {}
                for item in itens:
                    st.markdown(f"### {item}")
                    status = st.radio(f"Status - {item} (Reinspeção)", ["Conforme", "Não Conforme", "N/A"], index=2, key=f"re_{serie_sel}_{item}")
                    obs = st.text_area(f"Observações - {item}", key=f"re_obs_{serie_sel}_{item}")
                    resultados[item] = {"status": status, "obs": obs}

                submit_button = st.form_submit_button("Salvar Reinspeção")

                if submit_button:
                    salvar_checklist(serie_sel, resultados, st.session_state['usuario'], reinspecao=True)
                    st.success(f"Reinspeção do Nº de Série {serie_sel} salva com sucesso!")
    else:
        st.info("Nenhum produto reprovado para reinspeção.")

# =============================
# Histórico Produção
# =============================
def mostrar_historico_producao():
    st.markdown("## 📚 Histórico de Produção")
    df_apont = carregar_apontamentos()
    if df_apont.empty:
        st.info("Nenhum apontamento registrado até agora.")
        return

    # Filtro de data
    data_inicio = st.date_input("Data Inicial", value=df_apont["data_hora"].min().date())
    data_fim = st.date_input("Data Final", value=df_apont["data_hora"].max().date())

    df_filtrado = df_apont[
        (df_apont["data_hora"].dt.date >= data_inicio) &
        (df_apont["data_hora"].dt.date <= data_fim)
    ].sort_values("data_hora", ascending=False)

    st.dataframe(df_filtrado[["numero_serie", "data_hora"]], use_container_width=True)

# =============================
# Histórico Qualidade
# =============================
def mostrar_historico_qualidade():
    st.markdown("## 📚 Histórico de Inspeção de Qualidade")
    df_checks = carregar_checklists()
    if df_checks.empty:
        st.info("Nenhum checklist registrado até agora.")
        return

    data_inicio = st.date_input("Data Inicial", value=df_checks["data_hora"].min().date())
    data_fim = st.date_input("Data Final", value=df_checks["data_hora"].max().date())

    df_filtrado = df_checks[
        (df_checks["data_hora"].dt.date >= data_inicio) &
        (df_checks["data_hora"].dt.date <= data_fim)
    ].sort_values("data_hora", ascending=False)

    st.dataframe(
        df_filtrado[[
            "numero_serie", "item", "status", "observacoes",
            "inspetor", "produto_reprovado", "reinspecao", "data_hora"
        ]],
        use_container_width=True
    )

# =============================
# Dashboard Produção
# =============================
def painel_dashboard():
    def processar_codigo_barras():
        codigo_barras = st.session_state["codigo_barras"]
        if codigo_barras:
            if not codigo_barras.isdigit():
                st.warning("Apenas números são permitidos no código de barras!")
                st.session_state["codigo_barras"] = ""
                return
            sucesso = salvar_apontamento(codigo_barras.strip())
            if sucesso:
                st.success(f"Código {codigo_barras} registrado com sucesso!")
            else:
                st.warning(f"Código {codigo_barras} já registrado hoje ou erro.")
            st.session_state["codigo_barras"] = ""

    st.markdown("# 📊 Painel de Apontamentos")
    st.text_input("Leia o Código de Barras aqui:", key="codigo_barras", on_change=processar_codigo_barras)

    # ================= Filtro de Datas =================
    hoje = datetime.datetime.now(TZ).date()
    data_selecionada = st.date_input("Selecione o intervalo de datas:", value=(hoje, hoje))
    if isinstance(data_selecionada, tuple):
        data_inicio, data_fim = data_selecionada
    else:
        data_inicio = data_fim = data_selecionada

    df_apont = carregar_apontamentos()
    if not df_apont.empty:
        start_date = TZ.localize(datetime.datetime.combine(data_inicio, datetime.time.min))
        end_date = TZ.localize(datetime.datetime.combine(data_fim, datetime.time.max))
        df_filtrado = df_apont[(df_apont["data_hora"] >= start_date) & (df_apont["data_hora"] <= end_date)]
    else:
        df_filtrado = pd.DataFrame()

    total_lidos = len(df_filtrado)

    # ================= Meta acumulada por hora =================
    meta_hora = {
        datetime.time(7, 0): 22,
        datetime.time(8, 0): 22,
        datetime.time(9, 0): 22,
        datetime.time(10, 0): 22,
        datetime.time(11, 10): 26,
        datetime.time(12, 10): 0,
        datetime.time(13, 0): 18,
        datetime.time(14, 0): 22,
        datetime.time(15, 0): 22,
        datetime.time(15, 48): 12
    }

    meta_acumulada = 0
    hora_atual = datetime.datetime.now(TZ)
    for h, m in meta_hora.items():
        horario_atual = TZ.localize(datetime.datetime.combine(hoje, h))
        if horario_atual <= hora_atual:
            meta_acumulada += m

    atraso = meta_acumulada - total_lidos if total_lidos < meta_acumulada else 0

    # ================= % de aprovação apenas para o mesmo dia =================
    df_checks = carregar_checklists()
    if not df_checks.empty and not df_filtrado.empty:
        df_checks_filtrado = df_checks[df_checks["numero_serie"].isin(df_filtrado["numero_serie"].unique())]
    else:
        df_checks_filtrado = pd.DataFrame()

    if not df_checks_filtrado.empty:
        series_with_checks = df_checks_filtrado["numero_serie"].unique()
        aprovados = 0
        total_reprovados = 0
        for serie in series_with_checks:
            checks_all_for_serie = df_checks_filtrado[df_checks_filtrado["numero_serie"] == serie].sort_values("data_hora")
            if checks_all_for_serie.empty:
                continue
            teve_reinspecao = (checks_all_for_serie["reinspecao"] == "Sim").any()
            if teve_reinspecao:
                approved = False
            else:
                ultimo = checks_all_for_serie.tail(1).iloc[0]
                approved = (ultimo["produto_reprovado"] == "Não")
            if approved:
                aprovados += 1
            else:
                total_reprovados += 1
        total_inspecionado = len(series_with_checks)
        aprovacao_perc = (aprovados / total_inspecionado) * 100 if total_inspecionado > 0 else 0.0
    else:
        aprovacao_perc = 0.0
        total_inspecionado = 0
        total_reprovados = 0

    # ========= Cartões grandes =========
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
            <div style="background-color:#DDE3FF;padding:20px;border-radius:15px;text-align:center">
                <h3>TOTAL PRODUZIDO</h3>
                <h1>{total_lidos}</h1>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
            <div style="background-color:#E5F5E5;padding:20px;border-radius:15px;text-align:center">
                <h3>% APROVAÇÃO</h3>
                <h1>{aprovacao_perc:.2f}%</h1>
                <p>Total inspecionado: {total_inspecionado}</p>
                <p>Total reprovado: {total_reprovados}</p>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        cor = "#FFCCCC" if atraso > 0 else "#DFF2DD"
        texto = f"Atraso: {atraso}" if atraso > 0 else "Dentro da Meta"
        st.markdown(f"""
            <div style="background-color:{cor};padding:20px;border-radius:15px;text-align:center">
                <h3>ATRASO</h3>
                <h1>{texto}</h1>
            </div>
        """, unsafe_allow_html=True)

    # ========= Produção hora a hora =========
    st.markdown("### ⏱️ Produção Hora a Hora")
    col_meta = st.columns(len(meta_hora))
    col_prod = st.columns(len(meta_hora))

    for i, (h, m) in enumerate(meta_hora.items()):
        produzido = len(df_filtrado[df_filtrado["data_hora"].dt.hour == h.hour])
        cor_meta = "#4CAF50"  # verde
        cor_prod = "#000000"  # preto
        col_meta[i].markdown(f"<div style='background-color:{cor_meta};color:white;padding:10px;border-radius:5px;text-align:center'><b>{h.strftime('%H:%M')}<br>{m}</b></div>", unsafe_allow_html=True)
        col_prod[i].markdown(f"<div style='background-color:{cor_prod};color:white;padding:10px;border-radius:5px;text-align:center'><b>{h.strftime('%H:%M')}<br>{produzido}</b></div>", unsafe_allow_html=True)



# =============================
# Dashboard Qualidade
# =============================
def dashboard_qualidade():
    st.markdown("# 📊 Dashboard de Qualidade")
    df_checks = carregar_checklists()

    if df_checks.empty:
        st.info("Nenhum checklist registrado ainda.")
        return

    total_inspecionado = df_checks["numero_serie"].nunique()
    ultimos_checks = df_checks.sort_values("data_hora").groupby("numero_serie").tail(1)
    aprovados = ultimos_checks[ultimos_checks["produto_reprovado"]=="Não"]["numero_serie"].nunique()
    perc_aprov = (aprovados / total_inspecionado *100) if total_inspecionado>0 else 0

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
            <div style="background-color:#DDE3FF;padding:20px;border-radius:15px;text-align:center">
                <h3>TOTAL INSPECIONADO</h3>
                <h1>{total_inspecionado}</h1>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
            <div style="background-color:#E5F5E5;padding:20px;border-radius:15px;text-align:center">
                <h3>% APROVAÇÃO</h3>
                <h1>{perc_aprov:.2f}%</h1>
            </div>
        """, unsafe_allow_html=True)

    df_nc = df_checks[df_checks["status"]=="Não Conforme"]
    if not df_nc.empty:
        pareto = df_nc.groupby("item")["numero_serie"].count().sort_values(ascending=False).reset_index()
        pareto.columns = ["Item", "Quantidade"]
        pareto["%"] = pareto["Quantidade"].cumsum() / pareto["Quantidade"].sum() * 100

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=pareto["Item"],
            y=pareto["Quantidade"],
            text=pareto["Quantidade"],
            textposition='auto',
            name="Quantidade NC"
        ))
        fig.add_trace(go.Scatter(
            x=pareto["Item"],
            y=pareto["%"],
            mode="lines+markers",
            name="% Acumulado",
            yaxis="y2"
        ))

        fig.update_layout(
            title="Pareto das Não Conformidades",
            yaxis=dict(title="Quantidade NC"),
            yaxis2=dict(title="%", overlaying="y", side="right", range=[0, 110]),
            legend=dict(x=0.8, y=1.1)
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nenhuma não conformidade registrada.")

# =============================
# App principal
# =============================
def app():
    st.set_page_config(page_title="Controle de Qualidade", layout="wide")
    login()
    menu = st.sidebar.selectbox("Menu", [
        "Dashboard Produção",
        "Inspeção de Qualidade",
        "Reinspeção",
        "Histórico de Produção",
        "Histórico de Inspeção",
        "Dashboard de Qualidade"
    ])

    if menu == "Dashboard Produção":
        painel_dashboard()
    elif menu == "Inspeção de Qualidade":
        checklist_qualidade()
    elif menu == "Reinspeção":
        reinspecao()
    elif menu == "Histórico de Produção":
        mostrar_historico_producao()
    elif menu == "Histórico de Inspeção":
        mostrar_historico_qualidade()
    elif menu == "Dashboard de Qualidade":
        dashboard_qualidade()

if __name__ == "__main__":
    app()
