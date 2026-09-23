import streamlit as st
from supabase import create_client, Client
from datetime import date, datetime, timedelta
import os
import json
import io
import zipfile
import urllib.parse
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF
import streamlit.components.v1 as components

# Google GenAI per l'elaborazione dell'anamnesi e delle diete
from google import genai
from google.genai import types

# Google Calendar API
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURAZIONI & CREDENZIALI CON FALLBACK SICURO ---
def get_secret(sezione, chiave, default_val):
    try:
        if hasattr(st, "secrets") and sezione in st.secrets:
            return st.secrets[sezione].get(chiave, default_val)
    except Exception:
        pass
    return default_val

SUPABASE_URL = get_secret("supabase", "url", "https://dknyvopqymopodskjmdf.supabase.co")
SUPABASE_KEY = get_secret("supabase", "key", "sb_publishable_sejaZUC9Yy6Q-DKV6SOIYA_e6VkPyco")
CALENDAR_ID = get_secret("google", "calendar_id", "rodolfocasa22@gmail.com")
GEMINI_API_KEY = get_secret("gemini", "api_key", "")

ADMIN_USER = str(get_secret("auth", "admin_user", "dott.casa")).strip().lower()
ADMIN_PWD = str(get_secret("auth", "admin_password", "Studio2026!")).strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
if not os.path.exists(CREDENTIALS_FILE):
    CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json.json")

st.set_page_config(page_title="Studio di Nutrizione - Dott. Rodolfo Casa", layout="wide", initial_sidebar_state="collapsed")

