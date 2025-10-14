import streamlit as st
import streamlit.components.v1 as components
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

# ================================
# Verificação do autorefresh
# ================================
try:
    from streamlit_autorefresh import st_autorefresh
    AUTORELOAD_AVAILABLE = True
except ImportError:
    AUTORELOAD_AVAILABLE = False

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
usuarios = {"admin": "admin","Maria": "maria","Catia": "catia", "Vera": "vera", "Bruno":"bruno"}

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
    # Verifica duplicidade, exceto em caso de reinspeção
    existe = supabase.table("checklists").select("numero_serie").eq("numero_serie", serie).execute()
    if not reinspecao and existe.data:
        st.error("⚠️ INVÁLIDO! DUPLICIDADE – Este Nº de Série já foi inspecionado.")
        return None

    # Determina se o produto foi reprovado
    reprovado = any(info['status'] == "Não Conforme" for info in resultados.values())

    # Pega a hora atual em São Paulo e converte para UTC
    data_hora_utc = datetime.datetime.now(TZ).astimezone(pytz.UTC).isoformat()

    # Converte a foto para base64 se houver
    foto_base64 = None
    if foto_etiqueta is not None:
        try:
            foto_bytes = foto_etiqueta.getvalue()
            foto_base64 = base64.b64encode(foto_bytes).decode()
        except Exception as e:
            st.error(f"Erro ao processar a foto: {e}")
            foto_base64 = None

    # Itera sobre os itens do checklist
    for item, info in resultados.items():
        # Monta o payload
        payload = {
            "numero_serie": serie,
            "item": item,
            "status": info.get('status', ''),
            "observacoes": info.get('obs', ''),
            "inspetor": usuario,
            "data_hora": data_hora_utc,
            "produto_reprovado": "Sim" if reprovado else "Não",
            "reinspecao": "Sim" if reinspecao else "Não"
        }

        # Só inclui a foto para o item "Etiqueta"
        if item == "Etiqueta" and foto_base64:
            payload["foto_etiqueta"] = foto_base64

        # Log de debug (opcional)
        print("Enviando para Supabase:", payload)

        # Tenta enviar para o Supabase
        try:
            supabase.table("checklists").insert(payload).execute()
        except APIError as e:
            st.error("❌ Erro ao salvar no banco de dados.")
            st.write("Código:", e.code)
            st.write("Mensagem:", e.message)
            st.write("Detalhes:", e.details)
            st.write("Dica:", e.hint)
            raise  # relança o erro se quiser encerrar a execução

    st.success(f"✅ Checklist salvo com sucesso para o Nº de Série {serie}")
    return True

def carregar_apontamentos():
    response = supabase.table("apontamentos").select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    return df




def salvar_apontamento(serie, tipo_producao=None):
    # Usa UTC sempre para evitar problemas de fuso
    agora_utc = datetime.datetime.now(datetime.timezone.utc)
    hoje_utc = agora_utc.date()

    # Define o início e fim do dia (em UTC)
    inicio_utc = datetime.datetime.combine(hoje_utc, datetime.time.min).replace(tzinfo=datetime.timezone.utc)
    fim_utc = datetime.datetime.combine(hoje_utc, datetime.time.max).replace(tzinfo=datetime.timezone.utc)

    # Verifica se já existe apontamento para o mesmo número de série no dia atual (em UTC)
    response = supabase.table("apontamentos")\
        .select("*")\
        .eq("numero_serie", serie)\
        .gte("data_hora", inicio_utc.isoformat())\
        .lte("data_hora", fim_utc.isoformat())\
        .execute()

    if response.data:
        return False  # Já registrado hoje

    # Salva novo apontamento com horário atual em UTC
    dados = {
        "numero_serie": serie,
        "data_hora": agora_utc.isoformat()  # Garantido UTC
    }

    if tipo_producao is not None:
        dados["tipo_producao"] = tipo_producao

    res = supabase.table("apontamentos").insert(dados).execute()

    if res.data and not getattr(res, "error", None):
        return True
    else:
        st.error(f"Erro ao inserir apontamento: {getattr(res, 'error', 'Desconhecido')}")
        return False




