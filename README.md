# Studio Nutrizione – Gestionale

App Streamlit (Supabase + Google Calendar + Gemini) per la gestione di pazienti, diete, misure, fatture e backup.

## Configurazione

1. Copia `.streamlit/secrets.toml.example` in `.streamlit/secrets.toml` (o incolla il contenuto nei Secrets di Streamlit Cloud) e compila i valori.
   **Nessun valore ha un default nel codice**: se mancano `supabase.url`, `supabase.key`, `auth.admin_user`, `auth.admin_password` l'app non parte.
2. Esegui `db/migrazione_sicurezza.sql` nel SQL Editor di Supabase (colonna PIN, CF univoco, Row Level Security).
   Dopo aver attivato la RLS l'app deve usare la chiave **service_role** (solo nei secrets, mai nel repository).
3. Imposta un PIN per ogni paziente (cartella clinica → «PIN di accesso»). Quando tutti lo hanno, metti
   `consenti_accesso_senza_pin = false` nei secrets.
4. Se le vecchie credenziali (chiave Supabase, password admin `Studio2026!`) sono mai state pubbliche, **ruotale**: restano nella cronologia git.

## Sviluppo

```
pip install -r requirements.txt pytest pyflakes
streamlit run app.py
pytest -q
```

`logic.py` contiene la logica pura (CF, fatture, BMR, paginazione…) ed è coperta da `tests/test_logic.py`;
`tests/test_app_smoke.py` esegue l'app con Streamlit `AppTest` e un Supabase simulato.
