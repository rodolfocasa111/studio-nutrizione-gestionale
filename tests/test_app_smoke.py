"""Test di fumo dell'app con Streamlit AppTest e un Supabase simulato in memoria."""
import os
import sys
import types
import pytest

pytest.importorskip("streamlit")
pytest.importorskip("fpdf")
pytest.importorskip("pypdf")
pytest.importorskip("googleapiclient")
pytest.importorskip("google.genai")
from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")

CF = "RSSMRA80A01H501U"


class Resp:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.rows = db[name]
        self.op, self.payload, self.filters, self._range, self._count = "select", None, [], None, None
        self._order = None

    def select(self, cols="*", count=None): self._count = count; return self
    def eq(self, c, v): self.filters.append((c, lambda x, v=v: x == v)); return self
    def in_(self, c, vals): self.filters.append((c, lambda x, vals=vals: x in vals)); return self
    def order(self, c, desc=False): self._order = (c, desc); return self
    def limit(self, n): return self
    def range(self, a, b): self._range = (a, b); return self
    def insert(self, p): self.op, self.payload = "insert", p; return self
    def update(self, p): self.op, self.payload = "update", p; return self
    def delete(self): self.op = "delete"; return self
    def filter(self, c, op, v): return self.eq(c, v)

    def _match(self):
        return [r for r in self.rows if all(f(r.get(c)) for c, f in self.filters)]

    def execute(self):
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", len(self.rows) + 1 + len(out) + 100 * hash(self.name) % 1000)
                self.rows.append(it); out.append(it)
            return Resp(out)
        if self.op == "update":
            m = self._match()
            for r in m: r.update(self.payload)
            return Resp(m)
        if self.op == "delete":
            m = self._match()
            self.db[self.name][:] = [r for r in self.rows if r not in m]
            return Resp(m)
        m = self._match()
        if self._order:
            m = sorted(m, key=lambda r: (r.get(self._order[0]) is None, r.get(self._order[0])), reverse=self._order[1])
        if self._range:
            m = m[self._range[0]:self._range[1] + 1]
        if self.name == "voci_dieta":  # join simulato
            m = [{**r, "alimenti": next((a for a in self.db["alimenti"] if a["id"] == r["alimento_id"]), None)} for r in m]
        if self.name == "scadenze":
            m = [{**r, "pazienti": next((p for p in self.db["pazienti"] if p["id"] == r.get("paziente_id")), None)} for r in m]
        return Resp(m, count=len(m))


class FakeClient:
    def __init__(self):
        self.db = {n: [] for n in ["pazienti", "diete", "voci_dieta", "alimenti", "misure_pazienti", "esami_laboratorio",
                                   "scadenze", "movimenti_fiscali", "template_diete", "template_voci_dieta"]}
    def table(self, n): return Query(self.db, n)


@pytest.fixture
def fake(monkeypatch):
    import streamlit as st
    st.cache_resource.clear(); st.cache_data.clear()  # il client e il registro tentativi sono in cache di processo
    client = FakeClient()
    client.db["pazienti"].append({"id": 1, "nome": "Mario", "cognome": "Rossi", "codice_fiscale": CF, "telefono": "340 1234567",
                                  "email": "m@x.it", "data_nascita": "1980-01-01", "obiettivo_clinico": "Mantenimento / Rieducazione"})
    client.db["alimenti"] += [
        {"id": 1, "nome": "Pasta di semola", "energia_kcal": 350, "proteine_g": 12, "carboidrati_g": 72, "lipidi_g": 1.5, "fibra_g": 3, "categoria": "Cereali"},
        {"id": 2, "nome": "Petto di pollo <b>", "energia_kcal": 110, "proteine_g": 23, "carboidrati_g": 0, "lipidi_g": 1.5, "fibra_g": 0, "categoria": "Carne"},
    ]
    client.db["diete"].append({"id": 1, "paziente_id": 1, "titolo": "Piano", "target_kcal": 2000})
    client.db["voci_dieta"].append({"id": 1, "dieta_id": 1, "giorno_settimana": "Lunedì", "pasto": "Pranzo", "alimento_id": 1, "grammi": 80})
    client.db["misure_pazienti"] += [
        {"id": 1, "paziente_id": 1, "data_rilevazione": "2026-01-10", "peso_kg": 80, "circ_vita_cm": 90, "circ_fianchi_cm": 100},
        {"id": 2, "paziente_id": 1, "data_rilevazione": "2026-03-10", "peso_kg": 77, "circ_vita_cm": 88, "circ_fianchi_cm": 99},
    ]
    mod = types.ModuleType("supabase")
    mod.create_client = lambda url, key: client
    mod.Client = object
    monkeypatch.setitem(sys.modules, "supabase", mod)
    monkeypatch.syspath_prepend(ROOT)
    return client


