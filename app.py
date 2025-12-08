# final_app.py  (2025-12-08 version)
# Simplified clean version — No selection pool, direct AI generation per artwork
# 4-museum unified search (MET / CMA / AIC / BM fallback)
# Clean Explorer & Stories UI
# English only

import streamlit as st
import requests
from typing import Dict, List, Any, Optional
import time

# ----------------------- Page Setup -----------------------
st.set_page_config(page_title="Mythic Art Explorer", layout="wide")

# ----------------------- Myth Seeds -----------------------
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
    "Poseidon": "God of the sea and earthquakes.",
    "Hades": "Ruler of the underworld.",
    "Demeter": "Goddess of agriculture.",
    "Persephone": "Queen of the underworld.",
    "Heracles": "Hero of the Twelve Labors.",
    "Perseus": "Hero who slew Medusa.",
    "Orpheus": "Musician who entered the underworld.",
    "Narcissus": "Youth who fell in love with his reflection.",
    "Theseus": "Hero who defeated the Minotaur.",
    "Medusa": "Gorgon with petrifying gaze."
}
MYTH_LIST = sorted(MYTH_DB.keys())

# ----------------------- Museum API endpoints -----------------------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

CMA_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks/?q={}"
CMA_OBJECT = "https://openaccess-api.clevelandart.org/api/artworks/{}"

AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search?q={}&limit=80"
AIC_OBJECT = "https://api.artic.edu/api/v1/artworks/{}"

# British Museum fallback (uses MET API search)
BM_FALLBACK = MET_SEARCH

# ----------------------- Helpers -----------------------
@st.cache_data(ttl=3600)
def safe_get_json(url: str):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        return None
    return None

def safe_lower(x):
    if not x:
        return ""
    return str(x).lower()

# ----------------------- FILTER -----------------------
MYTH_KEYWORDS = [k.lower() for k in MYTH_DB.keys()]
CULTURE_HINT = ["greek", "roman", "hellenistic", "classical"]
MEDIUM_HINT = ["marble", "bronze", "terracotta", "vase", "sculpture", "engraving", "relief"]

def strong_filter(meta: Dict) -> bool:
    title = safe_lower(meta.get("title") or meta.get("objectName"))
    culture = safe_lower(meta.get("culture") or meta.get("period"))
    medium = safe_lower(meta.get("medium") or meta.get("technique"))

    if any(k in title for k in MYTH_KEYWORDS): return True
    if any(k in culture for k in CULTURE_HINT): return True
    if any(k in medium for k in MEDIUM_HINT) and any(k in title for k in MYTH_KEYWORDS): return True

    return False

# ----------------------- Museum Search -----------------------
def search_met(q, limit=60):
    out = []
    js = safe_get_json(f"{MET_SEARCH}?q={q}&hasImages=true")
    ids = js.get("objectIDs") if js else []
    if not ids: return out
    for oid in ids[:limit]:
        m = safe_get_json(MET_OBJECT.format(oid))
        if not m: continue
        out.append({
            "source": "MET",
            "title": m.get("title"),
            "thumb": m.get("primaryImageSmall"),
            "meta": m
        })
    return out

def search_cma(q, limit=40):
    out = []
    js = safe_get_json(CMA_SEARCH.format(q))
    data = js.get("data") if js else []
    for obj in data[:limit]:
        img = None
        imgs = obj.get("images") or {}
        if isinstance(imgs, dict):
            img = imgs.get("web")
        out.append({
            "source": "CMA",
            "title": obj.get("title"),
            "thumb": img,
            "meta": obj
        })
    return out

def search_aic(q, limit=60):
    out = []
    js = safe_get_json(AIC_SEARCH.format(q))
    data = js.get("data") if js else []
    for d in data[:limit]:
        full = safe_get_json(AIC_OBJECT.format(d.get("id"))) or {}
        m = full.get("data") or d
        img = None
        if m.get("image_id"):
            img = f"https://www.artic.edu/iiif/2/{m['image_id']}/full/400,/0/default.jpg"
        out.append({
            "source": "AIC",
            "title": m.get("title"),
            "thumb": img,
            "meta": m
        })
    return out

