"""Logica pura (senza Streamlit) dell'applicazione: testabile in isolamento."""
import hashlib
import hmac
import html
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from datetime import date, datetime

TZ_STUDIO = ZoneInfo("Europe/Rome")

# Codice fiscale: accetta anche i caratteri sostitutivi dell'omocodia (LMNPQRSTUV)
_CF_RE = re.compile(r"^[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-EHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]$")

OBIETTIVI_CLINICI = [
    "Dimagrimento / Ricomposizione", "Aumento Massa Muscolare",
    "Nutrizione Clinica / Patologie", "Mantenimento / Rieducazione",
]
PASTI = ["Colazione", "Spuntino Mattina", "Pranzo", "Merenda Pomeriggio", "Cena"]
GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

SOGLIA_BOLLO = Decimal("77.47")
IMPORTO_BOLLO = Decimal("2.00")
ALIQUOTA_ENPAB = Decimal("0.04")


def oggi() -> date:
    """Data odierna nel fuso dello studio (il server gira in UTC)."""
    return datetime.now(TZ_STUDIO).date()


def esc(valore) -> str:
    """Escape HTML per qualsiasi valore proveniente dal database."""
    return html.escape("" if valore is None else str(valore))


def json_per_script(obj) -> str:
    """JSON sicuro da incorporare dentro un tag <script> (impedisce '</script>')."""
    return json.dumps(obj).replace("</", "<\\/").replace("<!--", "<\\!--")


def normalizza_cf(cf: str) -> str:
    return (cf or "").strip().upper().replace(" ", "")


def cf_valido(cf: str) -> bool:
    return bool(_CF_RE.match(normalizza_cf(cf)))


def normalizza_telefono(raw) -> str:
    """Restituisce il numero in formato internazionale senza '+' (per wa.me)."""
    t = re.sub(r"[^\d+]", "", str(raw or ""))
    if not t:
        return ""
    if t.startswith("+"):
        return t[1:]
    if t.startswith("00"):
        return t[2:]
    if t.startswith("3"):  # cellulare italiano senza prefisso
        return "39" + t
    return t


def estrai_cf(descrizione: str) -> str:
    m = re.search(r"CF:\s*([A-Za-z0-9]{16})", descrizione or "")
    return m.group(1).upper() if m else "NON INDICATO"


def hash_pin(pin: str, cf: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), normalizza_cf(cf).encode(), 120_000).hex()


def verifica_pin(pin: str, cf: str, hash_salvato: str) -> bool:
    return hmac.compare_digest(hash_pin(pin, cf), hash_salvato or "")


def confronto_costante(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def calcola_bmr_tdee(sesso: str, peso_kg: float, altezza_cm: float, eta: int, molt_laf: float):
    """Mifflin-St Jeor. Restituisce (bmr, tdee, bmi)."""
    bmr = (10 * peso_kg) + (6.25 * altezza_cm) - (5 * eta) + (5 if sesso == "Maschio" else -161)
    bmi = peso_kg / ((altezza_cm / 100.0) ** 2)
    return bmr, bmr * molt_laf, bmi


def eta_da_data_nascita(data_nascita, riferimento: date = None):
    try:
        nato = date.fromisoformat(str(data_nascita)[:10])
    except (TypeError, ValueError):
        return None
    rif = riferimento or oggi()
    return rif.year - nato.year - ((rif.month, rif.day) < (nato.month, nato.day))


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcola_fattura(onorario) -> dict:
    """Onorario + rivalsa ENPAB 4% + bollo (se imponibile > 77,47 €). Importi arrotondati al centesimo."""
    base = _q(Decimal(str(onorario)))
    rivalsa = _q(base * ALIQUOTA_ENPAB)
    imponibile = base + rivalsa
    bollo = IMPORTO_BOLLO if imponibile > SOGLIA_BOLLO else Decimal("0.00")
    return {"onorario": base, "rivalsa": rivalsa, "imponibile": imponibile,
            "bollo": bollo, "totale": imponibile + bollo}


def enpab_contenuta_negli_incassi(totale_incassi: float) -> float:
    """Gli incassi da fattura includono già la rivalsa del 4%: la quota è tot/1.04*0.04."""
    return round(float(totale_incassi) / 1.04 * 0.04, 2)


def prossimo_numero_fattura(descrizioni, anno: int) -> str:
    """Prossimo numero progressivo FAT-<anno>-NNN, dedotto dai movimenti già registrati."""
    massimo = 0
    for d in descrizioni:
        m = re.search(rf"FAT-{anno}-(\d+)", d or "")
        if m:
            massimo = max(massimo, int(m.group(1)))
    return f"FAT-{anno}-{massimo + 1:03d}"


_SOSTITUZIONI_PDF = {
    "€": "EUR", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "•": "-", "→": "->", " ": " ",
}


def pdf_safe(testo) -> str:
    """Rende il testo compatibile con i font core di FPDF (latin-1)."""
    s = "" if testo is None else str(testo)
    for k, v in _SOSTITUZIONI_PDF.items():
        s = s.replace(k, v)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def fetch_all(client, tabella, select="*", order=None, desc=False, filtri=None, pagina=1000):
    """Legge tutte le righe superando il limite di 1000 righe per richiesta di PostgREST."""
    righe, start = [], 0
    while True:
        q = client.table(tabella).select(select)
        for col, val in (filtri or {}).items():
            q = q.eq(col, val)
        if order:
            q = q.order(order, desc=desc)
        dati = q.range(start, start + pagina - 1).execute().data or []
        righe.extend(dati)
        if len(dati) < pagina:
            return righe
        start += pagina


def parse_grammi(valore, default=100.0) -> float:
    if valore is None:
        return default
    if isinstance(valore, (int, float)):
        return float(valore) if valore > 0 else default
    numeri = re.findall(r"\d+(?:[.,]\d+)?", str(valore))
    try:
        g = float(numeri[0].replace(",", ".")) if numeri else default
    except ValueError:
        return default
    return g if g > 0 else default


def trova_alimento(nome: str, catalogo: dict):
    """Cerca un alimento per nome: prima corrispondenza esatta, poi inclusione. None se assente.
    `catalogo` è {nome_minuscolo: id}. Non restituisce mai un alimento 'a caso'."""
    n = (nome or "").strip().lower()
    if len(n) < 3:
        return None
    if n in catalogo:
        return catalogo[n]
    candidati = [(k, v) for k, v in catalogo.items() if n in k or (len(k) >= 3 and k in n)]
    if len(candidati) == 1:
        return candidati[0][1]
    if candidati:  # più candidati: scegli il nome più vicino per lunghezza
        return min(candidati, key=lambda kv: abs(len(kv[0]) - len(n)))[1]
    return None
