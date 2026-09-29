import sys, os
from datetime import date
from decimal import Decimal
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logic as L


def test_cf():
    assert L.cf_valido("rssmra80a01h501u")
    assert not L.cf_valido("")
    assert not L.cf_valido("ABC")


def test_telefono():
    assert L.normalizza_telefono("340 123-4567") == "393401234567"
    assert L.normalizza_telefono("+39 340 1234567") == "393401234567"
    assert L.normalizza_telefono("0039340123") == "39340123"
    assert L.normalizza_telefono(None) == ""


def test_bmr():
    bmr, tdee, bmi = L.calcola_bmr_tdee("Maschio", 75, 175, 30, 1.2)
    assert round(bmr) == 1699 and abs(tdee - 2038.5) < 0.01 and round(bmi, 1) == 24.5
    assert round(L.calcola_bmr_tdee("Femmina", 60, 165, 30, 1)[0]) == 1320


def test_fattura():
    f = L.calcola_fattura(100)
    assert f["rivalsa"] == Decimal("4.00") and f["bollo"] == Decimal("2.00") and f["totale"] == Decimal("106.00")
    assert L.calcola_fattura(70)["bollo"] == Decimal("0.00")  # 72.80 < 77.47
    assert L.calcola_fattura(10.10)["totale"] == Decimal("10.50")


def test_enpab():
    assert L.enpab_contenuta_negli_incassi(104) == 4.0


def test_numero_fattura():
    assert L.prossimo_numero_fattura([], 2026) == "FAT-2026-001"
    assert L.prossimo_numero_fattura(["Fattura FAT-2026-009 - X", "Fattura FAT-2025-050"], 2026) == "FAT-2026-010"


def test_estrai_cf():
    assert L.estrai_cf("Fattura X - Rossi (CF: rssmra80a01h501u)") == "RSSMRA80A01H501U"
    assert L.estrai_cf("Incasso manuale") == "NON INDICATO"


def test_pdf_safe():
    assert L.pdf_safe("Costo 5 € – ok “x”") == 'Costo 5 EUR - ok "x"'
    assert L.pdf_safe("ł").encode("latin-1")


def test_script_json():
    assert "</script>" not in L.json_per_script([{"t": "</script><b>"}])


def test_esc():
    assert L.esc("<b>&") == "&lt;b&gt;&amp;" and L.esc(None) == ""


def test_pin():
    h = L.hash_pin("1234", "RSSMRA80A01H501U")
    assert L.verifica_pin("1234", "rssmra80a01h501u", h) and not L.verifica_pin("0000", "RSSMRA80A01H501U", h)
    assert not L.verifica_pin("1234", "RSSMRA80A01H501U", "")


def test_eta():
    assert L.eta_da_data_nascita("1990-06-15", date(2026, 6, 14)) == 35
    assert L.eta_da_data_nascita("1990-06-15", date(2026, 6, 15)) == 36
    assert L.eta_da_data_nascita(None) is None


def test_grammi():
    assert L.parse_grammi(None) == 100.0 and L.parse_grammi("80 g") == 80.0
    assert L.parse_grammi("2,5") == 2.5 and L.parse_grammi(-3) == 100.0


def test_trova_alimento():
    cat = {"pasta di semola": 1, "riso": 2, "pollo petto": 3}
    assert L.trova_alimento("Riso", cat) == 2
    assert L.trova_alimento("pasta", cat) == 1
    assert L.trova_alimento("", cat) is None
    assert L.trova_alimento("cioccolato", cat) is None


class _Q:
    def __init__(self, data): self.data, self.r = data, None
    def select(self, *_): return self
    def eq(self, *_): return self
    def order(self, *_, **__): return self
    def range(self, a, b): self.r = (a, b); return self
    def execute(self):
        class R: pass
        r = R(); r.data = self.data[self.r[0]:self.r[1] + 1]; return r

class _C:
    def __init__(self, n): self.n = n
    def table(self, _): return _Q(list(range(self.n)))


def test_fetch_all_pagina():
    assert len(L.fetch_all(_C(2500), "t")) == 2500
    assert len(L.fetch_all(_C(1000), "t")) == 1000
    assert L.fetch_all(_C(0), "t") == []