# =============================
# Funções do App
# =============================
# =============================
# Login centralizado e estilizado
# =============================
def login():
    if 'logado' not in st.session_state:
        st.session_state['logado'] = False
        st.session_state['usuario'] = None

    if not st.session_state['logado']:
        # Tela centralizada
        st.markdown("""
        <div style="
            max-width:400px;
            margin:auto;
            margin-top:100px;
            padding:40px;
            border-radius:15px;
            background: linear-gradient(135deg, #DDE3FF, #E5F5E5);
            box-shadow: 0px 0px 20px rgba(0,0,0,0.1);
            text-align:center;
        ">
            <h1 style='color:#2F4F4F;'>🔒 MÓDULO DE PRODUÇÃO</h1>
            <p style='color:#555;'>Entre com seu usuário e senha</p>
        </div>
        """, unsafe_allow_html=True)

        usuario = st.text_input("Usuário", key="login_user")
        senha = st.text_input("Senha", type="password", key="login_pass")
        if st.button("Entrar"):
            if usuario in usuarios and usuarios[usuario] == senha:
                st.session_state['logado'] = True
                st.session_state['usuario'] = usuario
                st.success(f"Bem-vindo, {usuario}!")
            else:
                st.error("Usuário ou senha incorretos.")
        st.stop()
    else:
        st.write(f"Logado como: {st.session_state['usuario']}")
        if st.button("Sair"):
            st.session_state['logado'] = False
            st.session_state['usuario'] = None
            st.experimental_set_query_params()  # força atualização da página

# ================================
# Função utilitária para status
# ================================
def status_emoji_para_texto(emoji):
    if emoji == "✅":
        return "Conforme"
    elif emoji == "❌":
        return "Não Conforme"
    else:
        return "N/A"
            