def search_bm(q, limit=40):
    # fallback to MET
    return search_met(q, limit)

def unified_search(q):
    q = q.lower()
    r = []
    r.extend(search_met(q))
    r.extend(search_cma(q))
    r.extend(search_aic(q))
    r.extend(search_bm(q))
    return r

# ----------------------- AI text generation -----------------------
def openai_client():
    try:
        from openai import OpenAI
        key = st.session_state.get("OPENAI_KEY", "")
        if not key:
            return None
        return OpenAI(api_key=key)
    except:
        return None

def generate_text(character, seed, artwork_meta):
    client = openai_client()
    if not client:
        return "AI disabled (no API key)."

    title = artwork_meta.get("title") or "Untitled"
    date = artwork_meta.get("objectDate") or artwork_meta.get("date") or ""

    prompt = f"""
You are a museum curator. Produce 3 labeled sections:

1) Character Overview — 2 sentences about {character}. Seed: {seed}

2) Myth Narrative — 4–6 sentences retelling a key myth.

3) Artwork Commentary — 4–6 sentences about the artwork "{title}" ({date}), discussing composition, symbolism, and connection to the myth.

Separate sections with '---'.
"""
    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        return resp.output_text
    except Exception as e:
        return f"AI error: {e}"

# ----------------------- UI -----------------------
st.sidebar.title("Settings")
inp_key = st.sidebar.text_input("OpenAI API key (optional)", type="password")
if st.sidebar.button("Save key"):
    st.session_state["OPENAI_KEY"] = inp_key
    st.sidebar.success("Saved.")

page = st.sidebar.selectbox("Page", ["Home", "Explorer & Stories", "About"])

# ----------------------- HOME -----------------------
if page == "Home":
    st.title("🏛 Mythic Art Explorer")
    st.write("""
Search Greek mythological figures across four open museum APIs:

- MET (New York)
- Cleveland Museum of Art (CMA)
- Art Institute of Chicago (AIC)
- British Museum (fallback through MET data)

This version provides **direct AI generation** for every artwork.  
No selection pool, no extra steps.
""")

# ----------------------- EXPLORER -----------------------
elif page == "Explorer & Stories":
    st.title("Explore & Generate Stories")
    character = st.selectbox("Choose a mythic figure", MYTH_LIST)
    seed = MYTH_DB.get(character, "")

    if st.button("Search"):
        st.info("Searching across MET / CMA / AIC / BM ...")
        raw = unified_search(character)
        filtered = [r for r in raw if strong_filter(r["meta"])]
        st.session_state["results"] = filtered
        st.success(f"Found {len(filtered)} artworks.")

    results = st.session_state.get("results", [])
    if results:
        st.subheader(f"Results for {character}")
        cols = st.columns(3)

        for i, rec in enumerate(results):
            with cols[i % 3]:
                if rec.get("thumb"):
                    st.image(rec["thumb"], use_column_width=True)
                st.write(f"**{rec['title']}**")
                st.caption(rec["source"])

                if st.button(f"View Detail {i}"):
                    st.session_state["detail"] = rec

# ----------------------- DETAIL + AI -----------------------
    if "detail" in st.session_state:
        st.markdown("---")
        item = st.session_state["detail"]
        st.header(item["title"])
        if item.get("thumb"):
            st.image(item["thumb"], width=400)
        meta = item["meta"]

        st.write("**Basic Info**")
        st.write(f"- Medium: {meta.get('medium') or meta.get('technique')}")
        st.write(f"- Date: {meta.get('objectDate') or meta.get('date')}")
        if meta.get("objectURL"):
            st.write(f"[Open Museum Page]({meta['objectURL']})")

        st.markdown("### Generate 3-part museum text")
        if st.button("Generate AI Text"):
            out = generate_text(character, seed, meta)
            st.text_area("AI Output", out, height=300)

# ----------------------- ABOUT -----------------------
elif page == "About":
    st.title("About")
    st.write("""
This version simplifies the UI:

- No selection pool  
- Direct per-artwork AI generation  
- Clean Explorer & Stories combined

APIs used:
- Metropolitan Museum of Art
- Cleveland Museum of Art
- Art Institute of Chicago
- British Museum fallback (via MET)
""")
