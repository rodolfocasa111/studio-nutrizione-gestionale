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
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import tempfile
import google.generativeai as genai

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

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

ADMIN_USER = str(get_secret("auth", "admin_user", "dott.casa")).strip().lower()
ADMIN_PWD = str(get_secret("auth", "admin_password", "Studio2026!")).strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
if not os.path.exists(CREDENTIALS_FILE):
    CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json.json")

st.set_page_config(page_title="Studio Nutrizionale", layout="wide", initial_sidebar_state="collapsed")

# Stile CSS Interfaccia
st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 2.2rem !important; padding-bottom: 2.5rem; }
    
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
    .login-box {
        max-width: 420px;
        margin: 50px auto;
        padding: 30px;
        background: #FFFFFF;
        border-radius: 14px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------------------------------------
# CONTROLLO SESSIONE & GATEWAY DI LOGIN
# -------------------------------------------------------------------------------------------------
if "autenticato" not in st.session_state:
    st.session_state["autenticato"] = False
    st.session_state["username_attivo"] = ""

if not st.session_state["autenticato"]:
    st.markdown("<div class='login-box'>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align:center; color:#1E3A8A;'>🔒 Accesso Riservato</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#64748B; font-size:0.9rem;'>Studio di Nutrizione Clinica & Metabolismo</p>", unsafe_allow_html=True)
    
    with st.form("form_login"):
        user_input = st.text_input("Nome Utente", placeholder="es: dott.casa")
        pwd_input = st.text_input("Password", type="password", placeholder="••••••••")
        btn_login = st.form_submit_button("Accedi alla Piattaforma", type="primary", use_container_width=True)
        
        if btn_login:
            u_clean = user_input.strip().lower()
            p_clean = pwd_input.strip()
            if u_clean == ADMIN_USER and p_clean == ADMIN_PWD:
                st.session_state["autenticato"] = True
                st.session_state["username_attivo"] = u_clean
                st.rerun()
            else:
                st.error("Credenziali non valide. Riprova.")
    
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# -------------------------------------------------------------------------------------------------
# INTESTAZIONE SESSIONE UTENTE CON LOGOUT
# -------------------------------------------------------------------------------------------------
c_top_title, c_top_user = st.columns([4, 1.2])
with c_top_title:
    st.markdown("<span style='font-weight:700; color:#1E3A8A; font-size:1.1rem;'>🥗 Studio di Nutrizione Clinica & Metabolismo</span>", unsafe_allow_html=True)
with c_top_user:
    c_u_name, c_u_btn = st.columns([1.8, 1])
    with c_u_name:
        st.write(f"👤 `{st.session_state['username_attivo']}`")
    with c_u_btn:
        if st.button("Esci", help="Termina sessione"):
            st.session_state["autenticato"] = False
            st.session_state["username_attivo"] = ""
            st.rerun()

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

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

# Menu Principale
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

# -------------------------------------------------------------------------------------------------
# 1. CARTELLA PAZIENTI
# -------------------------------------------------------------------------------------------------
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
            with c1: n = st.text_input("Nome*"); cf = st.text_input("Codice Fiscale*").upper()
            with c2: c = st.text_input("Cognome*"); dn = st.date_input("Data di Nascita", value=date(1975, 1, 1), min_value=date(1920, 1, 1), max_value=date.today())
            with c3: tel = st.text_input("Telefono (es: 3401234567)"); em = st.text_input("Email")
            
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
            ca1, ca2 = st.columns(2)
            with ca1: up_pat = st.text_area("Anamnesi Patologica & Farmaci", value=p_sel.get("anamnesi_generale") or "", height=140, key=f"up_pat_{p_sel['id']}")
            with ca2: up_alim = st.text_area("Anamnesi Alimentare & Intolleranze", value=p_sel.get("anamnesi_alimentare") or "", height=140, key=f"up_alim_{p_sel['id']}")
            
            c_ob_up, _ = st.columns(2)
            with c_ob_up:
                curr_ob = p_sel.get("obiettivo_clinico") or "Dimagrimento / Ricomposizione"
                idx_ob = ["Dimagrimento / Ricomposizione", "Aumento Massa Muscolare", "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione"].index(curr_ob) if curr_ob in ["Dimagrimento / Ricomposizione", "Aumento Massa Muscolare", "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione"] else 0
                up_ob = st.selectbox("Obiettivo Primario:", ["Dimagrimento / Ricomposizione", "Aumento Massa Muscolare", "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione"], index=idx_ob, key=f"up_ob_{p_sel['id']}")

            up_note = st.text_area("Note di Visita & Obiettivi", value=p_sel.get("note_visita") or "", height=80, key=f"up_note_{p_sel['id']}")
            if st.button("💾 Salva Modifiche Cartella", type="primary", key=f"btn_save_{p_sel['id']}"):
                supabase.table("pazienti").update({
                    "anamnesi_generale": up_pat, "anamnesi_alimentare": up_alim, "note_visita": up_note, "obiettivo_clinico": up_ob
                }).eq("id", p_sel["id"]).execute()
                st.success("Cartella clinica salvata!")

        with tab_bmr:
            st.markdown("#### Calcolatore Energetico (Mifflin-St Jeor) & Ripartizione Macronutrienti")
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

            st.markdown("---")
            m_res1, m_res2, m_res3 = st.columns(3)
            m_res1.metric("BMR", f"{bmr:.0f} kcal")
            m_res2.metric("TDEE", f"{tdee:.0f} kcal")
            m_res3.metric("BMI", f"{bmi:.1f} kg/m²")

            st.markdown("#### 🎯 Strategia Nutrizionale per i Pasti")
            col_strat1, col_strat2, col_strat3 = st.columns([1.5, 1.5, 1.5])
            with col_strat1:
                tipo_piano = st.selectbox("Obiettivo:", ["Mantenimento (TDEE)", "Deficit Ipocalorico (-15%)", "Deficit Ipocalorico Marcato (-20%)", "Surplus Ipercalorico (+10%)", "Personalizzato"])
                if tipo_piano == "Deficit Ipocalorico (-15%)": kcal_target_calc = tdee * 0.85
                elif tipo_piano == "Deficit Ipocalorico Marcato (-20%)": kcal_target_calc = tdee * 0.80
                elif tipo_piano == "Surplus Ipercalorico (+10%)": kcal_target_calc = tdee * 1.10
                elif tipo_piano == "Mantenimento (TDEE)": kcal_target_calc = tdee
                else: kcal_target_calc = st.number_input("Kcal Target:", min_value=1000.0, value=float(round(tdee)), step=50.0)

            with col_strat2:
                g_pro_kg = st.slider("Proteine (g/kg peso):", min_value=1.0, max_value=2.6, value=1.6, step=0.1)
                grammi_p_calc = peso_kg * g_pro_kg
                kcal_p_calc = grammi_p_calc * 4.0

            with col_strat3:
                perc_fat = st.slider("Lipidi (% calorie totali):", min_value=15, max_value=40, value=25, step=1)
                kcal_fat_calc = (kcal_target_calc * (perc_fat / 100.0))
                grammi_fat_calc = kcal_fat_calc / 9.0

            kcal_carb_calc = max(0.0, kcal_target_calc - kcal_p_calc - kcal_fat_calc)
            grammi_carb_calc = kcal_carb_calc / 4.0
            litri_h2o_calc = round(peso_kg * 0.035, 1)

            st.markdown("##### Riepilogo Target:")
            c_tr1, c_tr2, c_tr3, c_tr4, c_tr5 = st.columns(5)
            c_tr1.metric("Kcal", f"{kcal_target_calc:.0f} kcal")
            c_tr2.metric("Proteine", f"{grammi_p_calc:.0f} g")
            c_tr3.metric("Carboidrati", f"{grammi_carb_calc:.0f} g")
            c_tr4.metric("Grassi", f"{grammi_fat_calc:.0f} g")
            c_tr5.metric("Acqua", f"{litri_h2o_calc} L/die")

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
            st.markdown("#### Storico Rilevazioni, Circonferenze & BIA")
            with st.expander("➕ Inserisci Nuova Misurazione & Dati BIA"):
                with st.form("form_misura_add", clear_on_submit=True):
                    st.write("**1. Peso e Circonferenze Corporee**")
                    c_m1, c_m2, c_m3 = st.columns(3)
                    with c_m1:
                        data_m = st.date_input("Data Visita", value=date.today())
                        p_mis = st.number_input("Peso Corporeo (kg)*", min_value=30.0, value=75.0, step=0.1)
                    with c_m2:
                        cvita = st.number_input("Circ. Vita (cm)", min_value=40.0, value=82.0, step=0.5)
                        cfianchi = st.number_input("Circ. Fianchi (cm)", min_value=50.0, value=98.0, step=0.5)
                    with c_m3:
                        ccoscia = st.number_input("Circ. Coscia (cm)", min_value=30.0, value=55.0, step=0.5)
                        cbraccio = st.number_input("Circ. Braccio (cm)", min_value=15.0, value=30.0, step=0.5)
                    
                    st.write("**2. Parametri Bioimpedenziometrici (BIA)**")
                    c_bia1, c_bia2, c_bia3, c_bia4 = st.columns(4)
                    with c_bia1:
                        fm_kg = st.number_input("Massa Grassa - FM (kg)", min_value=0.0, value=15.0, step=0.1)
                    with c_bia2:
                        ffm_kg = st.number_input("Massa Magra - FFM (kg)", min_value=0.0, value=60.0, step=0.1)
                    with c_bia3:
                        tbw_lt = st.number_input("Acqua Corporea - TBW (L)", min_value=0.0, value=44.0, step=0.1)
                    with c_bia4:
                        angolo_fase_val = st.number_input("Angolo di Fase (deg)", min_value=0.0, max_value=15.0, value=6.5, step=0.1)

                    note_m = st.text_input("Note Controllo (es: Buona aderenza, inizio integrazione...)")
                    
                    if st.form_submit_button("Salva Rilevazione Completa", type="primary"):
                        fm_p = round((fm_kg / p_mis) * 100.0, 1) if p_mis > 0 else 0.0
                        ffm_p = round((ffm_kg / p_mis) * 100.0, 1) if p_mis > 0 else 0.0
                        try:
                            supabase.table("misure_pazienti").insert({
                                "paziente_id": p_sel["id"], "data_rilevazione": str(data_m), "peso_kg": p_mis,
                                "circ_vita_cm": cvita, "circ_fianchi_cm": cfianchi, "circ_coscia_cm": ccoscia, "circ_braccio_cm": cbraccio,
                                "massa_grassa_kg": fm_kg, "massa_grassa_perc": fm_p, "massa_magra_kg": ffm_kg, "massa_magra_perc": ffm_p,
                                "acqua_totale_litri": tbw_lt, "angolo_fase": angolo_fase_val, "note": note_m
                            }).execute()
                            st.success("Rilevazione e analisi BIA salvate!")
                            st.rerun()
                        except Exception as err:
                            st.error(f"Errore: {err}")

            try:
                res_mis = supabase.table("misure_pazienti").select("*").eq("paziente_id", p_sel["id"]).order("data_rilevazione").execute()
                dati_misure = res_mis.data or []
            except Exception: dati_misure = []

            if dati_misure:
                df_m = pd.DataFrame(dati_misure)
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    fig_p, ax_p = plt.subplots(figsize=(5, 2.3))
                    ax_p.plot(df_m["data_rilevazione"], df_m["peso_kg"], marker='o', color='#2563EB', linewidth=2, label="Peso (kg)")
                    ax_p.set_title("Andamento Peso (kg)", fontweight='bold')
                    ax_p.grid(True, linestyle='--', alpha=0.5)
                    st.pyplot(fig_p)
                
                with c_g2:
                    fig_bia, ax_bia = plt.subplots(figsize=(5, 2.3))
                    if "massa_magra_kg" in df_m.columns and df_m["massa_magra_kg"].dropna().count() > 0:
                        ax_bia.plot(df_m["data_rilevazione"], df_m["massa_magra_kg"], marker='^', label="Massa Magra (FFM kg)", color='#10B981', linewidth=2)
                        ax_bia.plot(df_m["data_rilevazione"], df_m["massa_grassa_kg"], marker='v', label="Massa Grassa (FM kg)", color='#EF4444', linewidth=2)
                        ax_bia.set_title("Composizione Corporea BIA (kg)", fontweight='bold')
                        ax_bia.legend()
                        ax_bia.grid(True, linestyle='--', alpha=0.5)
                    else:
                        ax_bia.plot(df_m["data_rilevazione"], df_m["circ_vita_cm"], marker='s', label="Vita", color='#10B981')
                        ax_bia.plot(df_m["data_rilevazione"], df_m["circ_fianchi_cm"], marker='^', label="Fianchi", color='#F59E0B')
                        ax_bia.set_title("Andamento Circonferenze (cm)", fontweight='bold')
                        ax_bia.legend()
                        ax_bia.grid(True, linestyle='--', alpha=0.5)
                    st.pyplot(fig_bia)

                st.write("##### Dati Storici e Bioimpedenziometrici:")
                col_view = ["data_rilevazione", "peso_kg", "circ_vita_cm", "circ_fianchi_cm"]
                if "massa_grassa_kg" in df_m.columns:
                    col_view.extend(["massa_grassa_kg", "massa_grassa_perc", "massa_magra_kg", "massa_magra_perc", "acqua_totale_litri", "angolo_fase"])
                col_view.append("note")
                st.dataframe(df_m[[c for c in col_view if c in df_m.columns]], use_container_width=True)
            else:
                st.info("Nessuna misurazione presente.")

        with tab_esami:
            st.markdown("#### 🧪 Registro Esami Ematochimici")
            with st.expander("➕ Registra Parametro"):
                with st.form("form_esame_add", clear_on_submit=True):
                    c_e1, c_e2, c_e3 = st.columns(3)
                    with c_e1:
                        data_esame = st.date_input("Data Referto", value=date.today())
                        parametro = st.selectbox("Parametro Clinico:", [
                            "Glicemia a digiuno", "Emoglobina Glicata (HbA1c)", "Colesterolo Totale", 
                            "Colesterolo HDL", "Colesterolo LDL", "Trigliceridi", "Vitamina D (25-OH)", 
                            "Vitamina B12", "Ferritina", "Sideremia", "Creatinina", "Acido Urico", "TSH", "ALT (GPT)", "AST (GOT)"
                        ])
                    with c_e2:
                        valore = st.number_input("Valore Riscontrato", min_value=0.0, value=90.0, step=1.0)
                        unita = st.text_input("Unità di Misura", value="mg/dL")
                    with c_e3:
                        val_min = st.number_input("Minimo Riferimento", min_value=0.0, value=70.0, step=1.0)
                        val_max = st.number_input("Massimo Riferimento", min_value=0.0, value=100.0, step=1.0)
                    note_es = st.text_input("Note Referto")
                    if st.form_submit_button("Salva Esame", type="primary"):
                        try:
                            supabase.table("esami_laboratorio").insert({
                                "paziente_id": p_sel["id"], "data_esame": str(data_esame), "parametro": parametro,
                                "valore": valore, "unita_misura": unita, "valore_min": val_min, "valore_max": val_max, "note": note_es
                            }).execute()
                            st.success("Registrato!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore: {e}")

            try:
                res_esami = supabase.table("esami_laboratorio").select("*").eq("paziente_id", p_sel["id"]).order("data_esame", desc=True).execute()
                dati_esami = res_esami.data or []
            except Exception: dati_esami = []

            if dati_esami:
                for es in dati_esami:
                    col_es1, col_es2, col_es3, col_es4 = st.columns([1.5, 2.5, 2.5, 1])
                    v = float(es["valore"]); vmin = float(es.get("valore_min") or 0); vmax = float(es.get("valore_max") or 9999)
                    stato_html = "<span class='traffic-green'>Normale</span>"
                    if v < vmin or v > vmax: stato_html = f"<span class='traffic-red'>Fuori Range ({vmin}-{vmax})</span>"

                    with col_es1: st.write(f"📅 **{es['data_esame']}**")
                    with col_es2: st.write(f"**{es['parametro']}**: `{v} {es['unita_misura']}`")
                    with col_es3: st.markdown(stato_html, unsafe_allow_html=True)
                    with col_es4:
                        if st.button("🗑️", key=f"del_es_{es['id']}"):
                            supabase.table("esami_laboratorio").delete().eq("id", es["id"]).execute()
                            st.rerun()
            else:
                st.info("Nessun esame registrato.")

        with tab_msg:
            st.markdown("#### 💬 Invio Rapido Promemoria Visita")
            c_dt_v, c_hr_v = st.columns(2)
            with c_dt_v: dt_prox = st.date_input("Data Appuntamento:", value=date.today() + timedelta(days=2))
            with c_hr_v: hr_prox = st.time_input("Orario Appuntamento:", value=datetime.strptime("10:30", "%H:%M").time())

            testo_default_wa = (
                f"Gentile {p_sel['nome']}, le ricordo il Suo appuntamento per il controllo nutrizionale "
                f"fissato per {dt_prox.strftime('%d/%m/%Y')} alle ore {hr_prox.strftime('%H:%M')} presso lo studio. "
                f"In caso di variazioni La prego di avvisarmi con anticipo. Dott. Rodolfo Casa"
            )
            msg_personalizzato = st.text_area("Testo del Messaggio:", value=testo_default_wa, height=100)

            c_btn_wa, c_btn_em = st.columns(2)
            with c_btn_wa:
                if tel_wa:
                    url_wa = f"https://wa.me/{tel_wa}?text={urllib.parse.quote(msg_personalizzato)}"
                    st.link_button("📲 Apri WhatsApp Web / Invia Messaggio", url_wa, type="primary", use_container_width=True)
                else:
                    st.warning("Numero di telefono non presente.")
            with c_btn_em:
                email_paz = p_sel.get("email") or ""
                if email_paz:
                    url_mailto = f"mailto:{email_paz}?subject=Promemoria%20Visita%20Nutrizionale&body={urllib.parse.quote(msg_personalizzato)}"
                    st.link_button("✉️ Invia Promemoria Email", url_mailto, use_container_width=True)
                else:
                    st.info("Email non presente.")

        with tab_sintesi:
            st.markdown("#### 📄 Foglio di Sintesi Clinica Visita (One-Page Summary)")
            class PDFOnePageSummary(FPDF):
                def header(self):
                    self.set_font('Helvetica', 'B', 13)
                    self.cell(self.epw, 7, "STUDIO DI NUTRIZIONE CLINICA - SCHEDA SINTESI VISITA", align='C', new_x="LMARGIN", new_y="NEXT")
                    self.ln(2)
                def footer(self):
                    self.set_y(-10)
                    self.set_font('Helvetica', 'I', 7.5)
                    self.cell(self.epw, 5, "Documento a uso interno professionale - Riservato", align='C')

            def crea_pdf_one_page():
                pdf = PDFOnePageSummary()
                pdf.set_auto_page_break(auto=True, margin=10)
                pdf.add_page()
                w_utile = pdf.epw

                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_fill_color(240, 244, 248)
                pdf.cell(w_utile, 6, " 1. ANAGRAFICA E CONTATTI RAPIDI ", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8.5)
                pdf.cell(w_utile, 5, f"Paziente: {p_sel['cognome']} {p_sel['nome']} | CF: {p_sel.get('codice_fiscale') or 'N/D'} | Nascita: {p_sel.get('data_nascita') or 'N/D'}", new_x="LMARGIN", new_y="NEXT")
                pdf.cell(w_utile, 5, f"Tel: {p_sel.get('telefono') or 'N/D'} | Email: {p_sel.get('email') or 'N/D'} | Obiettivo: {p_sel.get('obiettivo_clinico') or 'Dimagrimento'}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)

                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_fill_color(254, 242, 242)
                pdf.cell(w_utile, 6, " 2. QUADRO CLINICO, PATOLOGIE & TERAPIE FARMACOLOGICHE ", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8)
                pat_txt = p_sel.get("anamnesi_generale") or "Nessuna patologia o terapia farmacologica segnalata."
                pdf.multi_cell(w_utile, 4.5, f"Patologie / Farmaci: {pat_txt}", new_x="LMARGIN", new_y="NEXT")
                alim_txt = p_sel.get("anamnesi_alimentare") or "Nessuna allergia o intolleranza nota."
                pdf.multi_cell(w_utile, 4.5, f"Allergie / Abitudini: {alim_txt}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)

                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_fill_color(240, 253, 244)
                pdf.cell(w_utile, 6, " 3. ANDAMENTO ANTROPOMETRICO E COMPOSIZIONE CORPOREA (BIA) ", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8)
                try: res_m_paz = supabase.table("misure_pazienti").select("*").eq("paziente_id", p_sel["id"]).order("data_rilevazione").execute().data or []
                except Exception: res_m_paz = []

                if res_m_paz:
                    prima_m = res_m_paz[0]; ultima_m = res_m_paz[-1]
                    p_init = float(prima_m.get("peso_kg") or 0); p_curr = float(ultima_m.get("peso_kg") or 0)
                    diff_p = p_curr - p_init; segno = "+" if diff_p > 0 else ""
                    pdf.cell(w_utile, 4.5, f"Peso: {p_init:.1f} kg -> {p_curr:.1f} kg (Delta: {segno}{diff_p:.1f} kg) | Circ. Vita: {ultima_m.get('circ_vita_cm') or 'N/D'} cm | Fianchi: {ultima_m.get('circ_fianchi_cm') or 'N/D'} cm", new_x="LMARGIN", new_y="NEXT")
                    if ultima_m.get("massa_grassa_kg"):
                        fm_v = float(ultima_m.get("massa_grassa_kg") or 0); ffm_v = float(ultima_m.get("massa_magra_kg") or 0); ph_v = float(ultima_m.get("angolo_fase") or 0)
                        pdf.cell(w_utile, 4.5, f"Analisi BIA: Massa Grassa (FM): {fm_v:.1f} kg ({ultima_m.get('massa_grassa_perc')}%) | Massa Magra (FFM): {ffm_v:.1f} kg ({ultima_m.get('massa_magra_perc')}%) | Angolo di Fase: {ph_v:.2f} deg", new_x="LMARGIN", new_y="NEXT")
                else:
                    pdf.cell(w_utile, 4.5, "Nessuna misurazione antropometrica registrata finora.", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)

                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_fill_color(254, 243, 199)
                pdf.cell(w_utile, 6, " 4. PARAMETRI EMATOCHIMICI SALIENTI / FUORI NORMA ", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8)
                try: res_es_paz = supabase.table("esami_laboratorio").select("*").eq("paziente_id", p_sel["id"]).order("data_esame", desc=True).execute().data or []
                except Exception: res_es_paz = []

                if res_es_paz:
                    for es in res_es_paz[:5]:
                        v = float(es["valore"]); vmin = float(es.get("valore_min") or 0); vmax = float(es.get("valore_max") or 9999)
                        flag = "[FUORI RANGE]" if (v < vmin or v > vmax) else "[OK]"
                        pdf.cell(w_utile, 4.5, f"- {es['parametro']}: {v} {es['unita_misura']} (Rif: {vmin}-{vmax}) {flag} (del {es['data_esame']})", new_x="LMARGIN", new_y="NEXT")
                else:
                    pdf.cell(w_utile, 4.5, "Nessun esame ematochimico refertato in cartella.", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)

                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_fill_color(243, 244, 246)
                pdf.cell(w_utile, 6, " 5. OBIETTIVI NUTRIZIONALI & NOTE DEL PROFESSIONISTA ", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8)
                try: res_d_paz = supabase.table("diete").select("*").eq("paziente_id", p_sel["id"]).execute().data or []
                except Exception: res_d_paz = []

                if res_d_paz:
                    d_obj = res_d_paz[0]
                    pdf.cell(w_utile, 4.5, f"Target Energetico: {d_obj.get('target_kcal') or 'N/D'} kcal | P: {d_obj.get('target_proteine_g') or 'N/D'}g | C: {d_obj.get('target_carboidrati_g') or 'N/D'}g | G: {d_obj.get('target_grassi_g') or 'N/D'}g", new_x="LMARGIN", new_y="NEXT")
                note_str = p_sel.get('note_visita') or 'Nessuna nota aggiuntiva.'
                pdf.multi_cell(w_utile, 4.5, f"Note Visita: {note_str}", new_x="LMARGIN", new_y="NEXT")
                return bytes(pdf.output())

            try:
                st.download_button("📥 Scarica Scheda Sintesi Visita One-Page (PDF)", crea_pdf_one_page(), file_name=f"Sintesi_Visita_{p_sel['cognome']}_{p_sel['nome']}.pdf", mime="application/pdf", type="primary", use_container_width=True)
            except Exception as e_pdf:
                st.error(f"Errore generazione PDF sintesi: {e_pdf}")

        with tab_consenso:
            st.markdown("#### 📑 Modulo di Consenso Informato & Privacy GDPR con Firma Elettronica")
            st.caption("Fai apporre la firma al paziente direttamente sul display tramite penna touch, dito o mouse.")

            class PDFConsenso(FPDF):
                def header(self):
                    self.set_font('Helvetica', 'B', 14)
                    self.cell(self.epw, 7, 'STUDIO DI NUTRIZIONE CLINICA', align='C', new_x="LMARGIN", new_y="NEXT")
                    self.set_font('Helvetica', 'I', 9)
                    self.cell(self.epw, 5, 'Consenso Informato al Trattamento Nutrizionale & Privacy GDPR', align='C', new_x="LMARGIN", new_y="NEXT")
                    self.ln(6)
                def footer(self):
                    self.set_y(-12)
                    self.set_font('Helvetica', 'I', 8)
                    self.cell(self.epw, 10, f'Pagina {self.page_no()}', align='C')

            def genera_pdf_consenso(firma_img=None):
                pdf = PDFConsenso()
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()
                w_utile = pdf.epw

                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(w_utile, 6, "DATI DEL PAZIENTE:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(w_utile, 5, f"Nome e Cognome: {p_sel['cognome']} {p_sel['nome']}", new_x="LMARGIN", new_y="NEXT")
                pdf.cell(w_utile, 5, f"Codice Fiscale: {p_sel.get('codice_fiscale') or 'N/D'} | Data di Nascita: {p_sel.get('data_nascita') or 'N/D'}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(4)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(w_utile, 6, "1. PRESTAZIONE PROFESSIONALE & OBIETTIVI", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8.5)
                pdf.multi_cell(w_utile, 4.5, "Il sottoscritto dichiara di essere stato informato in merito alle finalita' della consulenza nutrizionale e rilievi antropometrici. Il percorso ha valore di rieducazione nutrizionale e benessere psicofisico.", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(w_utile, 6, "2. TRATTAMENTO DATI E TRASMISSIONE SISTEMA TS (REG. UE 2016/679)", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8.5)
                pdf.multi_cell(w_utile, 4.5, "I dati forniti saranno trattati conformemente al GDPR per finalita' sanitarie, inclusa la trasmissione telematica al Sistema Tessera Sanitaria salvo opposizione.", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(8)
                
                pdf.set_font("Helvetica", "", 9)
                data_oggi = date.today().strftime('%d/%m/%Y')
                pdf.cell(100, 6, f"Data: {data_oggi}", align='L')
                pdf.cell(w_utile - 100, 6, "Firma del Paziente:", align='R', new_x="LMARGIN", new_y="NEXT")
                pdf.ln(4)

                if firma_img is not None:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                        firma_img.save(tmp_file.name)
                        pdf.image(tmp_file.name, x=w_utile - 60, y=pdf.get_y(), w=55)
                        tmp_path = tmp_file.name
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                else:
                    pdf.cell(100, 6, "")
                    pdf.cell(w_utile - 100, 6, "________________________________________", align='R')

                return bytes(pdf.output())

            st.write("✍️ **Firma del Paziente nel riquadro sottostante:**")
            
            try:
                canvas_result = st_canvas(
                    stroke_width=2,
                    stroke_color="#000000",
                    background_color="#F8FAFC",
                    height=150,
                    width=500,
                    drawing_mode="freedraw",
                    key=f"canvas_{p_sel['id']}"
                )
                firma_pil = None
                if canvas_result.image_data is not None:
                    img_data = canvas_result.image_data
                    if img_data.max() > 0:
                        firma_pil = Image.fromarray(img_data.astype('uint8'))
            except Exception as e_canvas:
                st.warning("Modalità firma alternativa attiva (Canvas non caricato)")
                firma_pil = None

            col_btn_sign1, col_btn_sign2 = st.columns([1.5, 2])
            with col_btn_sign1:
                st.download_button(
                    "📄 Scarica Consenso Firmato (PDF)",
                    genera_pdf_consenso(firma_pil),
                    file_name=f"Consenso_Firmato_{p_sel['cognome']}_{p_sel['nome']}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            with col_btn_sign2:
                if firma_pil:
                    st.success("Firma acquisita e pronta per il PDF!")
                else:
                    st.info("Traccia la firma sopra oppure scarica il modulo standard.")

# -------------------------------------------------------------------------------------------------
# 2. PIANO SETTIMANALE & TEMPLATE
# -------------------------------------------------------------------------------------------------
elif scelta_menu == "🥗 Piano Settimanale & Template":
    res_paz = supabase.table("pazienti").select("id, nome, cognome, codice_fiscale").order("cognome").execute()
    pazienti = res_paz.data or []
    if not pazienti:
        st.warning("Nessun paziente presente.")
    else:
        mappa_paz = {f"{p['cognome']} {p['nome']} (CF: {p.get('codice_fiscale') or 'N/D'})": p for p in pazienti}
        col_paz, col_btn_pdf = st.columns([3.2, 1.3])
        with col_paz:
            sel_paz_str = st.selectbox("Cartella Paziente Attiva:", list(mappa_paz.keys()))
            paziente = mappa_paz[sel_paz_str]
        
        res_d = supabase.table("diete").select("*").eq("paziente_id", paziente["id"]).execute()
        dieta = res_d.data[0] if res_d.data else supabase.table("diete").insert({"paziente_id": paziente["id"], "titolo": f"Piano - {paziente['cognome']}"}).execute().data[0]

        res_al = supabase.table("alimenti").select("*").order("nome").execute()
        alimenti_list = res_al.data or []
        dict_alimenti = {a["nome"].lower(): a for a in alimenti_list}
        nomi_completi = [a["nome"] for a in alimenti_list]

        res_voci = supabase.table("voci_dieta").select(
            "id, giorno_settimana, pasto, grammi, alimenti(nome, energia_kcal, proteine_g, lipidi_g, carboidrati_g, fibra_g)"
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

        col_tpl_carica, col_tpl_salva, col_tpl_gemini = st.columns([1.5, 1.5, 2])
        
        with col_tpl_carica:
            with st.expander("⚡ Carica Dieta Tipo"):
                try:
                    res_tpl = supabase.table("template_diete").select("*").order("nome").execute()
                    templates = res_tpl.data or []
                except Exception: templates = []

                if templates:
                    tpl_map = {f"{t['nome']} (~{t.get('target_kcal') or 2000} kcal)": t for t in templates}
                    scelto_tpl_str = st.selectbox("Seleziona Template:", list(tpl_map.keys()))
                    tpl_obj = tpl_map[scelto_tpl_str]
                    
                    if st.button("📥 Applica al Paziente", type="primary"):
                        supabase.table("voci_dieta").delete().eq("dieta_id", dieta["id"]).execute()
                        voci_tpl = supabase.table("template_voci_dieta").select("*").eq("template_id", tpl_obj["id"]).execute().data or []
                        for vt in voci_tpl:
                            supabase.table("voci_dieta").insert({
                                "dieta_id": dieta["id"], "giorno_settimana": vt["giorno_settimana"],
                                "pasto": vt["pasto"], "alimento_id": vt["alimento_id"], "grammi": vt["grammi"]
                            }).execute()
                        st.success("Template applicato!")
                        st.rerun()
                else:
                    st.info("Nessun template.")

        with col_tpl_salva:
            with st.expander("💾 Salva come Template"):
                nome_nuovo_tpl = st.text_input("Nome Modello:", placeholder="Es: Ipocalorica 1600")
                if st.button("Salva Template"):
                    if nome_nuovo_tpl.strip() and not df_dieta.empty:
                        nuovo_t = supabase.table("template_diete").insert({
                            "nome": nome_nuovo_tpl.strip(), "descrizione": "Creato da gestionale", "target_kcal": float(dieta.get("target_kcal") or 2000.0)
                        }).execute().data[0]
                        voci_da_salvare = supabase.table("voci_dieta").select("*").eq("dieta_id", dieta["id"]).execute().data or []
                        for vs in voci_da_salvare:
                            supabase.table("template_voci_dieta").insert({
                                "template_id": nuovo_t["id"], "giorno_settimana": vs["giorno_settimana"],
                                "pasto": vs["pasto"], "alimento_id": vs["alimento_id"], "grammi": vs["grammi"]
                            }).execute()
                        st.success("Template salvato!")
                        st.rerun()
                    else:
                        st.warning("Inserisci nome e alimenti.")

        with col_tpl_gemini:
            with st.expander("✨ Genera Template con AI (Gemini)"):
                uploaded_file = st.file_uploader("Carica file piano alimentare (PDF o TXT):", type=["pdf", "txt"])
                nome_gen_tpl = st.text_input("Nome per il nuovo Template AI:", placeholder="Es: Dieta da PDF Esistente")
                
                if st.button("🤖 Estrai e Crea Template con AI", type="primary"):
                    if uploaded_file and nome_gen_tpl.strip():
                        with st.spinner("Gemini sta analizzando il file e strutturando il template..."):
                            try:
                                file_bytes = uploaded_file.read()
                                model = genai.GenerativeModel('gemini-1.5-flash')
                                
                                prompt_ia = (
                                    "Analizza il documento allegato contenente un piano alimentare. "
                                    "Estrai i giorni della settimana (Lunedì, Martedì, Mercoledì, Giovedì, Venerdì, Sabato, Domenica), "
                                    "i pasti (Colazione, Spuntino Mattina, Pranzo, Merenda Pomeriggio, Cena) e gli alimenti con le rispettive grammature. "
                                    "Restituisci ESCLUSIVAMENTE un oggetto JSON valido con questa struttura esatta:\n"
                                    "[\n  {\"giorno\": \"Lunedì\", \"pasto\": \"Pranzo\", \"alimento\": \"Nome Alimento Esatto\", \"grammi\": 100},\n...\n]"
                                )
                                
                                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
                                    tmp.write(file_bytes)
                                    tmp_name = tmp.name
                                
                                sample_file = genai.upload_file(path=tmp_name)
                                response = model.generate_content([sample_file, prompt_ia])
                                
                                if os.path.exists(tmp_name): os.remove(tmp_name)
                                
                                raw_text = response.text.strip()
                                if "```json" in raw_text:
                                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                                elif "```" in raw_text:
                                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                                
                                dati_estratti = json.loads(raw_text)
                                
                                if dati_estratti:
                                    nuovo_t_ai = supabase.table("template_diete").insert({
                                        "nome": nome_gen_tpl.strip(), "descrizione": "Generato automaticamente con Gemini AI", "target_kcal": 2000.0
                                    }).execute().data[0]
                                    
                                    res_al_all = supabase.table("alimenti").select("id, nome").execute().data or []
                                    al_dict = {a["nome"].lower(): a["id"] for a in res_al_all}
                                    
                                    inseriti = 0
                                    for item in dati_estratti:
                                        alim_nome = item.get("alimento", "").strip().lower()
                                        grammi = float(item.get("grammi", 100))
                                        giorno = item.get("giorno", "Lunedì")
                                        pasto = item.get("pasto", "Pranzo")
                                        
                                        match_id = None
                                        for k, aid in al_dict.items():
                                            if alim_nome in k or k in alim_nome:
                                                match_id = aid
                                                break
                                        
                                        if not match_id and res_al_all:
                                            match_id = res_al_all[0]["id"]
                                            
                                        if match_id:
                                            supabase.table("template_voci_dieta").insert({
                                                "template_id": nuovo_t_ai["id"],
                                                "giorno_settimana": giorno,
                                                "pasto": pasto,
                                                "alimento_id": match_id,
                                                "grammi": grammi
                                            }).execute()
                                            inseriti += 1
                                            
                                    st.success(f"Template '{nome_gen_tpl}' creato con successo tramite IA ({inseriti} voci importate)!")
                                    st.rerun()
                                else:
                                    st.error("Gemini non ha restituito dati validi.")
                            except Exception as e_ai:
                                st.error(f"Errore durante l'elaborazione con Gemini: {e_ai}")
                    else:
                        st.warning("Carica un file e inserisci un nome per il template.")

        with col_btn_pdf:
            st.write("")
            st.write("")
            if not df_dieta.empty:
                class PDFPianoCompleto(FPDF):
                    def header(self):
                        self.set_font('Helvetica', 'B', 14)
                        self.cell(self.epw, 7, 'STUDIO DI NUTRIZIONE CLINICA', align='C', new_x="LMARGIN", new_y="NEXT")
                        self.set_font('Helvetica', 'I', 9)
                        self.cell(self.epw, 5, 'Piano Nutrizionale Personalizzato Settimanale', align='C', new_x="LMARGIN", new_y="NEXT")
                        self.ln(3)
                    def footer(self):
                        self.set_y(-12)
                        self.set_font('Helvetica', 'I', 8)
                        self.cell(self.epw, 10, f'Pagina {self.page_no()}', align='C')

                def genera_pdf_completo():
                    pdf = PDFPianoCompleto()
                    pdf.set_auto_page_break(auto=True, margin=12)
                    pdf.add_page()
                    w_utile = pdf.epw

                    pdf.set_font("Helvetica", "B", 10)
                    pdf.cell(w_utile, 5, f"Paziente: {paziente['cognome']} {paziente['nome']} | CF: {paziente.get('codice_fiscale') or 'N/D'}", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", "", 8.5)
                    pdf.cell(w_utile, 5, f"Data Rilascio: {date.today().strftime('%d/%m/%Y')} | Target: {dieta.get('target_kcal')} kcal | Acqua: {dieta.get('litri_acqua')} L/die", new_x="LMARGIN", new_y="NEXT")
                    pdf.ln(3)

                    for g in giorni_settimana:
                        sg = df_dieta[df_dieta["Giorno"] == g]
                        if not sg.empty:
                            pdf.set_font("Helvetica", "B", 9.5)
                            pdf.set_fill_color(232, 240, 254)
                            pdf.cell(w_utile, 5.5, f"  {g.upper()}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                            for p in sg["Pasto"].unique():
                                sp = sg[sg["Pasto"] == p]
                                pdf.set_font("Helvetica", "B", 8.5)
                                pdf.cell(w_utile, 4.5, f"    * {p}:", new_x="LMARGIN", new_y="NEXT")
                                pdf.set_font("Helvetica", "", 8)
                                for _, r in sp.iterrows():
                                    pdf.cell(w_utile, 4, f"       - {r['Alimento']}: {r['Grammi']}g ({r['Kcal']} kcal | P:{r['Proteine']}g C:{r['Carboidrati']}g G:{r['Grassi']}g)", new_x="LMARGIN", new_y="NEXT")
                            pdf.ln(1.5)

                    pdf.add_page()
                    if dieta.get("note_integrazione"):
                        pdf.set_font("Helvetica", "B", 11)
                        pdf.cell(w_utile, 6, "PIANO DI INTEGRAZIONE NUTRIZIONALE", new_x="LMARGIN", new_y="NEXT")
                        pdf.set_font("Helvetica", "", 8.5)
                        pdf.multi_cell(w_utile, 4.5, dieta.get("note_integrazione"), new_x="LMARGIN", new_y="NEXT")
                        pdf.ln(3)

                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(w_utile, 6, "GUIDA RAPIDA ALLE SOSTITUZIONI ALIMENTARI", new_x="LMARGIN", new_y="NEXT")
                    for s in TABELLA_SOSTITUZIONI:
                        pdf.set_font("Helvetica", "B", 8.5)
                        pdf.cell(w_utile, 5, f"- {s['Gruppo']}:", new_x="LMARGIN", new_y="NEXT")
                        pdf.set_font("Helvetica", "", 8)
                        pdf.multi_cell(w_utile, 4.5, f"  {s['Opzioni']}", new_x="LMARGIN", new_y="NEXT")
                        pdf.ln(1)

                    pdf.ln(3)
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(w_utile, 6, "LISTA DELLA SPESA SETTIMANALE AGGREGATA", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", "", 8.5)
                    spesa_agg = df_dieta.groupby("Alimento")["Grammi"].sum().reset_index().sort_values(by="Grammi", ascending=False)
                    for _, r_sp in spesa_agg.iterrows():
                        pdf.cell(w_utile, 4.5, f"  [ ] {r_sp['Alimento']}: {r_sp['Grammi']:.0f} g", new_x="LMARGIN", new_y="NEXT")
                    return bytes(pdf.output())

                st.download_button("📥 Scarica Piano & Spesa PDF", genera_pdf_completo(), file_name=f"Piano_Nutrizionale_{paziente['cognome']}.pdf", mime="application/pdf", type="primary", use_container_width=True)
            else:
                st.button("📥 Scarica Piano & Spesa PDF", disabled=True, use_container_width=True)

        st.markdown("### 📊 Monitoraggio Semaforo: Target vs Reale Medio")
        t_k = float(dieta.get("target_kcal") or 2000.0)
        t_prot = float(dieta.get("target_proteine_g") or 130.0)
        t_carb = float(dieta.get("target_carboidrati_g") or 220.0)
        t_fat = float(dieta.get("target_grassi_g") or 60.0)

        if not df_dieta.empty:
            tot_kcal = df_dieta["Kcal"].sum()
            tot_p = df_dieta["Proteine"].sum()
            tot_c = df_dieta["Carboidrati"].sum()
            tot_g = df_dieta["Grassi"].sum()
            media_die = tot_kcal / 7.0
            media_p = tot_p / 7.0
            media_c = tot_c / 7.0
            media_g = tot_g / 7.0

            def check_diff(reale, target):
                diff = reale - target
                perc = abs(diff) / target if target > 0 else 0
                cls = "traffic-green" if perc <= 0.08 else "traffic-red"
                segno = "+" if diff > 0 else ""
                return f"<span class='{cls}'>{reale:.0f} / {target:.0f} ({segno}{diff:.0f})</span>"

            c_sem1, c_sem2, c_sem3, c_sem4 = st.columns(4)
            with c_sem1: st.markdown(f"**Kcal Media/Die:**<br>{check_diff(media_die, t_k)}", unsafe_allow_html=True)
            with c_sem2: st.markdown(f"**Proteine (g/die):**<br>{check_diff(media_p, t_prot)}", unsafe_allow_html=True)
            with c_sem3: st.markdown(f"**Carboidrati (g/die):**<br>{check_diff(media_c, t_carb)}", unsafe_allow_html=True)
            with c_sem4: st.markdown(f"**Grassi (g/die):**<br>{check_diff(media_g, t_fat)}", unsafe_allow_html=True)

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                fig1, ax1 = plt.subplots(figsize=(4.5, 2.0))
                vals = [tot_c * 4, tot_p * 4, tot_g * 9]
                if sum(vals) > 0:
                    ax1.pie(vals, labels=['Carboidrati', 'Proteine', 'Grassi'], autopct='%1.1f%%', startangle=90, colors=['#3B82F6', '#10B981', '#F59E0B'])
                    ax1.axis('equal')
                    st.write("**Ripartizione Macro (%)**")
                    st.pyplot(fig1)
            with col_g2:
                fig2, ax2 = plt.subplots(figsize=(4.5, 2.0))
                k_giorni = [df_dieta[df_dieta["Giorno"] == g]["Kcal"].sum() for g in giorni_settimana]
                ax2.bar([g[:3] for g in giorni_settimana], k_giorni, color="#6366F1")
                ax2.axhline(t_k, color='red', linestyle='--', label=f'Target ({t_k:.0f} kcal)')
                ax2.set_ylabel("Kcal")
                ax2.legend()
                st.write("**Kcal per Giorno vs Target**")
                st.pyplot(fig2)
        else:
            st.info("Nessun alimento inserito.")

        st.markdown("---")
        tab_piano_visivo, tab_spesa_visiva, tab_sostituzioni_visiva = st.tabs(["🗓️ Menu Settimanale", "🛒 Lista Spesa Automatica", "🔄 Guida Sostituzioni"])
        with tab_spesa_visiva:
            if not df_dieta.empty:
                df_spesa = df_dieta.groupby("Alimento")["Grammi"].sum().reset_index().sort_values(by="Grammi", ascending=False)
                df_spesa.columns = ["Alimento da Acquistare", "Quantità Totale (g)"]
                st.dataframe(df_spesa, use_container_width=True)
            else:
                st.info("Aggiungi alimenti al menu.")

        with tab_sostituzioni_visiva:
            for s in TABELLA_SOSTITUZIONI:
                with st.expander(f"📌 {s['Gruppo']}"):
                    st.write(s["Opzioni"])

        with tab_piano_visivo:
            schede = st.tabs(giorni_settimana)
            for idx, g in enumerate(giorni_settimana):
                with schede[idx]:
                    df_g = df_dieta[df_dieta["Giorno"] == g] if not df_dieta.empty else pd.DataFrame()
                    if not df_g.empty:
                        st.markdown(f"**Totale {g}:** `{df_g['Kcal'].sum():.0f} Kcal` | 🥩 P: `{df_g['Proteine'].sum():.1f}g` | 🍚 C: `{df_g['Carboidrati'].sum():.1f}g` | 🥑 G: `{df_g['Grassi'].sum():.1f}g`")
                    st.markdown("---")

                    for p_nome in st.session_state["elenco_pasti"]:
                        st.markdown(f"<div class='meal-card'><strong>🍽️ {p_nome.upper()}</strong></div>", unsafe_allow_html=True)
                        if not df_g.empty:
                            sub_pasto = df_g[df_g["Pasto"] == p_nome]
                            for _, row in sub_pasto.iterrows():
                                c_info, c_del = st.columns([6, 1])
                                with c_info:
                                    st.write(f"• **{row['Alimento']}** — **{row['Grammi']}g** | `{row['Kcal']} kcal` (P: {row['Proteine']}g, C: {row['Carboidrati']}g, G: {row['Grassi']}g)")
                                with c_del:
                                    if st.button("❌", key=f"del_{row['id']}_{g}_{p_nome}", help="Elimina"):
                                        supabase.table("voci_dieta").delete().eq("id", row["id"]).execute()
                                        st.rerun()
                        
                        with st.form(f"form_add_{g}_{p_nome}", clear_on_submit=True):
                            c_in_al, c_in_gr, c_btn = st.columns([3.5, 1.2, 1.2])
                            with c_in_al: scelta_al = st.selectbox("Alimento:", nomi_completi, key=f"sel_{g}_{p_nome}", label_visibility="collapsed")
                            with c_in_gr: quantita = st.number_input("Grammi", min_value=5.0, value=100.0, step=10.0, key=f"gr_{g}_{p_nome}", label_visibility="collapsed")
                            with c_btn: invia = st.form_submit_button("➕ Inserisci", use_container_width=True, type="primary")
                            if invia and scelta_al:
                                al_obj = dict_alimenti[scelta_al.lower()]
                                supabase.table("voci_dieta").insert({
                                    "dieta_id": dieta["id"], "giorno_settimana": g, "pasto": p_nome,
                                    "alimento_id": al_obj["id"], "grammi": quantita
                                }).execute()
                                st.rerun()

# -------------------------------------------------------------------------------------------------
# 3. CATALOGO ALIMENTI
# -------------------------------------------------------------------------------------------------
elif scelta_menu == "🍎 Catalogo Alimenti & Cibi":
    st.subheader("🍎 Database Alimenti & Valori Nutrizionali dello Studio")
    st.caption("Aggiungi o consulta alimenti e prodotti commerciali (valori per 100g di parte edibile)[cite: 1].")

    tab_elenco_cibi, tab_nuovo_cibo = st.tabs(["📋 Tabella Alimenti dello Studio", "➕ Inserisci Nuovo Alimento / Prodotto"])

    with tab_nuovo_cibo:
        with st.form("form_nuovo_alimento", clear_on_submit=True):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                nome_cibo = st.text_input("Nome Alimento / Marchio Prodotto*", placeholder="Es: Fage Total 0%, Whey Isolate...")
                categoria_cibo = st.selectbox("Categoria:", ["Cereali & Derivati", "Carne, Pesce & Uova", "Latticini & Formaggi", "Frutta & Verdura", "Legumi", "Grassi & Condimenti", "Integratori", "Altro"])
            with col_a2:
                kcal_100g = st.number_input("Energia (Kcal per 100g)*", min_value=0.0, max_value=950.0, value=150.0, step=5.0)

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1: prot_100g = st.number_input("Proteine (g/100g)", min_value=0.0, max_value=100.0, value=10.0, step=0.5)
            with col_m2: carb_100g = st.number_input("Carboidrati (g/100g)", min_value=0.0, max_value=100.0, value=20.0, step=0.5)
            with col_m3: grassi_100g = st.number_input("Grassi / Lipidi (g/100g)", min_value=0.0, max_value=100.0, value=3.0, step=0.5)
            with col_m4: fibra_100g = st.number_input("Fibra (g/100g)", min_value=0.0, max_value=100.0, value=1.0, step=0.5)

            if st.form_submit_button("Salva Alimento nel Database", type="primary"):
                if nome_cibo.strip():
                    try:
                        supabase.table("alimenti").insert({
                            "nome": nome_cibo.strip(), "energia_kcal": kcal_100g, "proteine_g": prot_100g,
                            "carboidrati_g": carb_100g, "lipidi_g": grassi_100g, "fibra_g": fibra_100g, "categoria": categoria_cibo
                        }).execute()
                        st.success(f"Alimento '{nome_cibo}' inserito con successo!")
                        st.rerun()
                    except Exception as e_cibo:
                        st.error(f"Errore inserimento: {e_cibo}")
                else:
                    st.error("Il nome dell'alimento è obbligatorio.")

    with tab_elenco_cibi:
        try:
            res_all_alim = supabase.table("alimenti").select("*").order("nome").execute()
            lista_all_alim = res_all_alim.data or []
        except Exception: lista_all_alim = []

        if lista_all_alim:
            c_cerca_cibo, c_conteggio = st.columns([3, 1])
            with c_cerca_cibo: filtro_cibo = st.text_input("🔍 Cerca alimento per nome:", "").lower()
            with c_conteggio: st.write(""); st.write(f"Totale alimenti: **{len(lista_all_alim)}**")

            filtrati_cibi = [a for a in lista_all_alim if filtro_cibo in a["nome"].lower()]
            df_cibi = pd.DataFrame(filtrati_cibi)
            st.dataframe(df_cibi[["nome", "energia_kcal", "proteine_g", "carboidrati_g", "lipidi_g", "fibra_g", "categoria"]], use_container_width=True)

            with st.expander("🗑️ Eliminazione Alimento"):
                c_del_sel, c_del_act = st.columns([3, 1])
                with c_del_sel:
                    map_del_cibo = {f"{a['nome']} ({a['energia_kcal']} kcal)": a["id"] for a in filtrati_cibi}
                    if map_del_cibo: cibo_da_eliminare = st.selectbox("Seleziona alimento:", list(map_del_cibo.keys()))
                with c_del_act:
                    st.write("")
                    if map_del_cibo and st.button("Elimina Alimento", type="secondary"):
                        try:
                            supabase.table("alimenti").delete().eq("id", map_del_cibo[cibo_da_eliminare]).execute()
                            st.success("Alimento rimosso!")
                            st.rerun()
                        except Exception as e_del:
                            st.error(f"Impossibile eliminare: {e_del}")
        else:
            st.info("Nessun alimento presente nel database.")

# -------------------------------------------------------------------------------------------------
# 4. STATISTICHE CLINICHE & ANALYTICS
# -------------------------------------------------------------------------------------------------
elif scelta_menu == "📊 Statistiche & Analytics":
    st.subheader("📊 Cruscotto Statistico & Risultati Clinici dello Studio")
    st.caption("Panoramica globale dell'andamento dei pazienti, efficacia dei trattamenti e distribuzione degli obiettivi nutrizionali.")

    try:
        pazienti_all = supabase.table("pazienti").select("*").execute().data or []
        misure_all = supabase.table("misure_pazienti").select("*").order("data_rilevazione").execute().data or []
        visite_all = supabase.table("scadenze").select("*").execute().data or []
    except Exception:
        pazienti_all, misure_all, visite_all = [], [], []

    if pazienti_all:
        tot_pazienti = len(pazienti_all)
        tot_visite = len(visite_all)

        df_mis = pd.DataFrame(misure_all) if misure_all else pd.DataFrame()
        tot_kg_persi = 0.0
        miglior_calo = 0.0
        miglior_paziente_nome = "N/D"

        tabella_risultati = []
        if not df_mis.empty:
            for p in pazienti_all:
                sub_p = df_mis[df_mis["paziente_id"] == p["id"]]
                if len(sub_p) >= 2:
                    p_ini = float(sub_p.iloc[0]["peso_kg"])
                    p_fin = float(sub_p.iloc[-1]["peso_kg"])
                    delta = p_fin - p_ini
                    if delta < 0:
                        calo = abs(delta)
                        tot_kg_persi += calo
                        if calo > miglior_calo:
                            miglior_calo = calo
                            miglior_paziente_nome = f"{p['cognome']} {p['nome']}"
                    
                    tabella_risultati.append({
                        "Paziente": f"{p['cognome']} {p['nome']}",
                        "Obiettivo": p.get("obiettivo_clinico") or "Dimagrimento",
                        "Peso Iniziale (kg)": p_ini,
                        "Peso Attuale (kg)": p_fin,
                        "Variazione (kg)": round(delta, 1),
                        "Rilevazioni Effettuate": len(sub_p)
                    })

        col_st1, col_st2, col_st3, col_st4 = st.columns(4)
        col_st1.metric("Pazienti Totali in Archivio", f"{tot_pazienti}")
        col_st2.metric("Chili Persi Globali nello Studio", f"{tot_kg_persi:.1f} kg")
        col_st3.metric("Visite & Controlli Registrati", f"{tot_visite}")
        col_st4.metric("Miglior Risultato Singolo", f"-{miglior_calo:.1f} kg" if miglior_calo > 0 else "0.0 kg", f"{miglior_paziente_nome}")

        st.markdown("---")

        c_graf1, c_graf2 = st.columns(2)
        with c_graf1:
            st.markdown("##### 🎯 Distribuzione Obiettivi Clinici")
            df_paz = pd.DataFrame(pazienti_all)
            if "obiettivo_clinico" in df_paz.columns:
                ob_counts = df_paz["obiettivo_clinico"].fillna("Dimagrimento / Ricomposizione").value_counts()
                fig_ob, ax_ob = plt.subplots(figsize=(4.5, 2.3))
                ax_ob.pie(ob_counts.values, labels=ob_counts.index, autopct='%1.1f%%', startangle=90, colors=['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6'])
                ax_ob.axis('equal')
                st.pyplot(fig_ob)

        with c_graf2:
            st.markdown("##### 📈 Tipologia di Visite Pianificate")
            if visite_all:
                df_vis = pd.DataFrame(visite_all)
                vis_counts = df_vis["categoria"].fillna("ALTRO").value_counts()
                fig_vis, ax_vis = plt.subplots(figsize=(4.5, 2.3))
                ax_vis.bar([str(x)[:12] for x in vis_counts.index], vis_counts.values, color="#6366F1")
                ax_vis.set_ylabel("Numero Visite")
                plt.xticks(rotation=15)
                st.pyplot(fig_vis)

        st.markdown("---")
        st.markdown("##### 📋 Monitoraggio Aderenza e Progressi Pazienti")
        if tabella_risultati:
            df_tab_ris = pd.DataFrame(tabella_risultati).sort_values(by="Variazione (kg)")
            st.dataframe(df_tab_ris, use_container_width=True)
        else:
            st.info("Registra almeno 2 controlli peso per visualizzare la tabella dei progressi ponderali.")
    else:
        st.info("Nessun paziente presente.")

# -------------------------------------------------------------------------------------------------
# 5. CALENDARIO
# -------------------------------------------------------------------------------------------------
elif scelta_menu == "📅 Calendario & Visite":
    st.subheader("🗓️ Agenda Appuntamenti & Calendario Studio")
    st.caption("Sincronizzato in tempo reale con rodolfocasa22@gmail.com con avvisi a -30, -10 e -5 giorni.")
    
    res_scad = supabase.table("scadenze").select("id, titolo, data_scadenza, categoria, google_event_id, pazienti(nome, cognome, telefono)").order("data_scadenza").execute()
    eventi_db = res_scad.data or []

    c_ins, c_cal_view = st.columns([1.1, 2.5])
    with c_ins:
        st.markdown("#### ➕ Pianifica Visita o Scadenza")
        res_p = supabase.table("pazienti").select("id, nome, cognome").order("cognome").execute()
        paz_map = {f"{p['cognome']} {p['nome']}": p['id'] for p in (res_p.data or [])}
        
        with st.form("form_ev_cal_modern", clear_on_submit=True):
            paz_c = st.selectbox("Paziente collegato:", ["-- Scadenza Generale Studio --"] + list(paz_map.keys()))
            tit = st.text_input("Oggetto / Tipo Visita", placeholder="Es: Prima Visita, Controllo Mensile...")
            col_d, col_o = st.columns(2)
            with col_d: d_ev = st.date_input("Data Visita", value=date.today())
            with col_o: ora_ev = st.time_input("Orario", value=datetime.strptime("10:00", "%H:%M").time())
            cat = st.selectbox("Categoria", ["CONTROLLO_PAZIENTE", "PRIMA_VISITA", "SISTEMA_TS", "ENPAB", "ALTRO"])
            sync_g = st.checkbox("Sincronizza su Google Calendar (avvisi -30, -10, -5 gg)", value=True)
            
            if st.form_submit_button("Inserisci in Calendario", type="primary", use_container_width=True) and tit:
                p_id = paz_map[paz_c] if paz_c != "-- Scadenza Generale Studio --" else None
                nome_paz_str = f" - {paz_c}" if p_id else ""
                data_str = str(d_ev)
                g_event_id = None
                
                if sync_g:
                    g_event_id, _ = crea_evento_calendar(f"[{cat}] {tit}{nome_paz_str}", data_str, f"Orario: {ora_ev}")
                
                supabase.table("scadenze").insert({
                    "titolo": f"{tit}{nome_paz_str}", "data_scadenza": data_str, "categoria": cat, "paziente_id": p_id, "google_event_id": g_event_id
                }).execute()
                st.success("Registrato!")
                st.rerun()

        st.markdown("---")
        st.markdown("#### 🗑️ Gestione / Cancella Appuntamenti")
        if eventi_db:
            opzioni_canc_cal = {f"{ev['data_scadenza']} | {ev['titolo']}": ev for ev in eventi_db}
            sel_canc = st.selectbox("Seleziona evento da gestire:", list(opzioni_canc_cal.keys()))
            ev_da_eliminare = opzioni_canc_cal[sel_canc]
            
            c_btn_del, c_btn_wa_cal = st.columns(2)
            with c_btn_del:
                if st.button("🗑️ Elimina", use_container_width=True):
                    if ev_da_eliminare.get("google_event_id"):
                        elimina_evento_calendar(ev_da_eliminare["google_event_id"])
                    supabase.table("scadenze").delete().eq("id", ev_da_eliminare["id"]).execute()
                    st.success("Evento rimosso!")
                    st.rerun()
            
            with c_btn_wa_cal:
                pz_info = ev_da_eliminare.get("pazienti")
                if pz_info and pz_info.get("telefono"):
                    tel_w = str(pz_info['telefono']).replace(" ", "").replace("+", "")
                    txt_w = f"Gentile {pz_info['nome']}, le ricordo l'appuntamento per {ev_da_eliminare['titolo']} fissato per il {ev_da_eliminare['data_scadenza']}. Dott. Rodolfo Casa"
                    st.link_button("📲 WhatsApp", f"https://wa.me/{tel_w}?text={urllib.parse.quote(txt_w)}", use_container_width=True)
        else:
            st.info("Nessun appuntamento da gestire.")

    with c_cal_view:
        color_map = {"PRIMA_VISITA": "#10B981", "CONTROLLO_PAZIENTE": "#2563EB", "SISTEMA_TS": "#EF4444", "ENPAB": "#F59E0B", "ALTRO": "#6B7280"}
        eventi_fc = []
        for x in eventi_db:
            colore = color_map.get(x.get("categoria"), "#2563EB")
            pz = x.get("pazienti")
            nome_paz = f" ({pz['cognome']} {pz['nome']})" if pz else ""
            eventi_fc.append({"title": f"{x['titolo']}{nome_paz}", "start": x["data_scadenza"], "color": colore, "allDay": True})
        
        eventi_json = json.dumps(eventi_fc)
        data_iniziale = date.today().strftime("%Y-%m-%d")

        html_calendar = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset='utf-8' />
            <link href='https://cdn.jsdelivr.net/npm/fullcalendar@5.11.3/main.min.css' rel='stylesheet' />
            <script src='https://cdn.jsdelivr.net/npm/fullcalendar@5.11.3/main.min.js'></script>
            <script src='https://cdn.jsdelivr.net/npm/fullcalendar@5.11.3/locales/it.js'></script>
            <style>
                body {{ font-family: sans-serif; margin: 0; padding: 0; background: #fff; }}
                #calendar {{ max-width: 100%; margin: 0 auto; padding: 6px; }}
                .fc-toolbar-title {{ font-size: 1.25rem !important; font-weight: 700; color: #1E293B; }}
                .fc-button-primary {{ background-color: #2563EB !important; border: none !important; }}
                .fc-event {{ cursor: pointer; border-radius: 4px; padding: 2px 4px; font-size: 0.85rem; border: none; }}
            </style>
        </head>
        <body>
            <div id='calendar'></div>
            <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    var calendarEl = document.getElementById('calendar');
                    var calendar = new FullCalendar.Calendar(calendarEl, {{
                        locale: 'it', initialView: 'dayGridMonth', initialDate: '{data_iniziale}',
                        headerToolbar: {{ left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek' }},
                        buttonText: {{ today: 'Oggi', month: 'Mese', week: 'Settimana' }},
                        events: {eventi_json}
                    }});
                    calendar.render();
                }});
            </script>
        </body>
        </html>
        """
        components.html(html_calendar, height=560, scrolling=False)

# -------------------------------------------------------------------------------------------------
# 6. RESOCONTO ECONOMICO & FATTURAZIONE SANITARIA
# -------------------------------------------------------------------------------------------------
elif scelta_menu == "💶 Resoconto & Fatturazione Sanitaria":
    st.subheader("Bilancio Studio & Gestione Fatture Sanitarie")
    tab_registro, tab_fattura, tab_sts = st.tabs(["📊 Registro Movimenti & Bilancio", "🧾 Emetti Fattura Sanitaria PDF", "🏛️ Export Tracciato Sistema TS"])

    with tab_fattura:
        st.markdown("#### 🧾 Generatore Fattura Sanitaria Professionale")
        res_p = supabase.table("pazienti").select("*").order("cognome").execute()
        pazienti_list = res_p.data or []
        
        if not pazienti_list:
            st.warning("Inserisci prima un paziente.")
        else:
            mappa_fat = {f"{p['cognome']} {p['nome']} (CF: {p.get('codice_fiscale') or 'N/D'})": p for p in pazienti_list}
            paz_fat_str = st.selectbox("Intesta Fattura a:", list(mappa_fat.keys()))
            paz_fat = mappa_fat[paz_fat_str]

            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1: num_fat = st.text_input("Numero Fattura", value=f"FAT-{date.today().year}-001")
            with c_f2: data_fat = st.date_input("Data Emissione", value=date.today())
            with c_f3: metodo_pag = st.selectbox("Metodo Pagamento", ["Bonifico Bancario", "POS / Carta di Debito", "Contanti"])

            desc_prestazione = st.text_input("Descrizione Prestazione Sanitaria", value="Consulenza e valutazione nutrizionale con piano alimentare personalizzato")
            onorario_base = st.number_input("Onorario Base Prestazione (€)", min_value=10.0, value=100.0, step=5.0)

            rivalsa_enpab = onorario_base * 0.04
            imponibile_totale = onorario_base + rivalsa_enpab
            marca_da_bollo = 2.00 if imponibile_totale > 77.47 else 0.00
            totale_da_pagare = imponibile_totale + marca_da_bollo

            st.markdown("---")
            m_f1, m_f2, m_f3, m_f4 = st.columns(4)
            m_f1.metric("Onorario Base", f"€ {onorario_base:.2f}")
            m_f2.metric("ENPAB (4%)", f"€ {rivalsa_enpab:.2f}")
            m_f3.metric("Marca da Bollo", f"€ {marca_da_bollo:.2f}")
            m_f4.metric("Totale Fattura", f"€ {totale_da_pagare:.2f}")

            class PDFFattura(FPDF):
                def header(self):
                    self.set_font('Helvetica', 'B', 14)
                    self.cell(self.epw, 6, "STUDIO DI NUTRIZIONE CLINICA", align='L', new_x="LMARGIN", new_y="NEXT")
                    self.set_font('Helvetica', '', 8.5)
                    self.cell(self.epw, 4, "Biologo Nutrizionista | Ricevuta Sanitaria Tracciabile", align='L', new_x="LMARGIN", new_y="NEXT")
                    self.ln(6)
                def footer(self):
                    self.set_y(-12)
                    self.set_font('Helvetica', 'I', 8)
                    self.cell(self.epw, 10, f'Pagina {self.page_no()}', align='C')

            def crea_pdf_fattura():
                pdf = PDFFattura()
                pdf.add_page()
                w_utile = pdf.epw

                pdf.set_font("Helvetica", "B", 12)
                pdf.cell(w_utile, 7, f"FATTURA SANITARIA N. {num_fat} del {data_fat.strftime('%d/%m/%Y')}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(w_utile, 5, "DATI DEL CLIENTE / PAZIENTE:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(w_utile, 5, f"Nome e Cognome: {paz_fat['cognome']} {paz_fat['nome']}", new_x="LMARGIN", new_y="NEXT")
                pdf.cell(w_utile, 5, f"Codice Fiscale: {paz_fat.get('codice_fiscale') or 'N/D'}", new_x="LMARGIN", new_y="NEXT")
                pdf.cell(w_utile, 5, f"Modalita' Pagamento: {metodo_pag}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(6)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_fill_color(240, 240, 240)
                pdf.cell(w_utile * 0.75, 6, "  Descrizione Prestazione", border=1, fill=True)
                pdf.cell(w_utile * 0.25, 6, "Importo", border=1, fill=True, align='R', new_x="LMARGIN", new_y="NEXT")

                pdf.set_font("Helvetica", "", 9)
                pdf.cell(w_utile * 0.75, 6, f"  {desc_prestazione}", border=1)
                pdf.cell(w_utile * 0.25, 6, f"E {onorario_base:.2f}  ", border=1, align='R', new_x="LMARGIN", new_y="NEXT")
                pdf.cell(w_utile * 0.75, 6, "  Contributo Integrativo ENPAB (4%)", border=1)
                pdf.cell(w_utile * 0.25, 6, f"E {rivalsa_enpab:.2f}  ", border=1, align='R', new_x="LMARGIN", new_y="NEXT")
                if marca_da_bollo > 0:
                    pdf.cell(w_utile * 0.75, 6, "  Imposta di bollo assolta sull'originale (D.M. 17/06/2014)", border=1)
                    pdf.cell(w_utile * 0.25, 6, f"E {marca_da_bollo:.2f}  ", border=1, align='R', new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(w_utile * 0.75, 7, "  TOTALE DOVUTO", border=1, fill=True)
                pdf.cell(w_utile * 0.25, 7, f"E {totale_da_pagare:.2f}  ", border=1, fill=True, align='R', new_x="LMARGIN", new_y="NEXT")
                pdf.ln(6)
                pdf.set_font("Helvetica", "I", 8)
                pdf.multi_cell(w_utile, 4, "Operazione esente da IVA ai sensi dell'art. 10, comma 1, n. 18 del D.P.R. 633/1972. Spesa sanitaria detraibile con pagamento tracciabile.", new_x="LMARGIN", new_y="NEXT")
                return bytes(pdf.output())

            col_btn_f1, col_btn_f2 = st.columns([1.5, 2])
            with col_btn_f1:
                st.download_button("📥 Scarica Fattura Sanitaria (PDF)", crea_pdf_fattura(), file_name=f"Fattura_{num_fat}_{paz_fat['cognome']}.pdf", mime="application/pdf", type="primary", use_container_width=True)
            with col_btn_f2:
                if st.button("💾 Registra Incasso nel Registro Economico", use_container_width=True):
                    try:
                        supabase.table("movimenti_fiscali").insert({
                            "descrizione": f"Fattura {num_fat} - {paz_fat['cognome']} {paz_fat['nome']} (CF: {paz_fat.get('codice_fiscale')})",
                            "importo": totale_da_pagare,
                            "tipo": "ENTRATA",
                            "data": str(data_fat),
                            "metodo": metodo_pag
                        }).execute()
                        st.success("Fattura archiviata nel registro delle entrate!")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Errore registrazione: {err}")

    with tab_sts:
        st.markdown("#### 🏛️ Generatore Tracciato Sistema Tessera Sanitaria (MEF)")
        try:
            res_sts = supabase.table("movimenti_fiscali").select("*").filter("tipo", "eq", "ENTRATA").order("data").execute()
            mov_entrate = res_sts.data or []
        except Exception: mov_entrate = []

        if mov_entrate:
            righe_sts = []
            for e in mov_entrate:
                cf_estratto = "NON INDICATO"
                if "CF:" in e["descrizione"]:
                    cf_estratto = e["descrizione"].split("CF:")[1].replace(")", "").strip()
                righe_sts.append({
                    "Data Emissione": e["data"],
                    "Numero Fattura / Descrizione": e["descrizione"],
                    "Codice Fiscale Paziente": cf_estratto,
                    "Importo Totale (€)": e["importo"],
                    "Pagamento Tracciato": "Sì" if e.get("metodo") != "Contanti" else "No",
                    "Tipo Spesa": "SP (Spesa Sanitaria)"
                })
            df_sts = pd.DataFrame(righe_sts)
            st.dataframe(df_sts, use_container_width=True)
            st.download_button("📥 Scarica Tracciato Spese Sistema TS (CSV)", df_sts.to_csv(index=False).encode('utf-8'), file_name=f"Tracciato_Sistema_TS_{date.today().year}.csv", mime="text/csv", type="primary")
        else:
            st.info("Nessuna fattura emessa registrata.")

    with tab_registro:
        c_form, c_metriche = st.columns([1.1, 2.3])
        with c_form:
            st.markdown("#### ➕ Registra Spesa / Entrata Manuale")
            with st.form("form_trans_manuale", clear_on_submit=True):
                tipo = st.selectbox("Tipologia", ["Incasso Visita (Entrata)", "Spesa Studio Deducibile (Uscita)"])
                desc = st.text_input("Descrizione", placeholder="Es: Quota Ordine, Software, Carta lettino...")
                val = st.number_input("Importo (€)", min_value=1.0, value=90.0, step=5.0)
                data_m = st.date_input("Data Movimento", value=date.today())
                met = st.selectbox("Metodo Pagamento", ["POS / Carta", "Bonifico Bancario", "Contanti"])
                if st.form_submit_button("Salva Movimento", type="primary"):
                    is_e = "Entrata" in tipo
                    try:
                        supabase.table("movimenti_fiscali").insert({
                            "descrizione": desc, "importo": val if is_e else -val,
                            "tipo": "ENTRATA" if is_e else "USCITA", "data": str(data_m), "metodo": met
                        }).execute()
                        st.success("Registrato!")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Errore: {err}")

        with c_metriche:
            movs = []
            try:
                res_m = supabase.table("movimenti_fiscali").select("*").order("data", desc=True).execute()
                movs = res_m.data or []
            except Exception: movs = []
                
            if movs:
                df_m = pd.DataFrame(movs)
                tot_in = df_m[df_m["importo"] > 0]["importo"].sum()
                tot_out = abs(df_m[df_m["importo"] < 0]["importo"].sum())
                utile = tot_in - tot_out
                enpab = tot_in * 0.04
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Totale Incassi", f"€ {tot_in:,.2f}")
                m2.metric("Spese Totali", f"€ {tot_out:,.2f}")
                m3.metric("Utile Netto", f"€ {utile:,.2f}")
                m4.metric("Rivalsa ENPAB (4%)", f"€ {enpab:,.2f}")
                st.markdown("---")
                st.markdown("#### 📋 Registro Movimenti")
                for m in movs:
                    c_d, c_desc, c_imp, c_met, c_canc = st.columns([1.3, 3, 1.3, 1.8, 1])
                    c_d.write(f"📅 `{m['data']}`")
                    c_desc.write(f"**{m['descrizione']}**")
                    colore_imp = "green" if m["importo"] > 0 else "red"
                    c_imp.markdown(f"<span style='color:{colore_imp}; font-weight:700;'>€ {float(m['importo']):.2f}</span>", unsafe_allow_html=True)
                    c_met.write(f"_{m.get('metodo') or 'N/D'}_")
                    if c_canc.button("🗑️", key=f"del_mov_{m['id']}", help="Elimina"):
                        supabase.table("movimenti_fiscali").delete().eq("id", m["id"]).execute()
                        st.success("Eliminato!")
                        st.rerun()
            else:
                st.info("Nessun movimento presente nel registro.")

# -------------------------------------------------------------------------------------------------
# 7. BACKUP & DISASTER RECOVERY
# -------------------------------------------------------------------------------------------------
elif scelta_menu == "💾 Backup & Dati Studio":
    st.subheader("💾 Backup Completo Studio & Portabilità Dati (GDPR)")
    st.caption("Estrae una copia di sicurezza integrale di tutte le tabelle del gestionale in formato JSON/Excel compresso in un archivio ZIP.")

    def genera_archivio_backup():
        buffer_zip = io.BytesIO()
        tabelle = [
            "pazienti", "diete", "voci_dieta", "alimenti", "misure_pazienti", 
            "esami_laboratorio", "scadenze", "movimenti_fiscali", 
            "template_diete", "template_voci_dieta"
        ]
        
        with zipfile.ZipFile(buffer_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for tab in tabelle:
                try:
                    res_t = supabase.table(tab).select("*").execute()
                    dati_tab = res_t.data or []
                    
                    json_str = json.dumps(dati_tab, indent=2, default=str)
                    zf.writestr(f"{tab}.json", json_str)
                    
                    if dati_tab:
                        df_tab = pd.DataFrame(dati_tab)
                        csv_str = df_tab.to_csv(index=False)
                        zf.writestr(f"{tab}.csv", csv_str)
                except Exception as err:
                    zf.writestr(f"{tab}_errore.txt", str(err))

        buffer_zip.seek(0)
        return buffer_zip.getvalue()

    col_bk1, col_bk2 = st.columns([1.5, 2])
    with col_bk1:
        st.write("")
        st.download_button(
            label="📦 Scarica Archivio Backup Completo (.ZIP)",
            data=genera_archivio_backup(),
            file_name=f"Backup_Studio_Nutrizione_{date.today().strftime('%Y%m%d')}.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )
    with col_bk2:
        st.info("L'archivio ZIP include sia i file JSON completi per il ripristino tecnico sia i file CSV compatibili con Microsoft Excel / Google Sheets.")
