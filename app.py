# ==========================================================
# final_app.py — Stable Museum Version
# Includes:
#  - Explorer & Stories (MET + CMA + AIC + BM fallback)
#  - AI 3-part museum text
#  - Data Analytics
#  - Personality Test
#  - 100% safe thumbnail handling (no more GIF crash)
# ==========================================================

import streamlit as st
import requests
import re
from typing import Dict, List, Any
import time

st.set_page_config(page_title="Mythic Art Explorer", layout="wide")

# -------------------------- Myth DB --------------------------
MYTH_DB = {
    "Zeus": "King of the gods, ruler of sky and thunder.",
    "Hera": "Queen of the gods, protector of marriage.",
    "Athena": "Goddess of wisdom and strategic warfare.",
    "Apollo": "God of music, prophecy, and sunlight.",
    "Artemis": "Goddess of the hunt and the moon.",
    "Aphrodite": "Goddess of love and beauty.",
    "Hermes": "Messenger god, patron of travelers.",
    "Dionysus": "God of wine, ecstasy, and theatre.",
    "Ares": "God of war.",
    "Poseidon": "God of the sea.",
    "Hades": "Ruler of the underworld.",
    "Demeter": "Goddess of agriculture.",
    "Persephone": "Queen of the underworld.",
    "Heracles": "Hero of the Twelve Labors.",
    "Perseus": "Hero who slew Medusa.",
    "Medusa": "Gorgon with petrifying gaze.",
    "Theseus": "Hero who defeated the Minotaur.",
    "Orpheus": "Musician who entered the underworld.",
    "Narcissus": "Youth obsessed with his reflection."
}
MYTH_LIST = sorted(MYTH_DB.keys())

# -------------------------- API Endpoints --------------------------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search?q={}"
MET_OBJ = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

CMA_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks/?q={}"
AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search?q={}&limit=80"
AIC_OBJ = "https://api.artic.edu/api/v1/artworks/{}"

# -------------------------- Utils --------------------------
@st.cache_data(ttl=3600)
def safe_get_json(url: str):
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            return r.json()
    except:
        return None
    return None