SECRETS = {"supabase": {"url": "http://x", "key": "k"}, "auth": {"admin_user": "dott", "admin_password": "Segreta!1"}}


def nuova_app(monkeypatch, secrets=SECRETS):
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets.clear()
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    return at


def test_senza_secret_non_parte(fake, monkeypatch):
    at = nuova_app(monkeypatch, secrets={}).run()
    assert any("Configurazione incompleta" in e.value for e in at.error)


def login_admin(at, user="dott", pwd="Segreta!1"):
    ti = [w for w in at.text_input if w.label in ("Nome Utente", "Password")]
    ti[0].set_value(user); ti[1].set_value(pwd)
    [b for b in at.button if "Accedi al Gestionale" in b.label][0].click()
    return at.run()


def test_admin_login_errato_e_blocco(fake, monkeypatch):
    at = nuova_app(monkeypatch).run()
    for _ in range(5):
        at = login_admin(at, pwd="sbagliata")
    assert any("non valide" in e.value or "Troppi" in e.value for e in at.error)
    at = login_admin(at)  # anche la password giusta e' bloccata dopo 5 fallimenti
    assert any("Troppi tentativi" in e.value for e in at.error)
    assert at.session_state["autenticato"] is False


def test_admin_navigazione_completa(fake, monkeypatch):
    at = nuova_app(monkeypatch).run()
    at = login_admin(at)
    assert at.session_state["ruolo"] == "admin"
    assert not at.exception
    radio = at.radio[0]
    for voce in radio.options:
        radio.set_value(voce)
        at = at.run()
        assert not at.exception, f"eccezione in '{voce}': {[e.value for e in at.exception]}"
        radio = at.radio[0]


def test_paziente_login_e_pin(fake, monkeypatch):
    import logic
    fake.db["pazienti"][0]["pin_accesso"] = logic.hash_pin("4321", CF)
    at = nuova_app(monkeypatch).run()

    def prova(cf, pin):
        campi = {w.label: w for w in at.text_input}
        campi["Codice Fiscale"].set_value(cf); campi["PIN di accesso"].set_value(pin)
        [b for b in at.button if "Accedi al Tuo Portale" in b.label][0].click()
        return at.run()

    at = prova(CF, "0000")
    assert at.session_state["autenticato"] is False
    at = prova(CF, "4321")
    assert at.session_state["ruolo"] == "paziente" and not at.exception
    assert "pin_accesso" not in at.session_state["dati_paziente"]


def test_cf_duplicato_rifiutato(fake, monkeypatch):
    fake.db["pazienti"].append({**fake.db["pazienti"][0], "id": 2, "nome": "Altro"})
    at = nuova_app(monkeypatch).run()
    campi = {w.label: w for w in at.text_input}
    campi["Codice Fiscale"].set_value(CF)
    [b for b in at.button if "Accedi al Tuo Portale" in b.label][0].click()
    at = at.run()
    assert at.session_state["autenticato"] is False


def test_paziente_senza_pin_bloccato_se_configurato(fake, monkeypatch):
    s = {**SECRETS, "auth": {**SECRETS["auth"], "consenti_accesso_senza_pin": False}}
    at = nuova_app(monkeypatch, s).run()
    campi = {w.label: w for w in at.text_input}
    campi["Codice Fiscale"].set_value(CF)
    [b for b in at.button if "Accedi al Tuo Portale" in b.label][0].click()
    at = at.run()
    assert at.session_state["autenticato"] is False


def vai(at, voce_parziale):
    radio = at.radio[0]
    voce = [o for o in radio.options if voce_parziale in o][0]
    radio.set_value(voce)
    return at.run()


def admin(monkeypatch):
    at = nuova_app(monkeypatch).run()
    return login_admin(at)


def clic(at, testo):
    [b for b in at.button if testo in b.label][0].click()
    return at.run()


def test_nuovo_paziente_validazioni(fake, monkeypatch):
    at = vai(admin(monkeypatch), "Pazienti")
    at.checkbox[0].set_value(True); at = at.run()

    def compila(cf):
        campi = {w.label: w for w in at.text_input}
        campi["Nome*"].set_value("Anna"); campi["Cognome*"].set_value("Verdi"); campi["Codice Fiscale*"].set_value(cf)

    compila("XYZ"); at = clic(at, "Salva Paziente")
    assert any("formato non valido" in e.value for e in at.error)
    assert len(fake.db["pazienti"]) == 1

    compila(CF.lower()); at = clic(at, "Salva Paziente")  # duplicato (case-insensitive)
    assert any("già un paziente" in e.value for e in at.error)
    assert len(fake.db["pazienti"]) == 1

    compila("VRDNNA85M41F205Z")
    [w for w in at.text_input if w.label.startswith("PIN")][0].set_value("1234")
    at = clic(at, "Salva Paziente")
    assert len(fake.db["pazienti"]) == 2
    nuovo = fake.db["pazienti"][1]
    assert nuovo["codice_fiscale"] == "VRDNNA85M41F205Z" and nuovo["pin_accesso"] != "1234" and len(nuovo["pin_accesso"]) == 64