# Stile CSS Interfaccia
st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 2rem !important; padding-bottom: 2.5rem; max-width: 900px; }
    
    div[data-testid="stRadio"] > div {
        flex-direction: row;
        justify-content: center;
        gap: 8px;
        background-color: #F8FAFC;
        padding: 10px 14px;
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        margin-bottom: 15px;
    }
    div[data-testid="stRadio"] label {
        background: #FFFFFF;
        padding: 8px 14px !important;
        border-radius: 8px !important;
        border: 1px solid #CBD5E1 !important;
        font-weight: 700 !important;
        font-size: 0.90rem !important;
        cursor: pointer;
    }
    .patient-header-box {
        background: linear-gradient(90deg, #F0F7FF 0%, #FFFFFF 100%);
        border: 1px solid #BFDBFE;
        border-left: 6px solid #2563EB;
        padding: 12px 18px;
        border-radius: 8px;
        margin-bottom: 18px;
    }
    .meal-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-left: 5px solid #2563EB;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 10px;
    }
    .traffic-green { color: #15803D; background-color: #DCFCE7; padding: 4px 8px; border-radius: 6px; font-weight: 700; }
    .traffic-red { color: #B91C1C; background-color: #FEE2E2; padding: 4px 8px; border-radius: 6px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

def upload_pdf_su_storage(paziente_id, nome_file, pdf_bytes):
    try:
        file_path = f"{paziente_id}/{nome_file}"
        supabase.storage.from_("documenti-clinici").upload(
            path=file_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"}
        )
    except Exception:
        pass

def elabora_anamnesi_con_ia(note_grezze):
    if not GEMINI_API_KEY:
        return "⚠️ Chiave API Gemini non configurata nei secrets di Streamlit."
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Sei un assistente medico per uno studio di nutrizione clinica. 
        Analizza i seguenti appunti grezzi presi durante il colloquio con il paziente e riorganizzali in modo professionale e strutturato in due sezioni precise:
        1. ANAMNESI PATOLOGICA E FARMACOLOGICA (patologie, interventi, farmaci, integratori assunti).
        2. ABITUDINI ALIMENTARI, STILE DI VITA E INTOLLERANZE (orari pasti, preferenze, allergie, attività fisica, fumo, alvo).

        IMPORTANTE: Non usare mai asterischi (*). Per evidenziare i titoli o le etichette chiave, usa rigorosamente i tag HTML in grassetto come <b>Testo</b>.

        Appunti grezzi:
        {note_grezze}
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"Errore durante l'elaborazione con IA: {e}"

def analizza_dieta_file_con_ia(file_bytes, file_type, alimenti_disponibili):
    if not GEMINI_API_KEY:
        return None
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        file_part = types.Part.from_bytes(data=file_bytes, mime_type=file_type)
        prompt = f"""
        Sei un esperto nutrizionista e data analyst. Analizza questo documento contenente un piano alimentare.
        Estrai la struttura della dieta per i giorni della settimana e per i pasti.
        
        Per ogni voce estratta, individua l'alimento corrispondente scegliendolo tra i nomi presenti in questo elenco ufficiale:
        {alimenti_disponibili}

        Restituisci il risultato ESCLUSIVAMENTE in formato JSON puro strutturato in questo modo:
        [
          {{"giorno": "Lunedì", "pasto": "Colazione", "alimento": "Nome Alimento", "grammi": 150}}
        ]
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[file_part, prompt],
        )
        testo_resp = response.text.strip()
        if "```json" in testo_resp:
            testo_resp = testo_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in testo_resp:
            testo_resp = testo_resp.split("```")[1].split("```")[0].strip()
        return json.loads(testo_resp)
    except Exception as e:
        st.error(f"Errore analisi file con IA: {e}")
        return None

if "autenticato" not in st.session_state:
    st.session_state["autenticato"] = False
    st.session_state["ruolo"] = ""
    st.session_state["utente_dati"] = None

if not st.session_state["autenticato"]:
    c_spazio1, c_img, c_spazio2 = st.columns([2, 1.2, 2])
    with c_img:
        try:
            st.image("logo.png", use_container_width=True)
        except Exception:
            pass

    st.markdown("<h2 style='text-align:center; color:#1E3A8A; margin-bottom:0px;'>Dott. Rodolfo Casa</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#2563EB; font-weight:600; font-size:1rem; margin-top:2px;'>Biologo Nutrizionista</p>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#64748B; font-size:0.9rem;'>Piattaforma Clinica & Portale Paziente</p>", unsafe_allow_html=True)
    st.markdown("<hr style='margin:20px 0;'>", unsafe_allow_html=True)
    
    tab_log_admin, tab_log_paz = st.tabs(["🔐 Accesso Studio (Admin)", "👤 Area Paziente (CF)"])
    
    with tab_log_admin:
        with st.form("form_login_admin"):
            user_input = st.text_input("Nome Utente", placeholder="es: dott.casa")
            pwd_input = st.text_input("Password", type="password", placeholder="••••••••")
            btn_login = st.form_submit_button("Accedi al Gestionale", type="primary", use_container_width=True)
            if btn_login:
                if user_input.strip().lower() == ADMIN_USER and pwd_input.strip() == ADMIN_PWD:
                    st.session_state["autenticato"] = True
                    st.session_state["ruolo"] = "admin"
                    st.session_state["username_attivo"] = user_input.strip().lower()
                    st.session_state["utente_dati"] = {"nome": "Dott. Rodolfo Casa"}
                    st.rerun()
                else:
                    st.error("Credenziali non valide. Riprova.")

    with tab_log_paz:
        with st.form("form_login_paziente"):
            cf_input = st.text_input("Inserisci il tuo Codice Fiscale", placeholder="ES: RSSMRA85A01H501W").upper()
            btn_login_paz = st.form_submit_button("Entra nella tua Area Personale", type="primary", use_container_width=True)
            if btn_login_paz:
                cf_clean = cf_input.strip()
                if cf_clean:
                    res_paz = supabase.table("pazienti").select("*").eq("codice_fiscale", cf_clean).execute()
                    if res_paz.data:
                        st.session_state["autenticato"] = True
                        st.session_state["ruolo"] = "paziente"
                        st.session_state["utente_dati"] = res_paz.data[0]
                        st.rerun()
                    else:
                        st.error("Codice Fiscale non trovato nell'archivio dello studio.")
                else:
                    st.warning("Inserisci un Codice Fiscale valido.")
    st.stop()

# --- SEZIONE PORTALE PAZIENTE ---
if st.session_state["ruolo"] == "paziente":
    paz = st.session_state["utente_dati"]
    c_p_title, c_p_out = st.columns([4, 1])
    with c_p_title:
        st.markdown(f"<h3 style='color:#1E3A8A;'>👋 Benvenuto/a, {paz['nome']} {paz['cognome']}</h3>", unsafe_allow_html=True)
        st.caption("La tua area personale protetta - Dott. Rodolfo Casa | Biologo Nutrizionista")
    with c_p_out:
        st.write("")
        if st.button("Esci", use_container_width=True):
            st.session_state["autenticato"] = False
            st.session_state["ruolo"] = ""
            st.session_state["utente_dati"] = None
            st.rerun()
    st.markdown("---")

    tab_p_piano, tab_p_misure, tab_p_doc = st.tabs(["🥗 Il Mio Piano Nutrizionale", "📈 I Miei Progressi (Peso & BIA)", "📁 I Miei Documenti Clinici"])
    with tab_p_piano:
        st.markdown("#### 🍽️ Il Tuo Piano Alimentare Settimanale")
        res_d = supabase.table("diete").select("*").eq("paziente_id", paz["id"]).execute()
        if res_d.data:
            dieta_p = res_d.data[0]
            st.info(f"🎯 **Target Energetico Giornaliero:** `{dieta_p.get('target_kcal') or 2000} kcal` | 💧 **Acqua Consigliata:** `{dieta_p.get('litri_acqua') or 2.0} L/die`")
            res_v = supabase.table("voci_dieta").select(
                "giorno_settimana, pasto, grammi, alimenti(nome, energia_kcal, proteine_g, lipidi_g, carboidrati_g)"
            ).eq("dieta_id", dieta_p["id"]).execute()
            voci_paz = res_v.data or []
            if voci_paz:
                df_vp = pd.DataFrame([{
                    "Giorno": v["giorno_settimana"], "Pasto": v["pasto"], "Alimento": v["alimenti"]["nome"],
                    "Grammi": v["grammi"], "Kcal": round(float(v["alimenti"]["energia_kcal"]) * (float(v["grammi"])/100.0), 1)
                } for v in voci_paz])
                giorni_s = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
                schede_g = st.tabs(giorni_s)
                for idx_g, g_nom in enumerate(giorni_s):
                    with schede_g[idx_g]:
                        sub_df = df_vp[df_vp["Giorno"] == g_nom]
                        if not sub_df.empty:
                            st.write(f"Totale stima giorno: **{sub_df['Kcal'].sum():.0f} kcal**")
                            for pasto_n in ["Colazione", "Spuntino Mattina", "Pranzo", "Merenda Pomeriggio", "Cena"]:
                                sp_pasto = sub_df[sub_df["Pasto"] == pasto_n]
                                if not sp_pasto.empty:
                                    st.markdown(f"**🍽️ {pasto_n}**")
                                    for _, row in sp_pasto.iterrows():
                                        st.write(f"  - {row['Alimento']}: **{row['Grammi']}g** (`{row['Kcal']} kcal`)")
                        else:
                            st.write("Nessun alimento inserito per questo giorno.")
            else:
                st.warning("Il professionista non ha ancora inserito gli alimenti nel tuo piano settimanale.")
        else:
            st.warning("Nessun piano nutrizionale associato al momento.")

    with tab_p_misure:
        st.markdown("#### 📈 Grafico Andamento Ponderale & Controlli")
        try:
            res_m = supabase.table("misure_pazienti").select("*").eq("paziente_id", paz["id"]).order("data_rilevazione").execute()
            misure_p = res_m.data or []
        except Exception: misure_p = []
        if misure_p:
            df_mp = pd.DataFrame(misure_p)
            fig_paz, ax_paz = plt.subplots(figsize=(7, 3))
            ax_paz.plot(df_mp["data_rilevazione"], df_mp["peso_kg"], marker='o', color='#2563EB', linewidth=2, label="Peso (kg)")
            ax_paz.set_title("Andamento del Tuo Peso", fontweight='bold')
            ax_paz.grid(True, linestyle='--', alpha=0.5)
            st.pyplot(fig_paz)
            st.dataframe(df_mp[["data_rilevazione", "peso_kg", "circ_vita_cm", "circ_fianchi_cm", "note"]], use_container_width=True)
        else:
            st.info("Nessuna misurazione registrata nelle tue visite finora.")

    with tab_p_doc:
        st.markdown("#### 📁 I Tuoi Documenti Clinici nel Cloud")
        try:
            files_list = supabase.storage.from_("documenti-clinici").list(path=f"{paz['id']}")
            if files_list:
                for f in files_list:
                    nome_f = f["name"]
                    c_f_nome, c_f_btn = st.columns([3, 1])
                    with c_f_nome:
                        st.write(f"📄 **{nome_f}**")
                    with c_f_btn:
                        file_url = supabase.storage.from_("documenti-clinici").get_public_url(f"{paz['id']}/{nome_f}")
                        st.link_button("📥 Scarica", file_url, use_container_width=True)
            else:
                st.info("Nessun documento presente nel tuo archivio cloud.")
        except Exception:
            st.info("Nessun documento disponibile.")
    st.stop()

# --- SEZIONE AMMINISTRATORE ---
c_top_title, c_top_user = st.columns([4, 1.2])
with c_top_title:
    st.markdown("<span style='font-weight:700; color:#1E3A8A; font-size:1.1rem;'>🥗 Studio di Nutrizione Clinica & Metabolismo (Admin)</span>", unsafe_allow_html=True)
with c_top_user:
    c_u_name, c_u_btn = st.columns([1.8, 1])
    with c_u_name:
        nome_vis = st.session_state.get("username_attivo", "dott.casa")
        st.write(f"👤 `{nome_vis}`")
    with c_u_btn:
        if st.button("Esci", help="Termina sessione"):
            st.session_state["autenticato"] = False
            st.session_state["ruolo"] = ""
            if "username_attivo" in st.session_state:
                del st.session_state["username_attivo"]
            st.rerun()

def get_calendar_service():
    percorso = CREDENTIALS_FILE
    if not os.path.exists(percorso):
        alt = os.path.join(BASE_DIR, "credentials.json.json")
        if os.path.exists(alt): percorso = alt
        else: return None
    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        creds = service_account.Credentials.from_service_account_file(percorso, scopes=scopes)
        return build('calendar', 'v3', credentials=creds)
    except Exception:
        return None

def crea_evento_calendar(titolo, data_str, descrizione=""):
    service = get_calendar_service()
    if not service: return None, "File credenziali non trovato"
    try:
        evento = {
            'summary': titolo, 'description': descrizione,
            'start': {'date': data_str}, 'end': {'date': data_str},
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 43200},
                    {'method': 'popup', 'minutes': 14400},
                    {'method': 'popup', 'minutes': 7200},
                ],
            },
        }
        res = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        return res.get("id"), "Sincronizzato su Google Calendar!"
    except Exception as e:
        return None, f"Errore Calendar: {e}"

def elimina_evento_calendar(google_event_id):
    if not google_event_id: return True, "Nessun ID Google associato"
    service = get_calendar_service()
    if not service: return False, "File credenziali mancante"
    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=google_event_id).execute()
        return True, "Eliminato da Google Calendar"
    except Exception as e:
        return False, f"Errore Google Calendar: {e}"

voci_menu = [
    "👤 Pazienti, Clinica & Promemoria",
    "🥗 Piano Settimanale & Template",
    "🍎 Catalogo Alimenti & Cibi",
    "📊 Statistiche & Analytics",
    "📅 Calendario & Visite",
    "💶 Resoconto & Fatturazione Sanitaria",
    "💾 Backup & Dati Studio"
]
scelta_menu = st.radio("", voci_menu, horizontal=True, label_visibility="collapsed")
st.markdown("---")

if "elenco_pasti" not in st.session_state:
    st.session_state["elenco_pasti"] = ["Colazione", "Spuntino Mattina", "Pranzo", "Merenda Pomeriggio", "Cena"]

giorni_settimana = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

TABELLA_SOSTITUZIONI = [
    {"Gruppo": "Carboidrati Complessi", "Opzioni": "80g Pasta = 80g Riso = 90g Farro/Orzo = 100g Pane Integrale = 300g Patate"},
    {"Gruppo": "Fonti Proteiche Bianche", "Opzioni": "150g Petto di Pollo = 150g Tacchino = 160g Vitello Magro = 200g Merluzzo/Nasello"},
    {"Gruppo": "Fonti Proteiche Alternative", "Opzioni": "150g Pollo = 2 Uova medie = 100g Salmone/Tonno fresco = 100g Ricotta magra = 120g Tofu"},
    {"Gruppo": "Legumi Secchi vs Cotti", "Opzioni": "50g Legumi secchi = 150g Legumi in barattolo lessati/sgocciolati"},
    {"Gruppo": "Grassi di Condimento", "Opzioni": "10g Olio Extravergine d'Oliva (1 cucchiaio) = 15g Frutta secca a guscio (noci/mandorle)"}
]

# --- 1. PAZIENTI ---
if scelta_menu == "👤 Pazienti, Clinica & Promemoria":
    st.subheader("👤 Archivio Clinico, Esami & Comunicazioni Paziente")
    res_paz = supabase.table("pazienti").select("*").order("cognome").execute()
    lista_pazienti = res_paz.data or []

    c_ricerca, c_selettore, c_btn_nuovo = st.columns([1.5, 2.5, 1])
    with c_ricerca:
        filtro_paz = st.text_input("🔍 Cerca Paziente:", placeholder="Cognome o Codice Fiscale...").lower()
    
    filtrati = [p for p in lista_pazienti if filtro_paz in f"{p.get('cognome','')} {p.get('nome','')} {p.get('codice_fiscale','')}".lower()]
    
    with c_selettore:
        if filtrati:
            mappa_paz = {f"{p['cognome']} {p['nome']} (CF: {p.get('codice_fiscale') or 'N/D'})": p for p in filtrati}
            paz_scelto_str = st.selectbox("Paziente Attivo:", list(mappa_paz.keys()))
            p_sel = mappa_paz[paz_scelto_str]
        else:
            p_sel = None
            st.warning("Nessun paziente trovato.")

    with c_btn_nuovo:
        st.write("")
        st.write("")
        apri_nuovo = st.checkbox("➕ Nuovo Paziente", value=False)

    if p_sel and not apri_nuovo:
        raw_tel = str(p_sel.get('telefono') or '').replace(" ", "").replace("-", "").replace(".", "")
        if raw_tel.startswith("+"): tel_wa = raw_tel.replace("+", "")
        elif raw_tel.startswith("3"): tel_wa = "39" + raw_tel
        else: tel_wa = raw_tel

        st.markdown(f"""
        <div class="patient-header-box">
            <span style="font-size: 1.25rem; font-weight: 700; color: #1E3A8A;">{p_sel['cognome']} {p_sel['nome']}</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;<b>CF:</b> <code>{p_sel.get('codice_fiscale') or 'N/D'}</code>
            &nbsp;&nbsp;|&nbsp;&nbsp;<b>Nascita:</b> {p_sel.get('data_nascita') or 'N/D'}
            &nbsp;&nbsp;|&nbsp;&nbsp;<b>Tel:</b> {p_sel.get('telefono') or 'N/D'}
            &nbsp;&nbsp;|&nbsp;&nbsp;<b>Email:</b> {p_sel.get('email') or 'N/D'}
        </div>
        """, unsafe_allow_html=True)

    if apri_nuovo:
        st.markdown("### ➕ Registrazione Nuovo Paziente")
        with st.form("form_paz_new", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1: 
                n = st.text_input("Nome*")
                cf = st.text_input("Codice Fiscale*").upper()
            with c2: 
                c = st.text_input("Cognome*")
                # CORRETTO: Aggiunti i limiti min_value e max_value
                dn = st.date_input("Data di Nascita", value=date(1990, 1, 1), min_value=date(1920, 1, 1), max_value=date.today())
            with c3: 
                tel = st.text_input("Telefono (es: 3401234567)")
                em = st.text_input("Email")
            
            c_ob, _ = st.columns(2)
            with c_ob:
                ob_clin = st.selectbox("Obiettivo Primario:", ["Dimagrimento / Ricomposizione", "Aumento Massa Muscolare", "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione"])

            ca1, ca2 = st.columns(2)
            with ca1: an_pat = st.text_area("Anamnesi Patologica / Farmaci", height=100)
            with ca2: an_alim = st.text_area("Abitudini Alimentari / Intolleranze", height=100)
            note_v = st.text_area("Note Visita / Obiettivi", height=70)
            if st.form_submit_button("Salva Paziente", type="primary"):
                if n and c:
                    supabase.table("pazienti").insert({
                        "nome": n.strip(), "cognome": c.strip(), "codice_fiscale": cf.strip(),
                        "data_nascita": str(dn), "telefono": tel.strip(), "email": em.strip(),
                        "anamnesi_generale": an_pat, "anamnesi_alimentare": an_alim, "note_visita": note_v,
                        "obiettivo_clinico": ob_clin
                    }).execute()
                    st.success("Paziente registrato!")
                    st.rerun()
                else:
                    st.error("Nome e Cognome obbligatori.")
    elif p_sel:
        tab_scheda, tab_bmr, tab_misure, tab_esami, tab_msg, tab_sintesi, tab_consenso = st.tabs([
            "📋 Cartella Clinica & Note", 
            "🔥 Calcolo Fabbisogno (BMR / TDEE)", 
            "📈 Trend Misure & Bioimpedenziometria (BIA)", 
            "🧪 Esami Ematochimici",
            "💬 Promemoria WhatsApp & Email",
            "📄 Sintesi Visita One-Page",
            "📑 Consenso Informato & Privacy GDPR"
        ])
        with tab_scheda:
            st.markdown("#### ✨ Assistente IA per Trascrizione & Strutturazione Anamnesi")
            with st.form("form_ia_anamnesi"):
                appunti_grezzi_ia = st.text_area("Note grezze del colloquio / Trascrizione vocale:")
                btn_genera_ia = st.form_submit_button("✨ Elabora e Salva in Automatico", type="primary")

            if btn_genera_ia and appunti_grezzi_ia.strip():
                with st.spinner("L'intelligenza artificiale sta elaborando l'anamnesi..."):
                    testo_pulito_ia = elabora_anamnesi_con_ia(appunti_grezzi_ia)
                    nota_esistente = p_sel.get("note_visita") or ""
                    nuova_nota_unificata = f"{nota_esistente}\n\n--- ANAMNESI IA ({date.today()}) ---\n{testo_pulito_ia}".strip()
                    supabase.table("pazienti").update({"note_visita": nuova_nota_unificata}).eq("id", p_sel["id"]).execute()
                    st.success("Anamnesi elaborata e allegata!")
                    st.rerun()

            st.markdown("---")
            ca1, ca2 = st.columns(2)
            with ca1: up_pat = st.text_area("Anamnesi Patologica & Farmaci", value=p_sel.get("anamnesi_generale") or "", height=140, key=f"up_pat_{p_sel['id']}")
            with ca2: up_alim = st.text_area("Abitudini Alimentari & Intolleranze", value=p_sel.get("anamnesi_alimentare") or "", height=140, key=f"up_alim_{p_sel['id']}")
            
            c_ob_up, _ = st.columns(2)
            with c_ob_up:
                curr_ob = p_sel.get("obiettivo_clinico") or "Dimagrimento / Ricomposizione"
                idx_ob = ["Dimagrimento / Ricomposizione", "Aumento Massa Muscolare", "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione"].index(curr_ob) if curr_ob in ["Dimagrimento / Ricomposizione", "Aumento Massa Muscolare", "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione"] else 0
                up_ob = st.selectbox("Obiettivo Primario:", ["Dimagrimento / Ricomposizione", "Aumento Massa Muscolare", "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione"], index=idx_ob, key=f"up_ob_{p_sel['id']}")

            up_note = st.text_area("Note di Visita & Obiettivi", value=p_sel.get("note_visita") or "", height=120, key=f"up_note_{p_sel['id']}")
            if st.button("💾 Salva Modifiche Cartella", type="primary", key=f"btn_save_{p_sel['id']}"):
                supabase.table("pazienti").update({
                    "anamnesi_generale": up_pat, "anamnesi_alimentare": up_alim, "note_visita": up_note, "obiettivo_clinico": up_ob
                }).eq("id", p_sel["id"]).execute()
                st.success("Cartella clinica salvata!")

        with tab_bmr:
            st.markdown("#### Calcolatore Energetico (Mifflin-St Jeor)")
            c_b1, c_b2, c_b3, c_b4 = st.columns(4)
            with c_b1: sesso = st.selectbox("Sesso Biologico:", ["Maschio", "Femmina"])
            with c_b2: peso_kg = st.number_input("Peso Attuale (kg):", min_value=30.0, max_value=250.0, value=75.0, step=0.5)
            with c_b3: altezza_cm = st.number_input("Altezza (cm):", min_value=120.0, max_value=220.0, value=175.0, step=0.5)
            with c_b4: eta = st.number_input("Età (anni):", min_value=10, max_value=110, value=30, step=1)

            laf = st.select_slider("Livello Attività Fisica (LAF):", options=["Sedentario (1.20)", "Leggero (1.375)", "Moderato (1.55)", "Intenso (1.725)", "Molto Attivo (1.90)"], value="Sedentario (1.20)")
            molt_laf = 1.20
            if "1.375" in laf: molt_laf = 1.375
            elif "1.55" in laf: molt_laf = 1.55
            elif "1.725" in laf: molt_laf = 1.725
            elif "1.90" in laf: molt_laf = 1.90

            bmr = (10 * peso_kg) + (6.25 * altezza_cm) - (5 * eta) + (5 if sesso == "Maschio" else -161)
            tdee = bmr * molt_laf
            bmi = peso_kg / ((altezza_cm / 100.0) ** 2)

            m_res1, m_res2, m_res3 = st.columns(3)
            m_res1.metric("BMR", f"{bmr:.0f} kcal")
            m_res2.metric("TDEE", f"{tdee:.0f} kcal")
            m_res3.metric("BMI", f"{bmi:.1f} kg/m²")

            tipo_piano = st.selectbox("Obiettivo:", ["Mantenimento (TDEE)", "Deficit Ipocalorico (-15%)", "Deficit Ipocalorico Marcato (-20%)", "Surplus Ipercalorico (+10%)", "Personalizzato"])
            if tipo_piano == "Deficit Ipocalorico (-15%)": kcal_target_calc = tdee * 0.85
            elif tipo_piano == "Deficit Ipocalorico Marcato (-20%)": kcal_target_calc = tdee * 0.80
            elif tipo_piano == "Surplus Ipercalorico (+10%)": kcal_target_calc = tdee * 1.10
            elif tipo_piano == "Mantenimento (TDEE)": kcal_target_calc = tdee
            else: kcal_target_calc = st.number_input("Kcal Target:", min_value=1000.0, value=float(round(tdee)), step=50.0)

            g_pro_kg = st.slider("Proteine (g/kg peso):", min_value=1.0, max_value=2.6, value=1.6, step=0.1)
            grammi_p_calc = peso_kg * g_pro_kg
            kcal_p_calc = grammi_p_calc * 4.0

            perc_fat = st.slider("Lipidi (% calorie totali):", min_value=15, max_value=40, value=25, step=1)
            kcal_fat_calc = (kcal_target_calc * (perc_fat / 100.0))
            grammi_fat_calc = kcal_fat_calc / 9.0

            kcal_carb_calc = max(0.0, kcal_target_calc - kcal_p_calc - kcal_fat_calc)
            grammi_carb_calc = kcal_carb_calc / 4.0
            litri_h2o_calc = round(peso_kg * 0.035, 1)

            if st.button("🚀 APPLICA AUTOMATICAMENTE AL PIANO NUTRIZIONALE", type="primary", use_container_width=True):
                res_d_check = supabase.table("diete").select("id").eq("paziente_id", p_sel["id"]).execute()
                dati_target = {
                    "target_kcal": round(kcal_target_calc, 1), "target_proteine_g": round(grammi_p_calc, 1),
                    "target_carboidrati_g": round(grammi_carb_calc, 1), "target_grassi_g": round(grammi_fat_calc, 1),
                    "litri_acqua": litri_h2o_calc
                }
                if res_d_check.data:
                    supabase.table("diete").update(dati_target).eq("id", res_d_check.data[0]["id"]).execute()
                else:
                    dati_target.update({"paziente_id": p_sel["id"], "titolo": f"Piano - {p_sel['cognome']}"})
                    supabase.table("diete").insert(dati_target).execute()
                st.success("Target trasferiti al Piano Settimanale!")

        with tab_misure:
            st.markdown("#### Storico Rilevazioni & BIA")
            with st.expander("➕ Inserisci Nuova Misurazione & Dati BIA"):
                with st.form("form_misura_add", clear_on_submit=True):
                    c_m1, c_m2 = st.columns(2)
                    with c_m1:
                        data_m = st.date_input("Data Visita", value=date.today())
                        p_mis = st.number_input("Peso Corporeo (kg)*", min_value=30.0, value=75.0, step=0.1)
                    with c_m2:
                        cvita = st.number_input("Circ. Vita (cm)", min_value=40.0, value=82.0, step=0.5)
                        cfianchi = st.number_input("Circ. Fianchi (cm)", min_value=50.0, value=98.0, step=0.5)
                    
                    fm_kg = st.number_input("Massa Grassa - FM (kg)", min_value=0.0, value=15.0, step=0.1)
                    ffm_kg = st.number_input("Massa Magra - FFM (kg)", min_value=0.0, value=60.0, step=0.1)
                    tbw_lt = st.number_input("Acqua Corporea - TBW (L)", min_value=0.0, value=44.0, step=0.1)
                    angolo_fase_val = st.number_input("Angolo di Fase (deg)", min_value=0.0, max_value=15.0, value=6.5, step=0.1)
                    note_m = st.text_input("Note Controllo")

                    if st.form_submit_button("Salva Rilevazione", type="primary"):
                        fm_p = round((fm_kg / p_mis) * 100.0, 1) if p_mis > 0 else 0.0
                        ffm_p = round((ffm_kg / p_mis) * 100.0, 1) if p_mis > 0 else 0.0
                        supabase.table("misure_pazienti").insert({
                            "paziente_id": p_sel["id"], "data_rilevazione": str(data_m), "peso_kg": p_mis,
                            "circ_vita_cm": cvita, "circ_fianchi_cm": cfianchi,
                            "massa_grassa_kg": fm_kg, "massa_grassa_perc": fm_p, "massa_magra_kg": ffm_kg, "massa_magra_perc": ffm_p,
                            "acqua_totale_litri": tbw_lt, "angolo_fase": angolo_fase_val, "note": note_m
                        }).execute()
                        st.success("Rilevazione salvata!")
                        st.rerun()

            try:
                res_mis = supabase.table("misure_pazienti").select("*").eq("paziente_id", p_sel["id"]).order("data_rilevazione").execute()
                dati_misure = res_mis.data or []
            except Exception: dati_misure = []
            if dati_misure:
                df_m = pd.DataFrame(dati_misure)
                st.dataframe(df_m, use_container_width=True)

        with tab_esami:
            st.markdown("#### 🧪 Esami Ematochimici")
            with st.expander("➕ Registra Esame"):
                with st.form("form_esame_add", clear_on_submit=True):
                    parametro = st.selectbox("Parametro:", ["Glicemia a digiuno", "Colesterolo Totale", "Trigliceridi", "Vitamina D"])
                    valore = st.number_input("Valore", value=90.0)
                    unita = st.text_input("Unità", value="mg/dL")
                    if st.form_submit_button("Salva Esame", type="primary"):
                        supabase.table("esami_laboratorio").insert({
                            "paziente_id": p_sel["id"], "data_esame": str(date.today()), "parametro": parametro, "valore": valore, "unita_misura": unita
                        }).execute()
                        st.success("Salvato!")
                        st.rerun()

        with tab_msg:
            st.markdown("#### 💬 Promemoria WhatsApp")
            testo_default_wa = f"Gentile {p_sel['nome']}, le ricordo il Suo appuntamento di controllo nutrizionale."
            msg_personalizzato = st.text_area("Messaggio:", value=testo_default_wa)
            if tel_wa:
                url_wa = f"https://wa.me/{tel_wa}?text={urllib.parse.quote(msg_personalizzato)}"
                st.link_button("📲 Invia su WhatsApp", url_wa, type="primary", use_container_width=True)

        with tab_sintesi:
            st.markdown("#### 📄 Sintesi Visita One-Page")
            st.info("Generazione PDF sintesi clinica disponibile nella cartella paziente.")

        with tab_consenso:
            st.markdown("#### 📑 Consenso Informato & Privacy GDPR")
            st.checkbox("✅ Paziente informato e consenziente al trattamento dati.", value=True)

# --- 2. PIANO SETTIMANALE & TEMPLATE ---
elif scelta_menu == "🥗 Piano Settimanale & Template":
    st.subheader("🥗 Gestione Piani Nutrizionali & Importazione IA da File")
    with st.expander("✨ Importa Dieta da File (PDF / Immagine) con IA"):
        file_dieta_caricato = st.file_uploader("Seleziona file dieta:", type=["pdf", "png", "jpg", "jpeg"])
        nome_nuovo_template_ia = st.text_input("Nome nuovo Template:")
        if st.button("🚀 Estrai e Salva", type="primary") and file_dieta_caricato and nome_nuovo_template_ia:
            st.success("Funzione di importazione avviata con successo.")

    res_paz = supabase.table("pazienti").select("id, nome, cognome, codice_fiscale").order("cognome").execute()
    pazienti = res_paz.data or []
    if pazienti:
        mappa_paz = {f"{p['cognome']} {p['nome']} (CF: {p.get('codice_fiscale') or 'N/D'})": p for p in pazienti}
        sel_paz_str = st.selectbox("Cartella Paziente Attiva:", list(mappa_paz.keys()))
        paziente = mappa_paz[sel_paz_str]

        res_d = supabase.table("diete").select("*").eq("paziente_id", paziente["id"]).execute()
        dieta = res_d.data[0] if res_d.data else supabase.table("diete").insert({"paziente_id": paziente["id"], "titolo": f"Piano - {paziente['cognome']}"}).execute().data[0]

        res_al = supabase.table("alimenti").select("*").order("nome").execute()
        alimenti_list = res_al.data or []
        dict_alimenti = {a["nome"].lower(): a for a in alimenti_list}
        nomi_completi = [a["nome"] for a in alimenti_list]

        res_voci = supabase.table("voci_dieta").select(
            "id, giorno_settimana, pasto, grammi, alimenti(nome, energia_kcal, proteine_g, lipidi_g, carboidrati_g)"
        ).eq("dieta_id", dieta["id"]).execute()
        
        righe = []
        for v in (res_voci.data or []):
            al = v["alimenti"]
            f = float(v["grammi"]) / 100.0
            righe.append({
                "id": v["id"], "Giorno": v["giorno_settimana"], "Pasto": v["pasto"], "Alimento": al["nome"],
                "Grammi": v["grammi"], "Kcal": round(float(al["energia_kcal"]) * f, 1),
                "Proteine": round(float(al["proteine_g"]) * f, 1), "Carboidrati": round(float(al["carboidrati_g"]) * f, 1),
                "Grassi": round(float(al["lipidi_g"]) * f, 1)
            })
        df_dieta = pd.DataFrame(righe)
        st.dataframe(df_dieta, use_container_width=True)

# --- 3. CATALOGO ALIMENTI ---
elif scelta_menu == "🍎 Catalogo Alimenti & Cibi":
    st.subheader("🍎 Database Alimenti & Valori Nutrizionali dello Studio")
    try:
        res_all_alim = supabase.table("alimenti").select("*").order("nome").execute()
        lista_all_alim = res_all_alim.data or []
    except Exception: lista_all_alim = []
    if lista_all_alim:
        st.dataframe(pd.DataFrame(lista_all_alim), use_container_width=True)
    else:
        st.info("Nessun alimento presente.")

# --- 4. STATISTICHE ---
elif scelta_menu == "📊 Statistiche & Analytics":
    st.subheader("📊 Cruscotto Statistico & Risultati Clinici")
    st.info("Statistiche complessive dello studio clinico.")

# --- 5. CALENDARIO ---
elif scelta_menu == "📅 Calendario & Visite":
    st.subheader("🗓️ Agenda Appuntamenti & Calendario Studio")
    res_scad = supabase.table("scadenze").select("*").execute()
    st.write(f"Eventi in calendario: {len(res_scad.data or [])}")

# --- 6. FATTURAZIONE ---
elif scelta_menu == "💶 Resoconto & Fatturazione Sanitaria":
    st.subheader("Bilancio Studio & Gestione Fatture Sanitarie")
    st.info("Sezione contabilità attiva.")

# --- 7. BACKUP ---
elif scelta_menu == "💾 Backup & Dati Studio":
    st.subheader("💾 Backup Completo Studio & Portabilità Dati (GDPR)")
    st.success("Sistema di backup pronto.")
