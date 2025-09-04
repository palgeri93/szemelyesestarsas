# app.py
from __future__ import annotations
from pathlib import Path
import io
import re
import os
import pandas as pd
import streamlit as st

# -------------------- Oldalbeállítás --------------------
st.set_page_config(
    page_title="Kompetencia-felmérés",
    page_icon="✅",
    layout="centered",
)

# -------------------- Elérési utak --------------------
BASE = Path(__file__).parent.resolve()
KERDESBANK_DIR = BASE / "KERDESBANKOK"

def _norm_txt(s: str) -> str:
    """Ékezetlenített, kisbetűs, nem alfanumerikus jeleket szóközre cserélő normalizálás."""
    s = str(s).strip().lower()
    table = str.maketrans("áéíóöőúüű", "aeioooouuu")
    s = s.translate(table)
    s = re.sub(r"[^0-9a-z]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _tokens(s: str) -> set[str]:
    return set(_norm_txt(s).split())

def _list_xlsx() -> list[Path]:
    cand_dirs = [BASE, KERDESBANK_DIR]
    files: list[Path] = []
    for d in cand_dirs:
        if d.exists():
            files.extend(sorted(d.glob("*.xlsx")))
    return files

# DEBUG: mit látunk?
st.write("DEBUG – BASE tartalma:", [p.name for p in BASE.iterdir() if p.exists()])
st.write("DEBUG – KERDESBANKOK létezik?:", KERDESBANK_DIR.exists())
st.write("DEBUG – Elérhető .xlsx fájlok:", [p.name for p in _list_xlsx()])

# A 4 bank címke (a gombok felirata)
BANK_CIMEK = [
    "Személyes kompetencia 5-6 osztály",
    "Személyes kompetencia 7-8 osztály",
    "Társas kompetencia 5-6 osztály",
    "Társas kompetencia 7-8 osztály",
]

def _bank_cim_to_required_tokens(bank_cim: str) -> set[str]:
    """A kiválasztott bank címkéjéből olyan tokeneket képezünk,
    amiknek a fájlnévben is szerepelniük kell (normalizált formában)."""
    t = _tokens(bank_cim)
    req = set()
    # szemelyes/tarsas/kompetenciak
    if "szemelyes" in t:
        req.add("szemelyes")
    if "tarsas" in t:
        req.add("tarsas")
    req.add("kompetenciak")  # a fájlokban többnyire ez szerepel
    # évfolyamok
    if "5" in t and "6" in t:
        req.update({"5", "6"})
    if "7" in t and "8" in t:
        req.update({"7", "8"})
    # oszt / osztaly – bármelyik jó
    req.add("oszt")  # a legtöbb fájlnévben röviden jelenik meg
    return req

def resolve_excel_for_bank(bank_cim: str) -> Path | None:
    """Megpróbáljuk megtalálni a hozzá tartozó .xlsx fájlt lazán illesztve."""
    req = _bank_cim_to_required_tokens(bank_cim)
    candidates = _list_xlsx()
    best: tuple[int, Path] | None = None
    for p in candidates:
        toks = _tokens(p.stem)  # kiterjesztés nélkül
        # elfogadjuk, ha az összes kötelező token benne van
        ok = req.issubset(toks)
        if not ok:
            continue
        score = len(toks)  # primitív pontozás: kevesebb zaj jobb
        if best is None or score < best[0]:
            best = (score, p)
    # ha nem találtunk teljes fedést, próbáljuk „osztaly”/„oszt” cserével is
    if best is None:
        alt_req = set(req)
        alt_req.discard("oszt")
        alt_req.add("osztaly")
        for p in candidates:
            toks = _tokens(p.stem)
            if alt_req.issubset(toks):
                return p
    return best[1] if best else None

# Kategória-kód → felirat (A–H). Csak az előfordulókat mutatjuk.
KATEGORIA_LABEL = {
    "A": "Önismeret, önértékelés, önbizalom",
    "B": "Motiváció, optimizmus, teljesítményvágy",
    "C": "Lelkiismeretesség, kitartás",
    "D": "Kezdeményezőkészség, kreativitás",
    "E": "Empátia, sokféleség elfogadása",
    "F": "Együttműködés",
    "G": "Konfliktuskezelés",
    "H": "Kommunikáció",
}

LIKERT_OPCIOK = [
    "1 – Egyáltalán nem jellemző",
    "2 – Inkább nem jellemző",
    "3 – Részben jellemző",
    "4 – Inkább jellemző",
    "5 – Teljesen jellemző",
]

# -------------------- Betöltő függvény --------------------
@st.cache_data(show_spinner=True)
def betolt_xlsx(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)

    # Normalizált oszlopnevek (ékezet és whitespace kezelése)
    def norm(s: str) -> str:
        s2 = s.strip().lower()
        s2 = re.sub(r"\s+", "_", s2)
        table = str.maketrans("áéíóöőúüű", "aeioooouuu")
        return s2.translate(table)

    dfn = df.rename(columns={c: norm(c) for c in df.columns})

    kerdes_col = first_col(dfn, ["kerdes", "kerdes_szoveg", "allitas", "item", "szoveg"])
    kat_col    = first_col(dfn, ["kategoria", "dimenzio"])
    inv_col    = first_col(dfn, ["inverz_e", "inverz", "forditott", "forditott_e"])

    if kerdes_col is None or kat_col is None:
        raise ValueError("Az Excelben nem található a 'Kérdés' és/vagy 'Kategória' oszlop.")

    # Inverz: Igen/Nem → bool
    dfn["_inverse"] = False
    if inv_col and inv_col in dfn.columns:
        dfn["_inverse"] = (
            dfn[inv_col].astype(str).str.strip().str.lower()
            .isin(["igen", "true", "1", "y", "yes"])
        )

    out = pd.DataFrame({
        "kerdes": dfn[kerdes_col].astype(str).str.strip(),
        "kategoria": dfn[kat_col].astype(str).str.strip(),
        "inverse": dfn["_inverse"].fillna(False),
    })
    out = out[out["kerdes"].str.len() > 0].reset_index(drop=True)
    return out

def first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

# -------------------- UI – fejléc, űrlap --------------------
st.markdown("## Kompetencia-felmérés")
st.write("Add meg a neved és az osztályod, majd válaszd ki a kérdésbankot a gombokkal.")

with st.form("meta_form", clear_on_submit=False):
    nev = st.text_input("Név", value=st.session_state.get("nev", "")).strip()
    osztaly = st.text_input("Osztály", value=st.session_state.get("osztaly", "")).strip()
    if st.form_submit_button("Mentés"):
        st.session_state["nev"] = nev
        st.session_state["osztaly"] = osztaly

# -------------------- 4 választógomb --------------------
cols = st.columns(2)
with cols[0]:
    if st.button("Személyes kompetencia 5-6 osztály"):
        st.session_state["bank_cim"] = "Személyes kompetencia 5-6 osztály"
with cols[1]:
    if st.button("Személyes kompetencia 7-8 osztály"):
        st.session_state["bank_cim"] = "Személyes kompetencia 7-8 osztály"
with cols[0]:
    if st.button("Társas kompetencia 5-6 osztály"):
        st.session_state["bank_cim"] = "Társas kompetencia 5-6 osztály"
with cols[1]:
    if st.button("Társas kompetencia 7-8 osztály"):
        st.session_state["bank_cim"] = "Társas kompetencia 7-8 osztály"

bank_cim = st.session_state.get("bank_cim")
if not bank_cim:
    st.info("Válassz kérdésbankot a fenti gombokkal!")
    st.stop()

# -------------------- Kérdésbank betöltése --------------------
excel_path = resolve_excel_for_bank(bank_cim)
st.write("DEBUG – kiválasztott bank:", bank_cim)
st.write("DEBUG – Megtalált Excel elérési út:", str(excel_path) if excel_path else None)

if not excel_path or not excel_path.exists():
    st.error(
        "A kérdésbank fájl nem található az elnevezési eltérések miatt. "
        "Kérlek, ellenőrizd, hogy a megfelelő .xlsx fájl a projekt gyökérben "
        "vagy a KERDESBANKOK mappában van-e. "
        f"Elérhető fájlok: {[p.name for p in _list_xlsx()]}"
    )
    st.stop()

try:
    bank_df = betolt_xlsx(excel_path)
except Exception as e:
    st.error(f"Nem sikerült beolvasni a kérdésbankot: {e}")
    st.stop()

# -------------------- Kitöltő felület --------------------
st.markdown(f"### {bank_cim}")
if not st.session_state.get("nev") or not st.session_state.get("osztaly"):
    st.warning("A folytatáshoz add meg a **Név** és **Osztály** mezőket a felső űrlapon.")
    st.stop()

if "valaszok" not in st.session_state:
    st.session_state["valaszok"] = {}
valaszok: dict[int, int] = st.session_state["valaszok"]

st.divider()
st.write("Jelöld meg, mennyire jellemzőek rád az alábbi állítások (1–5).")

for i, sor in bank_df.iterrows():
    kerdes = sor["kerdes"]
    key = f"q_{i}"
    default_idx = valaszok.get(i, None)
    idx = st.radio(
        f"{i+1}. {kerdes}",
        options=list(range(len(LIKERT_OPCIOK))),
        format_func=lambda k: LIKERT_OPCIOK[k],
        index=default_idx if default_idx is not None else None,
        horizontal=True,
        key=key,
    )
    if idx is not None:
        valaszok[i] = idx

osszes_kerdes = len(bank_df)
megvalaszolt = len(valaszok)
if megvalaszolt < osszes_kerdes:
    st.warning(f"Még **{osszes_kerdes - megvalaszolt}** kérdésre nem válaszoltál.")
    st.stop()

# -------------------- Pontszámítás (inverz is) --------------------
bank_df["raw"] = [valaszok[i] + 1 for i in range(osszes_kerdes)]  # 1..5
bank_df["score"] = bank_df.apply(lambda r: 6 - r["raw"] if r["inverse"] else r["raw"], axis=1)

# -------------------- Kategória-összesítés --------------------
kat_agg = (
    bank_df.groupby("kategoria")["score"]
    .agg(["count", "sum", "mean"])
    .reset_index()
    .sort_values("kategoria")
    .rename(columns={"count": "tételszám", "sum": "összpont", "mean": "átlag"})
)

def kat_cim(k: str) -> str:
    k2 = str(k).strip()
    return f"{k2} – {KATEGORIA_LABEL[k2]}" if k2 in KATEGORIA_LABEL else k2

kat_agg["kategória"] = kat_agg["kategoria"].map(kat_cim)
kat_agg = kat_agg[["kategória", "tételszám", "összpont", "átlag"]]

st.divider()
st.markdown("### Eredmények")

col_a, col_b = st.columns([2, 1])
with col_a:
    st.subheader("Kategória-összesítés")
    st.dataframe(kat_agg, hide_index=True, use_container_width=True)
with col_b:
    st.metric("Összpont (összes kérdés)", int(bank_df["score"].sum()))

# -------------------- Letöltés XLSX --------------------
st.divider()
st.subheader("Riport letöltése")

valaszok_long = bank_df[["kategoria", "kerdes", "inverse", "raw", "score"]].copy()
valaszok_long.rename(columns={
    "kategoria": "Kategória",
    "kerdes": "Kérdés",
    "inverse": "Inverz kérdés?",
    "raw": "Jelölt érték (1..5)",
    "score": "Pont (inverz után)",
}, inplace=True)

wide = (
    bank_df.assign(kat=bank_df["kategoria"])
    .pivot_table(index=None, values="score", columns="kat", aggfunc="mean")
)
wide.index = [0]

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
    valaszok_long.to_excel(wr, sheet_name="valaszok", index=False)
    bank_df[["kategoria", "kerdes", "inverse", "raw", "score"]].to_excel(wr, sheet_name="atalakitott", index=False)
    kat_agg.to_excel(wr, sheet_name="kategoriak", index=False)
    wide.to_excel(wr, sheet_name="kategoriak_wide", index=False)

fnev = f"kompetencia_eredmeny_{(st.session_state.get('nev') or 'tanulo').replace(' ', '_')}.xlsx"
st.download_button(
    "Eredmény letöltése (XLSX)",
    data=buf.getvalue(),
    file_name=fnev,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption(f"Név: **{st.session_state.get('nev','')}**, Osztály: **{st.session_state.get('osztaly','')}**, Bank: **{bank_cim}**")