def test_fattura_progressiva_e_niente_duplicati(fake, monkeypatch):
    at = vai(admin(monkeypatch), "Fatturazione")
    assert not at.exception
    assert [w for w in at.text_input if w.label.startswith("Numero Fattura")][0].value.endswith("-001")
    at = clic(at, "Registra Incasso")
    m = fake.db["movimenti_fiscali"]
    assert len(m) == 1 and m[0]["importo"] == 106.0 and "CF: " + CF in m[0]["descrizione"]
    at = vai(at, "Fatturazione")
    assert [w for w in at.text_input if w.label.startswith("Numero Fattura")][0].value.endswith("-002")
    # forzo lo stesso numero: deve essere bloccato
    [w for w in at.text_input if w.label.startswith("Numero Fattura")][0].set_value(m[0]["descrizione"].split()[1])
    at = at.run()
    assert any("già registrata" in e.value for e in at.error)
    assert [b for b in at.button if "Registra Incasso" in b.label][0].disabled


def test_calendario_senza_credenziali_avvisa(fake, monkeypatch):
    at = vai(admin(monkeypatch), "Calendario")
    [w for w in at.text_input if w.label.startswith("Oggetto")][0].set_value("Controllo")
    at = clic(at, "Inserisci in Calendario")
    assert len(fake.db["scadenze"]) == 1 and fake.db["scadenze"][0]["google_event_id"] is None
    assert any("NON sincronizzata" in w.value for w in at.warning)


def test_calendario_titolo_vuoto(fake, monkeypatch):
    at = vai(admin(monkeypatch), "Calendario")
    at = clic(at, "Inserisci in Calendario")
    assert any("oggetto" in e.value for e in at.error) and not fake.db["scadenze"]


def test_backup_su_richiesta(fake, monkeypatch):
    at = vai(admin(monkeypatch), "Backup")
    assert "_backup" not in at.session_state  # non si genera a ogni rerun
    at = clic(at, "Prepara Backup")
    dati, errori = at.session_state["_backup"]
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(dati))
    assert "pazienti.json" in z.namelist() and not errori


def test_pdf_con_caratteri_unicode(fake, monkeypatch):
    fake.db["alimenti"][0]["nome"] = "Pasta “integrale” – 100% ł €"
    fake.db["diete"][0]["note_integrazione"] = "Vitamina D – 1000 UI • € 5"
    at = nuova_app(monkeypatch).run()
    campi = {w.label: w for w in at.text_input}
    campi["Codice Fiscale"].set_value(CF)
    at = clic(at, "Accedi al Tuo Portale")
    assert at.session_state["ruolo"] == "paziente" and not at.exception
    assert len(at.get("download_button")) >= 1


def test_piano_aggiunta_alimento_e_pasti(fake, monkeypatch):
    at = vai(admin(monkeypatch), "Piano Settimanale")
    assert not at.exception
    at = clic(at, "Inserisci")
    assert len(fake.db["voci_dieta"]) == 2 and not at.exception


def test_applica_template_sostituisce_senza_perdite(fake, monkeypatch):
    fake.db["template_diete"].append({"id": 7, "nome": "Tipo", "target_kcal": 1800})
    fake.db["template_voci_dieta"] += [
        {"id": 1, "template_id": 7, "giorno_settimana": "Martedì", "pasto": "Cena", "alimento_id": 2, "grammi": 150},
        {"id": 2, "template_id": 7, "giorno_settimana": "Mercoledì", "pasto": "Pranzo", "alimento_id": 1, "grammi": 70},
    ]
    at = vai(admin(monkeypatch), "Piano Settimanale")
    at = clic(at, "Applica al Paziente")
    voci = fake.db["voci_dieta"]
    assert sorted((v["giorno_settimana"], v["grammi"]) for v in voci) == [("Martedì", 150), ("Mercoledì", 70)]


def test_template_vuoto_non_cancella_la_dieta(fake, monkeypatch):
    fake.db["template_diete"].append({"id": 7, "nome": "Vuoto", "target_kcal": 1800})
    at = vai(admin(monkeypatch), "Piano Settimanale")
    at = clic(at, "Applica al Paziente")
    assert len(fake.db["voci_dieta"]) == 1
    assert any("vuoto" in w.value for w in at.warning)
