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
    """Carrega todos os checklists do Supabase, sem limite de 1000 linhas."""
    data_total = []
    inicio = 0
    passo = 1000

    while True:
        response = supabase.table("checklists").select("*").range(inicio, inicio + passo - 1).execute()
        dados = response.data
        if not dados:
            break
        data_total.extend(dados)
        inicio += passo

    df = pd.DataFrame(data_total)

    if not df.empty and "data_hora" in df.columns:
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
            raise

    st.success(f"✅ Checklist salvo com sucesso para o Nº de Série {serie}")
    return True


def carregar_apontamentos():
    """Carrega todos os apontamentos do Supabase sem limite de 1000 linhas."""
    data_total = []
    inicio = 0
    passo = 1000

    while True:
        response = supabase.table("apontamentos").select("*").range(inicio, inicio + passo - 1).execute()
        dados = response.data
        if not dados:
            break
        data_total.extend(dados)
        inicio += passo

    df = pd.DataFrame(data_total)

    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce", utc=True).dt.tz_convert(TZ)

    return df


def salvar_apontamento(serie, op, tipo_producao=None):
    agora_utc = datetime.datetime.now(datetime.timezone.utc)
    hoje_utc = agora_utc.date()

    inicio_utc = datetime.datetime.combine(hoje_utc, datetime.time.min).replace(tzinfo=datetime.timezone.utc)
    fim_utc = datetime.datetime.combine(hoje_utc, datetime.time.max).replace(tzinfo=datetime.timezone.utc)

    response = supabase.table("apontamentos")\
        .select("*")\
        .eq("numero_serie", serie)\
        .gte("data_hora", inicio_utc.isoformat())\
        .lte("data_hora", fim_utc.isoformat())\
        .execute()

    if response.data:
        return False

    dados = {
        "numero_serie": serie,
        "op": str(op).strip(),
        "data_hora": agora_utc.isoformat()
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
def login():
    if 'logado' not in st.session_state:
        st.session_state['logado'] = False
        st.session_state['usuario'] = None

    if not st.session_state['logado']:
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
            st.experimental_set_query_params()


def status_emoji_para_texto(emoji):
    if emoji == "✅":
        return "Conforme"
    elif emoji == "❌":
        return "Não Conforme"
    else:
        return "N/A"


def checklist_qualidade(numero_serie, usuario):
    import time

    st.markdown(f"## ✔️ Checklist de Qualidade – Nº de Série: {numero_serie}")

    if "checklist_bloqueado" not in st.session_state:
        st.session_state.checklist_bloqueado = False

    if "checklist_cache" not in st.session_state:
        st.session_state.checklist_cache = {}

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga?Gravação do número de série da viga está legível e pintada?",
        "Etiqueta do ABS está conforme? Com número de série compátivel ao da viga? Teste do ABS está aprovado?",
        "Rodagem – tipo correto? Especifique o modelo",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições? Especifique o modelo:",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios? As tampas dos cubos dos ambos os lados são iguais?",
        "Pintura do eixo livre de oxidação,isento de escorrimento na pintura, pontos sem tinta e camada conforme padrão?",
        "Os cordões de solda do eixo estão conformes?"
    ]

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_IMETRO E NÚMERO DE SÉRIE",
        3: "TESTE_ABS",
        4: "RODAGEM_MODELO",
        5: "GRAXEIRAS E ANÉIS ELÁSTICOS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA_FREIO",
        8: "TAMPA_CUBO",
        9: "PINTURA_EIXO",
        10: "SOLDA"
    }

    opcoes_modelos = {
        4: ["Single", "Aço", "Alumínio", "N/A"],
        6: ["Spring", "Cuíca", "N/A"],
        7: ["Automático", "Manual", "N/A"],
        10: ["Conforme", "Respingo", "Falta de cordão", "Porosidade", "Falta de Fusão"]
    }

    resultados = {}
    modelos = {}

    st.write("Clique no botão correspondente a cada item:")
    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_checklist_{numero_serie}", clear_on_submit=False):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 2, 2])

            cols[0].markdown(f"**{i}. {pergunta}**")

            escolha = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"resp_{numero_serie}_{i}",
                horizontal=True,
                index=None,
                label_visibility="collapsed"
            )
            resultados[i] = escolha

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

        submit = st.form_submit_button("💾 Salvar Checklist")

    if submit:
        if st.session_state.checklist_bloqueado:
            st.warning("⏳ Salvamento em andamento... aguarde.")
            return

        st.session_state.checklist_bloqueado = True

        faltando = [i for i, resp in resultados.items() if resp is None]
        modelos_faltando = [
            i for i in opcoes_modelos
            if modelos.get(i) is None or modelos[i] == ""
        ]

        if faltando or modelos_faltando:
            msg = ""
            if faltando:
                msg += f"⚠️ Responda todas as perguntas! Faltam: {[item_keys[i] for i in faltando]}\n"
            if modelos_faltando:
                msg += f"⚠️ Preencha todos os modelos! Faltam: {[item_keys[i] for i in modelos_faltando]}"
            st.error(msg)
            st.session_state.checklist_bloqueado = False
            return

        dados_para_salvar = {}
        for i, resp in resultados.items():
            chave_item = item_keys.get(i, f"Item_{i}")
            dados_para_salvar[chave_item] = {
                "status": status_emoji_para_texto(resp),
                "obs": modelos.get(i)
            }

        try:
            salvar_checklist(numero_serie, dados_para_salvar, usuario)
            st.success(f"✅ Checklist do Nº de Série {numero_serie} salvo com sucesso!")
            st.session_state.checklist_cache[numero_serie] = dados_para_salvar
            time.sleep(0.5)

        except Exception as e:
            st.error(f"❌ Erro ao salvar checklist: {e}")
        finally:
            st.session_state.checklist_bloqueado = False