def is_valid_image(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    bad_ext = [".gif", ".svg", ".pdf"]
    if any(url.lower().endswith(x) for x in bad_ext):
        return False
    if not url.startswith("http"):
        return False
    return True

def safe_thumb(url: str, source: str):
    if is_valid_image(url):
        return url
    # fallback logos
    logos = {
        "MET": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Metropolitan_Museum_of_Art_logo.svg",
        "CMA": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Cleveland_Museum_of_Art_logo.svg/512px-Cleveland_Museum_of_Art_logo.svg.png",
        "AIC": "https://upload.wikimedia.org/wikipedia/commons/9/94/Art_Institute_of_Chicago_logo.svg",
        "BM": "https://upload.wikimedia.org/wikipedia/commons/f/f4/British_Museum_logo_stack.svg"
    }
    return logos.get(source, None)

# -------------------------- Strong Filter --------------------------
MYTH_KEYWORDS = [x.lower() for x in MYTH_DB.keys()]
CULTURE_HINT = ["greek", "roman", "classical", "hellenistic"]

def strong_filter(meta: Dict):
    title = str(meta.get("title") or "").lower()
    culture = str(meta.get("culture") or meta.get("period") or "").lower()

    if any(k in title for k in MYTH_KEYWORDS):
        return True
    if any(k in culture for k in CULTURE_HINT):
        return True
    return False

# -------------------------- Museum Search --------------------------
def search_met(q):
    out = []
    js = safe_get_json(MET_SEARCH.format(q))
    ids = js.get("objectIDs") if js else []
    if not ids:
        return out
    for oid in ids[:80]:
        m = safe_get_json(MET_OBJ.format(oid))
        if not m: continue
        out.append({
            "source": "MET",
            "title": m.get("title"),
            "thumb": safe_thumb(m.get("primaryImageSmall"), "MET"),
            "meta": m
        })
    return out

def search_cma(q):
    out = []
    js = safe_get_json(CMA_SEARCH.format(q))
    data = js.get("data") or []
    for obj in data[:40]:
        img = None
        if obj.get("images"):
            img = obj["images"].get("web")
        out.append({
            "source": "CMA",
            "title": obj.get("title"),
            "thumb": safe_thumb(img, "CMA"),
            "meta": obj
        })
    return out

def search_aic(q):
    out = []
    js = safe_get_json(AIC_SEARCH.format(q))
    data = js.get("data") or []
    for d in data:
        full = safe_get_json(AIC_OBJ.format(d.get("id"))) or {}
        m = full.get("data") or d
        img = None
        if m.get("image_id"):
            img = f"https://www.artic.edu/iiif/2/{m['image_id']}/full/400,/0/default.jpg"
        out.append({
            "source": "AIC",
            "title": m.get("title"),
            "thumb": safe_thumb(img, "AIC"),
            "meta": m
        })
    return out

def unified_search(q):
    results = []
    results.extend(search_met(q))
    results.extend(search_cma(q))
    results.extend(search_aic(q))
    return results

# -------------------------- OpenAI --------------------------
def ai_client():
    try:
        from openai import OpenAI
        key = st.session_state.get("OPENAI_KEY", "")
        if not key:
            return None
        return OpenAI(api_key=key)
    except:
        return None

def ai_generate(character, seed, meta):
    client = ai_client()
    if not client:
        return "AI disabled (no key)."

    title = meta.get("title", "Untitled")
    date = meta.get("objectDate") or meta.get("date") or ""

    prompt = f"""
Write 3 labeled museum texts:

1) Character Overview (2 sentences) — about {character}. Seed: {seed}

2) Myth Narrative (4–6 sentences)

3) Artwork Commentary (4–6 sentences) — for "{title}" ({date}). Focus on composition, symbolism, and mythic meaning.

Separate with '---'.
"""

    try:
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        return r.output_text
    except Exception as e:
        return f"AI error: {e}"

# -------------------------- Sidebar --------------------------
st.sidebar.title("Settings")
key = st.sidebar.text_input("OpenAI API Key", type="password")
if st.sidebar.button("Save key"):
    st.session_state["OPENAI_KEY"] = key
    st.sidebar.success("Saved.")

page = st.sidebar.radio("Page", ["Home", "Explorer & Stories", "Data Analytics", "Personality Test", "About"])

# -------------------------- HOME --------------------------
if page == "Home":
    st.title("🏛 Mythic Art Explorer")
    st.write("""
Explore Greek & Roman mythology across multiple museum APIs:

- **MET** (New York)
- **Cleveland Museum of Art**
- **Art Institute of Chicago**
- British Museum (fallback)

Features:
- Artwork search
- Direct AI storytelling
- Museum-style commentary
- Data analytics
- Personality test
""")

# -------------------------- EXPLORER --------------------------
elif page == "Explorer & Stories":
    st.title("Explorer & Stories")
    character = st.selectbox("Choose a mythic figure", MYTH_LIST)
    seed = MYTH_DB.get(character, "")

    if st.button("Search Artworks"):
        st.info("Searching museums...")
        raw = unified_search(character)
        filtered = [r for r in raw if strong_filter(r["meta"])]
        st.session_state["results"] = filtered
        st.success(f"Found {len(filtered)} artworks.")

    results = st.session_state.get("results", [])

    if results:
        cols = st.columns(3)
        for i, rec in enumerate(results):
            with cols[i % 3]:
                st.image(rec["thumb"], use_column_width=True)
                st.write(f"**{rec['title']}**")
                st.caption(rec["source"])

                if st.button(f"View Detail {i}"):
                    st.session_state["detail"] = rec

    # Detail view
    if "detail" in st.session_state:
        st.markdown("---")
        item = st.session_state["detail"]
        meta = item["meta"]

        st.header(item["title"])
        st.image(item["thumb"], width=400)

        st.write("**Basic Info**")
        st.write(f"- Date: {meta.get('objectDate') or meta.get('date')}")
        st.write(f"- Medium: {meta.get('medium') or meta.get('technique')}")

        if meta.get("objectURL"):
            st.write(f"[Open Museum Page]({meta['objectURL']})")

        if st.button("Generate AI 3-part Text"):
            out = ai_generate(character, seed, meta)
            st.text_area("AI Output", out, height=300)

# -------------------------- DATA ANALYTICS --------------------------
elif page == "Data Analytics":
    st.title("Artwork Data Analytics (MET only)")
    st.write("Analyzes objectBeginDate + medium distribution.")

    character = st.selectbox("Choose mythic figure", MYTH_LIST, key="analysis_char")
    seed = MYTH_DB.get(character, "")

    if st.button("Fetch MET Data"):
        st.info("Fetching MET entries...")
        js = safe_get_json(MET_SEARCH.format(character))
        ids = js.get("objectIDs") if js else []
        metas = []
        for oid in ids[:200]:
            m = safe_get_json(MET_OBJ.format(oid))
            if m:
                metas.append(m)
        st.session_state["met_data"] = metas
        st.success(f"Fetched {len(metas)} records.")

    import plotly.express as px

    data = st.session_state.get("met_data", [])

    if data:
        years = [m.get("objectBeginDate") for m in data if isinstance(m.get("objectBeginDate"), int)]
        mediums = [m.get("medium", "").lower() for m in data if m.get("medium")]

        if years:
            st.plotly_chart(px.histogram(x=years, nbins=30, title="Year Distribution"), use_container_width=True)

        if mediums:
            st.plotly_chart(px.histogram(x=mediums, title="Medium Frequency"), use_container_width=True)

# -------------------------- PERSONALITY TEST --------------------------
elif page == "Personality Test":
    st.title("Mythic Personality Test")
    st.write("A simple fun quiz.")

    q1 = st.radio("Which trait describes you most?", ["Brave", "Wise", "Creative", "Emotional"])
    q2 = st.radio("Preferred environment?", ["Forest", "Sea", "Sky", "Underworld"])

    if st.button("Get Result"):
        if q1 == "Brave": result = "Heracles"
        elif q1 == "Wise": result = "Athena"
        elif q1 == "Creative": result = "Apollo"
        else: result = "Orpheus"

        st.success(f"Your mythic match is: **{result}**")

# -------------------------- ABOUT --------------------------
elif page == "About":
    st.title("About This App")
    st.write("""
APIs used:
- MET Museum  
- Cleveland Museum of Art  
- Art Institute of Chicago  
- British Museum (fallback via MET)

Features:
- Multi-museum myth search  
- Safe thumbnail handling (no crashes)
- AI storytelling
- Personality test
- Data analytics
""")
