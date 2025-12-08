##############################
# Mythic Art Explorer — Full Version (Recommended)
# Multi-Museum API (No keys required)
# Explorer + Stories Combined
# Strong Filtering + AI Museum Text
##############################

import streamlit as st
import requests
import json
import time
import collections
from typing import Dict, List, Optional
import plotly.express as px

st.set_page_config(page_title="Mythic Art Explorer", layout="wide")

###############################################
# 1) Local Myth Database
###############################################
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

###############################################
# 2) Museum API endpoints (ALL NO-KEY)
###############################################

## MET
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

## Cleveland Museum of Art (CMA)
CMA_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks/?q={}"
CMA_OBJECT = "https://openaccess-api.clevelandart.org/api/artworks/{}"

## Art Institute of Chicago (AIC)
AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search?q={}&limit=80"
AIC_OBJECT = "https://api.artic.edu/api/v1/artworks/{}"

## British Museum (Unofficial)
BM_SEARCH = "https://www.britishmuseum.org/api/search?query={}"

###############################################
# 3) Cached GET helper
###############################################
@st.cache_data(ttl=3600, show_spinner=False)
def safe_get(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None

###############################################
# 4) Strong Filtering
###############################################
MYTH_KEYWORDS = [
    "zeus","hera","athena","apollo","artemis","perseus","medusa","narcissus",
    "dionysus","ares","poseidon","hades","heracles","aphrodite","orpheus","theseus"
]

CULTURE_KEYWORDS = ["greek","roman","hellenistic","classical","myth"]

MEDIUM_KEYWORDS = [
    "marble","bronze","terracotta","sculpture","vase","ceramic",
    "oil","tempera","drawing","print","engraving"
]


def strong_filter(meta: Dict) -> bool:
    """Robust filter: title + culture + medium"""
    if not meta:
        return False

    title = (meta.get("title") or "").lower()
    culture = (meta.get("culture") or meta.get("period") or "").lower()
    medium = (meta.get("medium") or "").lower()

    # Any myth keyword in title
    if any(k in title for k in MYTH_KEYWORDS):
        return True

    # Greek/Roman culture
    if any(k in culture for k in CULTURE_KEYWORDS):
        return True

    # Classical media + myth hints
    if any(k in medium for k in MEDIUM_KEYWORDS) and any(m in title for m in MYTH_KEYWORDS):
        return True

    return False


###############################################
# 5) Unified Museum Search (4 museums)
###############################################
def search_all_museums(query: str, max_items: int = 60):
    """Search MET + CMA + AIC + BM"""

    results = []

    # ------------- MET -------------
    raw = safe_get(f"{MET_SEARCH}?q={query}&hasImages=true")
    ids = (raw.get("objectIDs") or [])[:max_items] if raw else []
    for oid in ids:
        meta = safe_get(MET_OBJECT.format(oid))
        if meta:
            results.append({
                "source": "MET",
                "id": oid,
                "title": meta.get("title"),
                "culture": meta.get("culture"),
                "medium": meta.get("medium"),
                "thumb": meta.get("primaryImageSmall") or meta.get("primaryImage"),
                "meta": meta,
            })

    # ---------- Cleveland (CMA) ----------
    cma = safe_get(CMA_SEARCH.format(query)) or {}
    for obj in cma.get("data", [])[:max_items]:
        results.append({
            "source": "CMA",
            "id": obj.get("id"),
            "title": obj.get("title"),
            "culture": obj.get("culture"),
            "medium": obj.get("technique"),
            "thumb": obj.get("images", {}).get("web"),
            "meta": obj,
        })

    # ---------- AIC ----------
    aic = safe_get(AIC_SEARCH.format(query)) or {}
    for obj in aic.get("data", [])[:max_items]:
        # Get full object
        full = safe_get(AIC_OBJECT.format(obj.get("id"))) or {}
        img = None
        if "data" in full and "image_id" in full["data"]:
            img = f"https://www.artic.edu/iiif/2/{full['data']['image_id']}/full/400,/0/default.jpg"

        results.append({
            "source": "AIC",
            "id": obj.get("id"),
            "title": obj.get("title"),
            "culture": obj.get("culture"),
            "medium": (full.get("data", {}) or {}).get("medium_display"),
            "thumb": img,
            "meta": full.get("data") or {},
        })

    # ---------- British Museum ----------
    bm = safe_get(BM_SEARCH.format(query)) or {}
    for obj in bm.get("results", [])[:max_items]:
        results.append({
            "source": "BM",
            "id": obj.get("id"),
            "title": obj.get("title"),
            "culture": ", ".join(obj.get("cultures", [])),
            "medium": ", ".join(obj.get("materials", [])),
            "thumb": obj.get("image", {}).get("url"),
            "meta": obj
        })

    return results


###############################################
# 6) OpenAI Wrapper
###############################################
def has_key():
    return "OPENAI_API_KEY" in st.session_state and st.session_state["OPENAI_API_KEY"]

def get_client():
    try:
        from openai import OpenAI
        return OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
    except:
        return None

def ai(prompt, max_tokens=450):
    client = get_client()
    if not client:
        raise RuntimeError("OpenAI key missing.")
    resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
    return resp.output_text or ""


###############################################
# Sidebar — OpenAI Key
###############################################
st.sidebar.title("Settings")
api = st.sidebar.text_input("OpenAI API Key (optional)", type="password")
if st.sidebar.button("Save key"):
    st.session_state["OPENAI_API_KEY"] = api
    st.sidebar.success("Key saved.")

page = st.sidebar.selectbox("Page", [
    "Home",
    "Mythic Explorer & Stories",
    "Data Visualization",
    "About"
])

###############################################
# HOME — Show Museum API list
###############################################
if page == "Home":
    st.title("🏛 Mythic Art Explorer — Full Version")
    st.markdown("""
This project explores mythological artworks from major public museum APIs:

### **Data Sources (all free, no key required)**
- **The Metropolitan Museum of Art (MET)**
- **Cleveland Museum of Art (CMA)**
- **The Art Institute of Chicago (AIC)**
- **The British Museum (Unofficial API)**

You can browse artworks, select myth-related items, and generate AI museum-style texts.
""")

###############################################
# Explorer + Stories (combined)
###############################################
if page == "Mythic Explorer & Stories":

    st.header("Mythic Explorer — Multi-Museum Search")

    character = st.selectbox("Choose figure", MYTH_LIST)
    st.write(MYTH_DB.get(character))

    # SEARCH BUTTON
    if st.button("Search All Museums"):
        st.info("Searching... This may take several seconds.")
        raw = search_all_museums(character, max_items=60)
        filtered = [r for r in raw if strong_filter(r)]
        st.session_state["results"] = filtered
        st.success(f"Found {len(filtered)} myth-related items.")

    results = st.session_state.get("results", [])

    # Display
    if results:
        st.subheader("Gallery")
        cols = st.columns(3)
        for i, rec in enumerate(results):
            with cols[i % 3]:
                st.image(rec["thumb"], use_column_width=True)
                st.write(f"**{rec['title']}**")
                st.caption(f"{rec['source']} Museum")
                if st.button(f"Select {rec['source']}-{rec['id']}", key=f"sel_{rec['id']}"):
                    st.session_state["selected"] = rec
                    st.success("Selected!")

    # If selected
    if "selected" in st.session_state:
        rec = st.session_state["selected"]
        m = rec["meta"]

        st.markdown("---")
        st.subheader("Selected Artwork")
        st.image(rec["thumb"], width=350)
        st.write(f"**{rec['title']}**")
        st.write(f"Source: {rec['source']}")

        # AI MUSEUM TEXT
        if st.button("Generate 3-Part Museum Text (AI)"):
            if not has_key():
                st.warning("Enter OpenAI key first in sidebar.")
            else:
                seed = MYTH_DB.get(character, "")

                prompt = f"""
Write 3 museum texts:

1) Character Overview (2 sentences): {character}. Seed: {seed}
2) Myth Narrative (4–6 sentences): Retell a key myth involving {character}.
3) Artwork Commentary (5–6 sentences): Analyze the artwork titled '{rec['title']}'. Discuss composition, lighting, symbolism, and relation to myth.

Separate sections with "---".
"""
                try:
                    out = ai(prompt)
                    st.write(out)
                except Exception as e:
                    st.error(f"AI failed: {e}")

###############################################
# Data Visualization
###############################################
if page == "Data Visualization":
    st.header("Data Visualization (MET only example)")

    st.write("Enter a figure to fetch year distributions from MET.")

    fig = st.selectbox("Choose figure", MYTH_LIST)

    if st.button("Fetch MET data"):
        ids = (safe_get(f"{MET_SEARCH}?q={fig}&hasImages=true") or {}).get("objectIDs") or []
        metas = []
        for oid in ids[:200]:
            m = safe_get(MET_OBJECT.format(oid))
            if m and strong_filter(m):
                metas.append(m)

        st.session_state["viz"] = metas
        st.success(f"Loaded {len(metas)} items.")

    metas = st.session_state.get("viz", [])
    if metas:
        years = [m.get("objectBeginDate") for m in metas if isinstance(m.get("objectBeginDate"), int)]
        if years:
            chart = px.histogram(x=years, nbins=30, title="Year Distribution")
            st.plotly_chart(chart, use_container_width=True)

###############################################
# About
###############################################
if page == "About":
    st.title("About")
    st.write("Mythic Art Explorer — Full Version")
    st.write("Multi-museum search + strong filtering + AI museum labels.")

# End of file