def checklist_reinspecao(numero_serie, usuario):
    st.markdown(f"## 🔄 Reinspeção – Nº de Série: {numero_serie}")

    df_checks = carregar_checklists()

    df_inspecao = df_checks[
        (df_checks["numero_serie"] == numero_serie) &
        (df_checks["reinspecao"] != "Sim")
    ]

    if df_inspecao.empty:
        st.warning("Nenhum checklist de inspeção encontrado para reinspeção.")
        return False

    hoje = datetime.datetime.now(TZ).date()
    df_inspecao["data_hora"] = pd.to_datetime(df_inspecao["data_hora"])
    df_inspecao_mesmo_dia = df_inspecao[df_inspecao["data_hora"].dt.date == hoje]
    if df_inspecao_mesmo_dia.empty:
        st.warning("Nenhum checklist de inspeção encontrado para hoje.")
        return False

    checklist_original = df_inspecao_mesmo_dia.sort_values("data_hora").iloc[-1]

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga?Gravação do número de série da viga está legível e pintada?",
        "Etiqueta do ABS está conforme? Com número de série compátivel ao da viga? Teste do ABS está aprovado?",
        "Rodagem – tipo correto? Especifique o modelo",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições? Especifique o modelo:",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios? As tampas dos cubos dos ambos os lados são iguais?",
        "Pintura do eixo livre de oxidação,isento de escorrimento na pintura, pontos sem tinta e camada conforme padrão?",
        "Os cordões de solda do eixo estão conformes?"
    ]

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_IMETRO E NÚMERO DE SÉRIE",
        3: "TESTE_ABS",
        4: "RODAGEM_MODELO",
        5: "GRAXEIRAS E ANÉIS ELÁSTICOS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA_FREIO",
        8: "TAMPA_CUBO",
        9: "PINTURA_EIXO",
        10: "SOLDA"
    }

    opcoes_modelos = {
        4: ["Single", "Aço", "Alumínio", "N/A"],
        6: ["Spring", "Cuíca", "N/A"],
        7: ["Automático", "Manual", "N/A"],
        10: ["Conforme", "Respingo", "Falta de cordão", "Porosidade", "Falta de Fusão"]
    }

    resultados = {}
    modelos = {}

    st.write("Clique no botão correspondente a cada item:")
    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_reinspecao_{numero_serie}"):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 2, 2])
            chave = item_keys[i]

            status_antigo = checklist_original.get(chave, {}).get("status") if isinstance(checklist_original.get(chave), dict) else checklist_original.get(chave)
            obs_antigo = checklist_original.get(chave, {}).get("obs") if isinstance(checklist_original.get(chave), dict) else ""

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
                index=(["✅", "❌", "🟡"].index(resp_antiga) if resp_antiga in ["✅", "❌", "🟡"] else 0),
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


