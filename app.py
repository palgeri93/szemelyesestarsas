# app.py
from __future__ import annotations
from pathlib import Path
import io
import re
import pandas as pd
import streamlit as st

# -------------------- Alap beállítások --------------------
st.set_page_config(
    page_title="Kompetencia-felmérés",
    page_icon="✅",
    layout="centered",
)

# A repo gyökere (ahol az app.py és az Excel-ek vannak)
BASE = Path(__file__).parent.resolve()

# A 4 kérdésbank fájl – nevezd át itt, ha a repóban más a nevük!
KERDESBANKOK = {
    "Személyes kompetencia 5-6 osztály": BASE / "Szemelyes_kompetenciak_5-6_oszt.xlsx",
    "Személyes kompetencia 7-8 osztály": BASE / "Szemelyes_kompetenciak_7-8_oszt.xlsx",
    "Társas kompetencia 5-6 osztály":    BASE / "Tarsas_kompetenciak_5-6_osztaly.xlsx",
    "Társas kompetencia 7-8 osztály":    BASE / "Tarsas_kompetenciak_7-8_osztaly.xlsx",
}

# Kategória-kód → felirat (A–H). Csak a ténylegesen előfordulókat jelenítjük meg.
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

# -------------------- Gyorsítótáras betöltés --------------------
@st.cache_data(show_spinner=True)
def betolt_xlsx(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    # Normalizáljuk az oszlopneveket: kisbetű, ékezet/whitespace eltávolítás, kötőjelek
    norm_map = {}
    for c in df.columns:
        key = re.sub(r"\s+", "_", c.strip().lower())
        key = key.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ö","o").replace("ő","o").replace("ú","u").replace("ü","u").replace("ű","u")
        norm_map[c] = key
    dfn = df.rename(columns=norm_map)

    # Keresünk értelmes oszlopokat a várható variánsokból
    kerdes_col = first_col(dfn, ["kerdes", "kérdés", "allitas", "allítás", "item", "szoveg", "szöveg"])
    kat_col    = first_col(dfn, ["kategoria", "kategória", "kat", "dimenzio", "dimenzió"])
    inv_col    = first_col(dfn, ["inverz_e", "inverz", "forditott", "forditott_e"])

    if kerdes_col is None or kat_col is None:
        raise ValueError("Az Excelben nem található a 'Kérdés' és/vagy 'Kategória' oszlop. Kérlek ellenőrizd a kérdésbankot.")

    # Inverz-e: Igen/Nem → boolean (True=fordított)
    dfn["_inverse"] = False
    if inv_col and inv_col in dfn.columns:
        dfn["_inverse"] = dfn[inv_col].astype(str).str.strip().str.lower().isin(["igen", "true", "1", "y", "yes"])

    # Standardizált, egységesített névvel adjuk vissza
    out = pd.DataFrame({
        "kerdes": dfn[kerdes_col].astype(str).str.strip(),
        "kategoria": dfn[kat_col].astype(str).str.strip(),
        "inverse": dfn["_inverse"].fillna(False),
    })
    # Eldobjuk az üres kérdéseket
    out = out[out["kerdes"].str.len() > 0].reset_index(drop=True)
    return out

def first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

# -------------------- UI – kezdőképernyő --------------------
st.markdown("## Kompetencia-felmérés")
st.write("Kérlek add meg a nevedet és az osztályodat, majd válaszd ki a kérdésbankot.")

with st.form("meta_form", clear_on_submit=False):
    nev = st.text_input("Név", value=st.session_state.get("nev","")).strip()
    osztaly = st.text_input("Osztály", value=st.session_state.get("osztaly","")).strip()
    submitted_meta = st.form_submit_button("Mentés")
    if submitted_meta:
        st.session_state["nev"] = nev
        st.session_state["osztaly"] = osztaly

# Választógombok – 4 kérdésbank
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
excel_path = KERDESBANKOK.get(bank_cim)
if not excel_path or not excel_path.exists():
    st.error(f"A kérdésbank fájl nem található: {excel_path}")
    st.stop()

try:
    bank_df = betolt_xlsx(excel_path)
except Exception as e:
    st.error(f"Nem sikerült beolvasni a kérdésbankot: {e}")
    st.stop()

# -------------------- Kitöltő felület --------------------
st.markdown(f"### {bank_cim}")
if not nev or not osztaly:
    st.warning("A folytatáshoz add meg a **Név** és **Osztály** mezőket a felső űrlapon.")
    st.stop()

# Session state az egyedi kulcsokhoz
if "valaszok" not in st.session_state:
    st.session_state["valaszok"] = {}

valaszok: dict[int, int] = st.session_state["valaszok"]

st.divider()
st.write("Jelöld meg, mennyire jellemzőek rád az alábbi állítások (1–5).")

for i, sor in bank_df.iterrows():
    kerdes = sor["kerdes"]
    key = f"q_{i}"
    default_idx = valaszok.get(i, None)
    # A radio értéke 0..4 index, később +1 → 1..5 pont
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

# Minden válasz megvan?
osszes_kerdes = len(bank_df)
megvalaszolt = len(valaszok)
if megvalaszolt < osszes_kerdes:
    st.warning(f"Még **{osszes_kerdes - megvalaszolt}** kérdésre nem válaszoltál.")
    st.stop()

# -------------------- Kiértékelés (inverz alapján) --------------------
# nyers pont (1..5)
bank_df["raw"] = [valaszok[i] + 1 for i in range(osszes_kerdes)]

# inverz kérdéseknél megfordítjuk: 6 - raw
bank_df["score"] = bank_df.apply(lambda r: 6 - r["raw"] if r["inverse"] else r["raw"], axis=1)

# Kategória aggregálás – csak a ténylegesen előfordulókat mutatjuk
kat_agg = (
    bank_df.groupby("kategoria")["score"]
    .agg(["count", "sum", "mean"])
    .reset_index()
    .sort_values("kategoria")
    .rename(columns={"count": "tételszám", "sum": "összpont", "mean": "átlag"})
)

# Feliratok hozzárendelése, ha A..H kódok vannak
def kat_cim(k: str) -> str:
    k2 = str(k).strip()
    if k2 in KATEGORIA_LABEL:
        return f"{k2} – {KATEGORIA_LABEL[k2]}"
    return k2

kat_agg["kategória"] = kat_agg["kategoria"].map(kat_cim)
kat_agg = kat_agg[["kategória", "tételszám", "összpont", "átlag"]]

st.divider()
st.markdown("### Eredmények")

col_a, col_b = st.columns([2,1])
with col_a:
    st.subheader("Kategória-összesítés")
    st.dataframe(kat_agg, hide_index=True, use_container_width=True)
with col_b:
    st.metric("Összpont (összes kérdés)", int(bank_df["score"].sum()))

# -------------------- Letöltés (XLSX, 3 munkalap) --------------------
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

# „széles” forma kategóriánkénti összefoglalóhoz (opcionális)
wide = (
    bank_df.assign(kat=bank_df["kategoria"])
    .pivot_table(index=None, values="score", columns="kat", aggfunc="mean")
)
wide.index = [0]  # egyetlen sor

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
    valaszok_long.to_excel(wr, sheet_name="valaszok", index=False)
    bank_df[["kategoria","kerdes","inverse","raw","score"]].to_excel(wr, sheet_name="atalakitott", index=False)
    kat_agg.to_excel(wr, sheet_name="kategoriak", index=False)
    # opcionális széles lap
    wide.to_excel(wr, sheet_name="kategoriak_wide", index=False)

fnev = f"kompetencia_eredmeny_{(st.session_state.get('nev') or 'tanulo').replace(' ', '_')}.xlsx"
st.download_button(
    "Eredmény letöltése (XLSX)",
    data=buf.getvalue(),
    file_name=fnev,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption(f"Név: **{st.session_state.get('nev','')}**, Osztály: **{st.session_state.get('osztaly','')}**, Bank: **{bank_cim}**")
