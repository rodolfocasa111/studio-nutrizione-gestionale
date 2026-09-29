-- Migrazione di sicurezza per Studio Nutrizione Gestionale
-- Eseguire nel SQL Editor di Supabase. Fare PRIMA un backup (menu "Backup & Dati Studio").

-- 1) PIN di accesso dei pazienti (hash PBKDF2 calcolato dall'app, mai il PIN in chiaro)
ALTER TABLE pazienti ADD COLUMN IF NOT EXISTS pin_accesso text;

-- 2) Codice fiscale univoco (ignora i valori vuoti/NULL).
--    Se il comando fallisce esistono CF duplicati: correggerli prima da "Pazienti".
--    Verifica: SELECT codice_fiscale, count(*) FROM pazienti GROUP BY 1 HAVING count(*) > 1;
UPDATE pazienti SET codice_fiscale = upper(trim(codice_fiscale)) WHERE codice_fiscale IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS pazienti_cf_unico
    ON pazienti (codice_fiscale) WHERE codice_fiscale IS NOT NULL AND codice_fiscale <> '';

-- 3) Row Level Security: nessuna policy = la chiave "anon/publishable" NON puo' leggere ne' scrivere nulla.
--    L'app deve usare la chiave service_role (solo nei secrets lato server, MAI nel repository).
ALTER TABLE pazienti              ENABLE ROW LEVEL SECURITY;
ALTER TABLE diete                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE voci_dieta            ENABLE ROW LEVEL SECURITY;
ALTER TABLE alimenti              ENABLE ROW LEVEL SECURITY;
ALTER TABLE misure_pazienti       ENABLE ROW LEVEL SECURITY;
ALTER TABLE esami_laboratorio     ENABLE ROW LEVEL SECURITY;
ALTER TABLE scadenze              ENABLE ROW LEVEL SECURITY;
ALTER TABLE movimenti_fiscali     ENABLE ROW LEVEL SECURITY;
ALTER TABLE template_diete        ENABLE ROW LEVEL SECURITY;
ALTER TABLE template_voci_dieta   ENABLE ROW LEVEL SECURITY;

-- Se le tabelle hanno gia' policy permissive per "anon", rimuoverle:
--   SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public';
--   DROP POLICY "<nome>" ON <tabella>;

-- 4) Facoltativo ma consigliato: chiavi esterne senza CASCADE sulle voci di dieta, cosi' un alimento
--    in uso non puo' essere cancellato (l'app lo controlla comunque).
--   ALTER TABLE voci_dieta DROP CONSTRAINT IF EXISTS voci_dieta_alimento_id_fkey;
--   ALTER TABLE voci_dieta ADD CONSTRAINT voci_dieta_alimento_id_fkey
--       FOREIGN KEY (alimento_id) REFERENCES alimenti(id) ON DELETE RESTRICT;