# ================================
# Página de Apontamento (OP 11 dígitos + Série 9 dígitos, com foco e OP travada)
# ================================
def pagina_apontamento():
    st.markdown("#  Registrar Apontamento")

    st.markdown("### ⏱️ Produção Hora a Hora")

    df_apont = carregar_apontamentos()
    tipo_producao = st.session_state.get("tipo_producao_apontamento", "Esteira")

    df_filtrado = df_apont[
        (df_apont["tipo_producao"].str.contains(tipo_producao, case=False, na=False)) &
        (df_apont["data_hora"].dt.date == datetime.datetime.now(TZ).date())
    ] if not df_apont.empty else pd.DataFrame()

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

    tipo_producao = st.radio(
        "Tipo de produção:",
        ["Eixo", "Manga", "PNM"],
        horizontal=True,
        key="tipo_producao_apontamento"
    )

    # estados
    if "codigo_barras" not in st.session_state:
        st.session_state["codigo_barras"] = ""
    if "op_barras" not in st.session_state:
        st.session_state["op_barras"] = ""
    if "op_atual" not in st.session_state:
        st.session_state["op_atual"] = ""

    # --- OP (11 dígitos) ---
    def processar_op():
        op = st.session_state["op_barras"].strip()

        if not op.isdigit() or len(op) != 11:
            st.error("⚠️ A OP deve conter exatamente 11 dígitos numéricos.")
            st.session_state["op_barras"] = ""
            return

        st.session_state["op_atual"] = op
        st.session_state["op_barras"] = ""

        # limpa o campo travado antigo, se existir (evita “grudar”)
        st.session_state.pop("op_travada", None)

        # foco na série
        components.html(
            """
            <script>
            setTimeout(function(){
                const inputSerie = window.parent.document.querySelector('input[id^="codigo_barras"]');
                if(inputSerie){ inputSerie.focus(); }
            }, 50);
            </script>
            """,
            height=0
        )

    # Se não tem OP, mostra campo para bipar OP; se tem OP, mostra travada (cinza)
    if not st.session_state.get("op_atual"):
        st.text_input(
            "Leia a OP (11 dígitos):",
            key="op_barras",
            on_change=processar_op,
            placeholder="Bipe a OP"
        )
    else:
        st.text_input(
            "OP (travada):",
            value=st.session_state.get("op_atual", ""),
            disabled=True,
            key="op_travada"
        )

    # --- Série (9 dígitos) ---
    def processar_codigo():
        codigo = st.session_state["codigo_barras"].strip()
        op = (st.session_state.get("op_atual") or "").strip()

        if not op:
            st.error("⚠️ Primeiro bipe a OP (11 dígitos).")
            st.session_state["codigo_barras"] = ""
            return

        if not codigo.isdigit() or len(codigo) != 9:
            st.error("⚠️ O número de série deve conter exatamente 9 dígitos numéricos.")
            st.session_state["codigo_barras"] = ""
            return

        df_apont_local = carregar_apontamentos()
        hoje = datetime.datetime.now(TZ).date()

        if not df_apont_local.empty:
            ja_apontado = df_apont_local[
                (df_apont_local["numero_serie"] == codigo) &
                (df_apont_local["data_hora"].dt.date == hoje)
            ]
            if not ja_apontado.empty:
                st.warning(f"⚠️ O código {codigo} já foi registrado hoje.")
                st.session_state["codigo_barras"] = ""
                return

        sucesso = salvar_apontamento(codigo, op, tipo_producao)
        if sucesso:
            st.success(f"Código {codigo} registrado com sucesso!")
        else:
            st.warning(f"Erro ao registrar o código {codigo}.")

        # limpa série
        st.session_state["codigo_barras"] = ""

        # ✅ AQUI é o ponto: destrava a OP para a próxima
        st.session_state["op_atual"] = ""
        st.session_state.pop("op_travada", None)

        # força o rerun pra tela voltar pro campo de OP imediatamente
        st.rerun()

    st.text_input(
        "Leia o Número de Série (9 dígitos):",
        key="codigo_barras",
        on_change=processar_codigo,
        placeholder="Aproxime o leitor"
    )

    # Foco automático simples (SEM observer infinito)
    foco = "op_barras" if not st.session_state.get("op_atual") else "codigo_barras"
    components.html(
        f"""
        <script>
        setTimeout(function(){{
            const el = window.parent.document.querySelector('input[id^="{foco}"]');
            if(el) el.focus();
        }}, 60);
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
            ultimos[["op", "numero_serie", "data_hora_fmt"]].rename(columns={"data_hora_fmt": "Hora"}),
            use_container_width=True
        )
    else:
        st.info("Nenhum apontamento encontrado.")



# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    app()

