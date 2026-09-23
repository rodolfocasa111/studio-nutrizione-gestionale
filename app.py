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
import pypdf

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
GEMINI_API_KEY = str(get_secret("gemini", "api_key", "")).strip()

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

ADMIN_USER = str(get_secret("auth", "admin_user", "dott.casa")).strip().lower()
ADMIN_PWD = str(get_secret("auth", "admin_password", "Studio2026!")).strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
if not os.path.exists(CREDENTIALS_FILE):
    CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json.json")

st.set_page_config(page_title="Studio Nutrizionale", layout="wide", initial_sidebar_state="collapsed")

# Stile CSS Interfaccia Professionale Avanzato
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
# 2. PIANO SETTIMANALE & TEMPLATE CON INTEGRAZIONE GEMINI
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
                nome_gen_tpl = st.text_input("Nome per il nuovo Template AI:", placeholder="Es: Dieta da File")
                
                if st.button("🤖 Estrai e Crea Template con AI", type="primary"):
                    if uploaded_file and nome_gen_tpl.strip():
                        with st.spinner("Gemini sta analizzando il file..."):
                            try:
                                testo_file = ""
                                if uploaded_file.name.endswith('.txt'):
                                    testo_file = uploaded_file.read().decode("utf-8", errors="ignore")
                                elif uploaded_file.name.endswith('.pdf'):
                                    reader = pypdf.PdfReader(uploaded_file)
                                    for page in reader.pages:
                                        testo_file += page.extract_text() or ""
                                else:
                                    testo_file = str(uploaded_file.read())

                                if not testo_file.strip():
                                    st.error("Il file risulta vuoto o non leggibile.")
                                else:
                                    model = genai.GenerativeModel('gemini-1.5-flash')
                                    prompt_ia = (
                                        "Analizza il seguente testo estratto da un piano alimentare. "
                                        "Estrai i giorni della settimana (Lunedì, Martedì, Mercoledì, Giovedì, Venerdì, Sabato, Domenica), "
                                        "i pasti (Colazione, Spuntino Mattina, Pranzo, Merenda Pomeriggio, Cena) e gli alimenti con le rispettive grammature. "
                                        "Restituisci ESCLUSIVAMENTE un oggetto JSON valido con questa struttura esatta:\n"
                                        "[\n  {\"giorno\": \"Lunedì\", \"pasto\": \"Pranzo\", \"alimento\": \"Nome Alimento\", \"grammi\": 100},\n...\n]\n\n"
                                        f"TESTO DEL PIANO:\n{testo_file[:15000]}"
                                    )
                                    
                                    response = model.generate_content(prompt_ia)
                                    raw_text = response.text.strip()
                                    
                                    if "```json" in raw_text:
                                        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                                    elif "```" in raw_text:
                                        raw_text = raw_text.split("