def checklist_qualidade(numero_serie, usuario): 
    st.markdown(f"## ✔️ Checklist de Qualidade – Nº de Série: {numero_serie}")

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga?",
        "Gravação do número de série da viga está legível e pintada?",
        "Etiqueta do ABS está conforme? Com número de série compátivel ao da viga? Teste do ABS está aprovado?",
        "Rodagem – tipo correto? Especifique o modelo",
        "Graxeiras estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições? Especifique o modelo:",
        "Modelo do freio correto? Especifique modelo",
        "Anéis elásticos devidamente encaixados no orifício?",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios? As tampas dos cubos dos ambos os lados são iguais?",
        "Pintura do eixo livre de oxidação,isento de escorrimento na pintura, pontos sem tinta e camada conforme padrão?",
        "Os cordões de solda do eixo estão conformes?"
    ]

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_IMETRO",
        3: "NUMERO_SERIE_VIGA",
        4: "TESTE ABS",
        5: "RODAGEM_MODELO",
        6: "GRAXEIRAS",
        7: "SISTEMA_ATUACAO",
        8: "MODELO_FREIO",
        9: "ANEIS_ELASTICOS",
        10: "CATRACA_FREIO",
        11: "TAMPA_CUBO",
        12: "PINTURA_EIXO",
        13: "SOLDA"
    }

    opcoes_modelos = {
        5: ["Single", "Aço", "Alumínio", "N/A"],
        7: ["Spring", "Cuíca", "N/A"],
        8: ["ABS", "Convencional"],
        10: ["Automático", "Manual", "N/A"],
        13: ["Conforme", "Respingo", "Falta de cordão", "Porosidade", "Falta de Fusão"]
    }

    resultados = {}
    modelos = {}

    st.write("Clique no botão correspondente a cada item:")
    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_checklist_{numero_serie}"):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 2, 2])  # pergunta + radio + modelo

            # Pergunta
            cols[0].markdown(f"**{i}. {pergunta}**")

            # Radio de conformidade
            escolha = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"resp_{numero_serie}_{i}",
                horizontal=True,
                index=None,
                label_visibility="collapsed"
            )
            resultados[i] = escolha

            # Seleção de modelos
            if i in opcoes_modelos:
                modelo = cols[2].selectbox(
                    "Modelo",
                    [""] + opcoes_modelos[i],
                    key=f"modelo_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
                modelos[i] = modelo
            else:
                modelos[i] = None

        submit = st.form_submit_button("Salvar Checklist")

        if submit:
            faltando = [i for i, resp in resultados.items() if resp is None]
            modelos_faltando = [
                i for i in opcoes_modelos
                if modelos.get(i) is None or modelos[i] == [] or modelos[i] == ""
            ]

            if faltando or modelos_faltando:
                msg = ""
                if faltando:
                    msg += f"⚠️ Responda todas as perguntas! Faltam: {[item_keys[i] for i in faltando]}\n"
                if modelos_faltando:
                    msg += f"⚠️ Preencha todos os modelos! Faltam: {[item_keys[i] for i in modelos_faltando]}"
                st.error(msg)
            else:
                # Formata para salvar no Supabase usando a palavra-chave
                dados_para_salvar = {}
                for i, resp in resultados.items():
                    chave_item = item_keys.get(i, f"Item_{i}")
                    dados_para_salvar[chave_item] = {
                        "status": "Conforme" if resp == "✅" else "Não Conforme" if resp == "❌" else "N/A",
                        "obs": modelos.get(i)
                    }

                salvar_checklist(numero_serie, dados_para_salvar, usuario)
                st.success(f"Checklist do Nº de Série {numero_serie} salvo com sucesso!")


def checklist_reinspecao(numero_serie, usuario):
    st.markdown(f"## 🔄 Reinspeção – Nº de Série: {numero_serie}")

    df_checks = carregar_checklists()  # Função que retorna o DataFrame com todos os checklists

    # Filtra apenas checklists do mesmo número de série e não reinspecionados
    df_inspecao = df_checks[
        (df_checks["numero_serie"] == numero_serie) &
        (df_checks.get("reinspecao", "Não") != "Sim")
    ]

    if df_inspecao.empty:
        st.warning("Nenhum checklist de inspeção encontrado para este número de série.")
        return False

    # Considera apenas os checklists do mesmo dia
    hoje = datetime.now().date()
    df_inspecao["data_hora"] = pd.to_datetime(df_inspecao["data_hora"])
    df_inspecao_mesmo_dia = df_inspecao[df_inspecao["data_hora"].dt.date == hoje]

    if df_inspecao_mesmo_dia.empty:
        st.warning("Nenhum checklist de inspeção encontrado para este número de série hoje.")
        return False

    checklist_original = df_inspecao_mesmo_dia.sort_values("data_hora").iloc[-1]

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga?",
        "Gravação do número de série da viga está legível e pintada?",
        "Etiqueta do ABS está conforme? Com número de série compátivel ao da viga? Teste do ABS está aprovado?",
        "Rodagem – tipo correto? Especifique o modelo",
        "Graxeiras estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições? Especifique o modelo:",
        "Modelo do freio correto? Especifique modelo",
        "Anéis elásticos devidamente encaixados no orifício?",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios? As tampas dos cubos dos ambos os lados são iguais?",
        "Pintura do eixo livre de oxidação, isento de escorrimento na pintura, pontos sem tinta e camada conforme padrão?",
        "Os cordões de solda do eixo estão conformes?"
    ]

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_IMETRO",
        3: "NUMERO_SERIE_VIGA",
        4: "TESTE ABS",
        5: "RODAGEM_MODELO",
        6: "GRAXEIRAS",
        7: "SISTEMA_ATUACAO",
        8: "MODELO_FREIO",
        9: "ANEIS_ELASTICOS",
        10: "CATRACA_FREIO",
        11: "TAMPA_CUBO",
        12: "PINTURA_EIXO",
        13: "SOLDA"
    }

    opcoes_modelos = {
        5: ["Single", "Aço", "Alumínio", "N/A"],
        7: ["Spring", "Cuíca", "N/A"],
        8: ["ABS", "Convencional"],
        10: ["Automático", "Manual", "N/A"],
        13: ["Conforme", "Respingo", "Falta de cordão", "Porosidade", "Falta de Fusão"]
    }

    resultados = {}
    modelos = {}

    st.write("Clique no botão correspondente a cada item:")
    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_reinspecao_{numero_serie}"):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 2, 2])
            chave = item_keys[i]

            # Status antigo
            status_antigo = checklist_original.get(chave, {}).get("status") if isinstance(checklist_original.get(chave), dict) else checklist_original.get(chave)
            obs_antigo = checklist_original.get(chave, {}).get("obs", "") if isinstance(checklist_original.get(chave), dict) else ""

            if status_antigo == "Conforme":
                resp_antiga = "✅"
            elif status_antigo == "Não Conforme":
                resp_antiga = "❌"
            elif status_antigo == "N/A":
                resp_antiga = "🟡"
            else:
                resp_antiga = None

            cols[0].markdown(f"**{i}. {pergunta}**")
            escolha = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"resp_reinspecao_{numero_serie}_{i}",
                horizontal=True,
                index=(["✅", "❌", "🟡"].index(resp_antiga) if resp_antida in ["✅", "❌", "🟡"] else 0),
                label_visibility="collapsed"
            )
            resultados[i] = escolha

            if i in opcoes_modelos:
                modelo = cols[2].selectbox(
                    "Modelo",
                    [""] + opcoes_modelos[i],
                    index=([""] + opcoes_modelos[i]).index(obs_antigo) if obs_antigo in opcoes_modelos[i] else 0,
                    key=f"modelo_reinspecao_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
                modelos[i] = modelo
            else:
                modelos[i] = obs_antigo

        submit = st.form_submit_button("Salvar Reinspeção")

        if submit:
            dados_para_salvar = {}
            for i, resp in resultados.items():
                chave_item = item_keys[i]
                dados_para_salvar[chave_item] = {
                    "status": "Conforme" if resp == "✅" else "Não Conforme" if resp == "❌" else "N/A",
                    "obs": modelos.get(i)
                }

            salvar_checklist(numero_serie, dados_para_salvar, usuario, reinspecao=True)
            st.success(f"Reinspeção do Nº de Série {numero_serie} salva com sucesso!")
            return True

    return False

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

    st.dataframe(df_filtrado[["numero_serie", "data_hora","tipo_producao"]], use_container_width=True)

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

# ================================
# Página de Apontamento (apenas leitor de código de barras)
# ================================
def pagina_apontamento():
    st.markdown("#  Registrar Apontamento")

    # ================= Produção hora a hora =================
    st.markdown("### ⏱️ Produção Hora a Hora")

    df_apont = carregar_apontamentos()
    tipo_producao = st.session_state.get("tipo_producao_apontamento", "Esteira")

    # Filtra apenas do dia atual e pelo tipo de produção
    df_filtrado = df_apont[
        (df_apont["tipo_producao"].str.contains(tipo_producao, case=False, na=False)) &
        (df_apont["data_hora"].dt.date == datetime.datetime.now(TZ).date())
    ] if not df_apont.empty else pd.DataFrame()

    meta_hora = {
        datetime.time(6, 0): 0,
        datetime.time(7, 0): 0,
        datetime.time(8, 0): 0,
        datetime.time(9, 0): 0,
        datetime.time(10, 0): 5,
        datetime.time(11, 0): 0,
        datetime.time(12, 0): 18,
        datetime.time(13, 0): 22,
        datetime.time(14, 0): 22,
        datetime.time(15, 0): 12,
    }

    col_meta = st.columns(len(meta_hora))
    col_prod = st.columns(len(meta_hora))

    for i, (h, m) in enumerate(meta_hora.items()):
        produzido = len(df_filtrado[df_filtrado["data_hora"].dt.hour == h.hour])
        col_meta[i].markdown(
            f"<div style='background-color:#4CAF50;color:white;padding:10px;border-radius:5px;text-align:center'><b>{h.strftime('%H:%M')}<br>{m}</b></div>",
            unsafe_allow_html=True
        )
        col_prod[i].markdown(
            f"<div style='background-color:#000000;color:white;padding:10px;border-radius:5px;text-align:center'><b>{h.strftime('%H:%M')}<br>{produzido}</b></div>",
            unsafe_allow_html=True
        )

    # ================= Tipo de produção =================
    tipo_producao = st.radio(
        "Tipo de produção:",
        ["Esteira", "Rodagem"],
        horizontal=True,
        key="tipo_producao_apontamento"
    )

    if "codigo_barras" not in st.session_state:
        st.session_state["codigo_barras"] = ""

    # ================= Input de leitura =================
    def processar_codigo():
        codigo = st.session_state["codigo_barras"].strip()
        if codigo:
            sucesso = salvar_apontamento(codigo, tipo_producao)
            if sucesso:
                st.success(f"Código {codigo} registrado com sucesso!")
            else:
                st.warning(f"Código {codigo} já registrado hoje ou erro.")
            st.session_state["codigo_barras"] = ""

    st.text_input(
        "Leia o Código de Barras:",
        key="codigo_barras",
        on_change=processar_codigo,
        placeholder="Aproxime o leitor"
    )

    # Mantém input sempre em foco
    components.html(
        """
        <script>
        function focarInput(){
            const input = window.parent.document.querySelector('input[id^="codigo_barras"]');
            if(input){ input.focus(); }
        }
        focarInput();
        new MutationObserver(focarInput).observe(
            window.parent.document.body,
            {childList: true, subtree: true}
        );
        </script>
        """,
        height=0
    )

    # ================= Últimos 10 apontamentos =================
    if not df_filtrado.empty:
        ultimos = df_filtrado.sort_values("data_hora", ascending=False).head(10)
        ultimos["data_hora_fmt"] = ultimos["data_hora"].dt.strftime("%d/%m/%Y %H:%M:%S")
        st.markdown("### 📋 Últimos 10 Apontamentos")
        st.dataframe(
            ultimos[["numero_serie", "data_hora_fmt"]].rename(columns={"data_hora_fmt": "Hora"}),
            use_container_width=True
        )
    else:
        st.info("Nenhum apontamento encontrado.")






def painel_dashboard():
    if AUTORELOAD_AVAILABLE:
        st_autorefresh(interval=60 * 1000, key="dashboard_refresh")
    else:
        st.warning(
            "Componente 'streamlit-autorefresh' não encontrado. "
            "Instale com: pip install streamlit-autorefresh (ou use o botão de atualizar)."
        )
        if st.button("Atualizar agora"):
            st.rerun()

    st.markdown("# 📊 Painel de Apontamentos")

    # ======================== filtro de datas ========================
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
        df_filtrado = df_apont[
            (df_apont["data_hora"] >= start_date) & (df_apont["data_hora"] <= end_date)
        ]
    else:
        df_filtrado = pd.DataFrame()

    total_lidos = len(df_filtrado)

    # ======================== Meta acumulada por hora ========================
    meta_hora = {
        datetime.time(6, 0): 22,
        datetime.time(7, 0): 22,
        datetime.time(8, 0): 22,
        datetime.time(9, 0): 22,
        datetime.time(10, 0): 22,
        datetime.time(11, 0): 4,
        datetime.time(12, 0): 18,
        datetime.time(13, 0): 22,
        datetime.time(14, 0): 22,
        datetime.time(15, 0): 12,
    }

    meta_acumulada = 0
    hora_atual = datetime.datetime.now(TZ)

    # só soma meta de horas que já passaram COMPLETAMENTE
    for h, m in meta_hora.items():
        horario_fechado = TZ.localize(datetime.datetime.combine(hoje, h)) + datetime.timedelta(hours=1)
        if hora_atual >= horario_fechado:
            meta_acumulada += m

    atraso = meta_acumulada - total_lidos if total_lidos < meta_acumulada else 0

    # ================= % de aprovação =================
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
            checks_all_for_serie = df_checks_filtrado[
                df_checks_filtrado["numero_serie"] == serie
            ].sort_values("data_hora")
            if checks_all_for_serie.empty:
                continue
            teve_reinspecao = (checks_all_for_serie["reinspecao"] == "Sim").any()
            approved = False if teve_reinspecao else (
                checks_all_for_serie.tail(1).iloc[0]["produto_reprovado"] == "Não"
            )
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

    # ======================= Esteira e Rodagem =======================
    if not df_filtrado.empty:
        df_esteira = df_filtrado[df_filtrado["tipo_producao"].str.contains("ESTEIRA", case=False, na=False)]
        df_rodagem = df_filtrado[df_filtrado["tipo_producao"].str.contains("RODAGEM", case=False, na=False)]
        total_esteira = len(df_esteira)
        total_rodagem = len(df_rodagem)
    else:
        total_esteira = 0
        total_rodagem = 0

    # ========= Cartões grandes =========
    col1, col2, col3 = st.columns(3)
    altura_cartao = "220px"

    # TOTAL PRODUZIDO
    with col1:
        st.markdown(f"""
        <div style="background-color:#DDE3FF;
                    height:{altura_cartao};
                    display:flex;
                    flex-direction:column;
                    justify-content:center;
                    align-items:center;
                    border-radius:15px;
                    text-align:center;
                    padding:10px;">
            <h3>TOTAL PRODUZIDO</h3>
            <h1>{total_lidos}</h1>
            <p style='font-size:16px;margin:0;'>Esteira: {total_esteira}</p>
            <p style='font-size:16px;margin:0;'>Rodagem: {total_rodagem}</p>
        </div>
        """, unsafe_allow_html=True)

    # % DE APROVAÇÃO
    with col2:
        st.markdown(f"""
        <div style="background-color:#E5F5E5;
                    height:{altura_cartao};
                    display:flex;
                    flex-direction:column;
                    justify-content:center;
                    align-items:center;
                    border-radius:15px;
                    text-align:center;
                    padding:10px;">
            <h3>% APROVAÇÃO</h3>
            <h1>{aprovacao_perc:.2f}%</h1>
            <p>Total inspecionado: {total_inspecionado}</p>
            <p>Total reprovado: {total_reprovados}</p>
        </div>
        """, unsafe_allow_html=True)

    # ATRASO
    with col3:
        cor = "#FFCCCC" if atraso > 0 else "#DFF2DD"
        texto = f"Atraso: {atraso}" if atraso > 0 else "Dentro da Meta"
        st.markdown(f"""
        <div style="background-color:{cor};
                    height:{altura_cartao};
                    display:flex;
                    flex-direction:column;
                    justify-content:center;
                    align-items:center;
                    border-radius:15px;
                    text-align:center;
                    padding:10px;">
            <h3>ATRASO</h3>
            <h1>{texto}</h1>
        </div>
        """, unsafe_allow_html=True)

    # ================== Produção hora a hora ==================
    st.markdown("### ⏱️ Produção Hora a Hora")
    col_meta = st.columns(len(meta_hora))
    col_prod = st.columns(len(meta_hora))

    for i, (h, m) in enumerate(meta_hora.items()):
        produzido = len(df_filtrado[df_filtrado["data_hora"].dt.hour == h.hour])
        col_meta[i].markdown(
            f"<div style='background-color:#4CAF50;color:white;padding:10px;border-radius:5px;text-align:center'><b>{h.strftime('%H:%M')}<br>{m}</b></div>",
            unsafe_allow_html=True
        )
        col_prod[i].markdown(
            f"<div style='background-color:#000000;color:white;padding:10px;border-radius:5px;text-align:center'><b>{h.strftime('%H:%M')}<br>{produzido}</b></div>",
            unsafe_allow_html=True
        )

    # ================== Listagem Esteira / Rodagem ==================
    if not df_filtrado.empty:
        st.markdown("### Produção Esteira")
        st.dataframe(df_esteira[["numero_serie", "data_hora"]], use_container_width=True)

        st.markdown("### Produção Rodagem")
        st.dataframe(df_rodagem[["numero_serie", "data_hora"]], use_container_width=True)
    else:
        st.info("Nenhum apontamento registrado no período selecionado.")



def dashboard_qualidade():
    st.markdown("# 📊 Dashboard de Qualidade")

    # ================= Filtro de datas =================
    hoje = datetime.datetime.now(TZ).date()
    data_selecionada = st.date_input("Selecione o intervalo de datas:", value=(hoje, hoje))
    if isinstance(data_selecionada, tuple):
        data_inicio, data_fim = data_selecionada
    else:
        data_inicio = data_fim = data_selecionada

    # ================= Dados de apontamentos =================
    df_apont = carregar_apontamentos()
    if not df_apont.empty:
        start_date = TZ.localize(datetime.datetime.combine(data_inicio, datetime.time.min))
        end_date = TZ.localize(datetime.datetime.combine(data_fim, datetime.time.max))
        df_filtrado = df_apont[(df_apont["data_hora"] >= start_date) & (df_apont["data_hora"] <= end_date)]
    else:
        df_filtrado = pd.DataFrame()

    total_lidos = len(df_filtrado)

    # ================= % de aprovação seguindo a mesma lógica do painel =================
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

    # ================= Cartões resumo =================
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
            <div style="background-color:#DDE3FF;padding:20px;border-radius:15px;text-align:center">
                <h3>TOTAL INSPECIONADO</h3>
                <h1>{total_inspecionado}</h1>
                <p>Total reprovado: {total_reprovados}</p>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
            <div style="background-color:#E5F5E5;padding:20px;border-radius:15px;text-align:center">
                <h3>% APROVAÇÃO</h3>
                <h1>{aprovacao_perc:.2f}%</h1>
            </div>
        """, unsafe_allow_html=True)

    # ================= Pareto das Não Conformidades =================
    df_nc = []
    if not df_checks_filtrado.empty:
        for _, row in df_checks_filtrado.iterrows():
            if row["status"] == "Não Conforme":
                df_nc.append({"item": row["item"], "numero_serie": row["numero_serie"]})

    df_nc = pd.DataFrame(df_nc)
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
        "Apontamento",
        "Inspeção de Qualidade",
        "Reinspeção",
        "Histórico de Produção",
        "Histórico de Inspeção",
        "Dashboard de Qualidade"
    ])

    if menu == "Dashboard Produção":
        painel_dashboard()

    elif menu == "Apontamento":
        pagina_apontamento()

    elif menu == "Inspeção de Qualidade":
        # ======================== FILTRO DE CÓDIGOS DO DIA ========================
        df_apont = carregar_apontamentos()
        hoje = datetime.datetime.now(TZ).date()
        
        if not df_apont.empty:
            start_of_day = TZ.localize(datetime.datetime.combine(hoje, datetime.time.min))
            end_of_day = TZ.localize(datetime.datetime.combine(hoje, datetime.time.max))
            df_hoje = df_apont[
                (df_apont["data_hora"] >= start_of_day) & 
                (df_apont["data_hora"] <= end_of_day)
            ]
            codigos_hoje = df_hoje["numero_serie"].unique()
        else:
            codigos_hoje = []

        df_checks = carregar_checklists()
        codigos_com_checklist = df_checks["numero_serie"].unique() if not df_checks.empty else []

        codigos_disponiveis = [c for c in codigos_hoje if c not in codigos_com_checklist]

        if codigos_disponiveis:
            numero_serie = st.selectbox(
                "Selecione o Nº de Série para Inspeção",
                codigos_disponiveis,
                index=0
            )
            usuario = st.session_state['usuario']
            checklist_qualidade(numero_serie, usuario)
        else:
            st.info("Nenhum código disponível para inspeção hoje.")

    elif menu == "Reinspeção":
        usuario = st.session_state['usuario']
        df_checks = carregar_checklists()

        if df_checks.empty:
            st.info("Nenhum checklist registrado ainda.")
        else:
            # Filtrar produtos reprovados e que ainda não passaram por reinspeção
            df_reprovados = df_checks[
                (df_checks["produto_reprovado"] == "Sim") &
                (df_checks["reinspecao"] != "Sim")
            ]

            numeros_serie_reinspecao = df_reprovados["numero_serie"].unique() if not df_reprovados.empty else []

            if len(numeros_serie_reinspecao) == 0:
                st.info("Nenhum checklist reprovado pendente para reinspeção.")
            else:
                numero_serie = st.selectbox(
                    "Selecione o Nº de Série para Reinspeção",
                    numeros_serie_reinspecao,
                    index=0
                )
                checklist_reinspecao(numero_serie, usuario)

    elif menu == "Histórico de Produção":
        mostrar_historico_producao()

    elif menu == "Histórico de Inspeção":
        mostrar_historico_qualidade()

    elif menu == "Dashboard de Qualidade":
        dashboard_qualidade()

    # Rodapé sempre no final
    st.markdown(
        "<p style='text-align:center;color:gray;font-size:12px;margin-top:30px;'>Created by Engenharia de Produção</p>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    app()




