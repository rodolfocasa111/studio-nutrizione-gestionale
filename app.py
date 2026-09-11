import streamlit as st
from supabase import create_client, Client
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF

# Configurazione della pagina
st.set_page_config(
    page_title="Studio Nutrizione - Gestionale",
    page_icon="🥗",
    layout="wide"
)

# Inizializzazione connessione Supabase dai secrets di Streamlit
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase: Client = init_connection()

# --- BARRA LATERALE (LOGO E AUTENTICAZIONE) ---
with st.sidebar:
    try:
        # Inserimento del logo personalizzato
        st.image("logo.png", use_container_width=True)
    except Exception:
        pass
    
    st.markdown("### Dott. Rodolfo Casa")
    st.markdown("*Biologo Nutrizionista*")
    st.markdown("---")
    
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.subheader("Login Amministratore")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Accedi"):
            if username == st.secrets["auth"]["admin_user"] and password == st.secrets["auth"]["admin_password"]:
                st.session_state.authenticated = True
                st.success("Accesso effettuato!")
                st.rerun()
            else:
                st.error("Credenziali non valide")
    else:
        st.success("Area Amministrativa Attiva")
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

# --- CORPO PRINCIPALE ---
st.title("Gestionale Studio di Nutrizione")

# Funzione per recuperare i pazienti da Supabase
def get_pazienti():
    try:
        response = supabase.table("pazienti").select("*").execute()
        return response.data
    except Exception:
        return []

if not st.session_state.authenticated:
    st.info("Area di consultazione rapida per i pazienti.")
    cf_cercato = st.text_input("Inserisci il Codice Fiscale del Paziente:")
    if cf_cercato:
        response = supabase.table("pazienti").select("*").eq("codice_fiscale", cf_cercato.upper()).execute()
        if response.data:
            st.success("Paziente trovato!")
            st.dataframe(pd.DataFrame(response.data))
        else:
            st.warning("Nessun paziente trovato con questo Codice Fiscale.")
else:
    # Sezione amministrativa completa
    tab1, tab2, tab3 = st.tabs(["Gestione Pazienti", "Nuova Visita", "Statistiche & Report"])
    
    with tab1:
        st.subheader("Anagrafica Pazienti")
        pazienti_list = get_pazienti()
        if pazienti_list:
            df_pazienti = pd.DataFrame(pazienti_list)
            st.dataframe(df_pazienti, use_container_width=True)
        else:
            st.info("Nessun paziente registrato nel database.")
            
        with st.form("nuovo_paziente_form"):
            st.subheader("Aggiungi Nuovo Paziente")
            nome = st.text_input("Nome e Cognome")
            cf = st.text_input("Codice Fiscale")
            email = st.text_input("Email")
            telefono = st.text_input("Telefono")
            submit_paziente = st.form_submit_button("Salva Paziente")
            
            if submit_paziente and nome and cf:
                try:
                    supabase.table("pazienti").insert({
                        "nome": nome, 
                        "codice_fiscale": cf.upper(), 
                        "email": email, 
                        "telefono": telefono
                    }).execute()
                    st.success(f"Paziente {nome} aggiunto con successo!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")

    with tab2:
        st.subheader("Registrazione Visita e Antropometria")
        pazienti_list = get_pazienti()
        if pazienti_list:
            nomi_pazienti = {p["nome"]: p["id"] for p in pazienti_list}
            paziente_scelto = st.selectbox("Seleziona Paziente", list(nomi_pazienti.keys()))
            
            col1, col2 = st.columns(2)
            with col1:
                peso = st.number_input("Peso (kg)", min_value=30.0, max_value=250.0, step=0.1)
                altezza = st.number_input("Altezza (cm)", min_value=100.0, max_value=230.0, step=0.1)
            with col2:
                circonferenza_vita = st.number_input("Circonferenza Vita (cm)", min_value=40.0, max_value=200.0, step=0.1)
                note_visita = st.text_area("Note sulla visita o piano alimentare")
                
            if st.button("Salva Visita"):
                paziente_id = nomi_pazienti[paziente_scelto]
                try:
                    supabase.table("visite").insert({
                        "paziente_id": paziente_id,
                        "peso": peso,
                        "altezza": altezza,
                        "circonferenza_vita": circonferenza_vita,
                        "note": note_visita
                    }).execute()
                    st.success("Visita salvata correttamente!")
                except Exception as e:
                    st.error(f"Errore nel salvataggio della visita: {e}")
        else:
            st.warning("Inserisci prima almeno un paziente nella sezione 'Gestione Pazienti'.")

    with tab3:
        st.subheader("Statistiche e Andamento Studio")
        st.write("Qui puoi monitorare i dati generali e le metriche dello studio nutrizionale.")
        # Spazio per grafici riepilogativi con matplotlib o metriche streamlit
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="Totale Pazienti", value=len(get_pazienti()))
        with col2:
            st.metric(label="Stato Sistema", value="Online su Cloud")
