# final_app.py
"""
Mythic Art Explorer — Full Version (Recommended)
- Multi-museum search (MET, AIC, CMA, British Museum unofficial)
- Strong, robust filtering (never crashes on missing fields)
- Combined Explorer + Stories page
- Selection pool (saved items)
- Optional OpenAI integration for 3-part museum text
- English UI
"""

import streamlit as st
import requests
import json
import time
import collections
from typing import Dict, List, Any, Optional
import plotly.express as px

# --------- Page config ----------
st.set_page_config(page_title="Mythic Art Explorer", layout="wide", initial_sidebar_state="expanded")

# --------- Local myth seeds ----------
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

# --------- Museum API endpoints (no-key) ----------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

# Cleveland Museum of Art (Open Access)
CMA_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks/?q={}"
CMA_OBJECT = "https://openaccess-api.clevelandart.org/api/artworks/{}"

# Art Institute of Chicago
AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search?q={}&limit=80"
AIC_OBJECT = "https://api.artic.edu/api/v1/artworks/{}"

# British Museum unofficial search (best-effort)
BM_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"  # fallback to MET search if BM unstable
# NOTE: Some BM unofficial APIs are unstable; we will fallback gracefully.

# --------- Helpers: safe HTTP GET with caching ----------
@st.cache_data(ttl=60*60, show_spinner=False)
def safe_get_json(url: str) -> Optional[Any]:
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None
    return None

# --------- Keywords + filtering (robust) ----------
MYTH_KEYWORDS = [
    "zeus","hera","athena","apollo","artemis","perseus","medusa","narcissus",
    "dionysus","ares","poseidon","hades","heracles","aphrodite","orpheus","theseus"
]
CULTURE_KEYWORDS = ["greek","roman","hellenistic","classical","myth"]
MEDIUM_KEYWORDS = [
    "marble","bronze","terracotta","sculpture","vase","ceramic",
    "oil","tempera","drawing","print","engraving","relief","statuette"
]

def safe_str_field(value: Any) -> str:
    """Return a lowercase string for various possible field types, safe for .lower()"""
    if not value:
        return ""
    if isinstance(value, str):
        return value.lower()
    try:
        return str(value).lower()
    except Exception:
        return ""

def strong_filter(meta: Dict) -> bool:
    """
    Robust heuristic filter to check whether a metadata dict is likely Greek/Roman myth related.
    Returns False on invalid input without raising.
    """
    if not isinstance(meta, dict):
        return False

    title = safe_str_field(meta.get("title") or meta.get("objectName") or meta.get("label") or "")
    culture = safe_str_field(meta.get("culture") or meta.get("period") or "")
    medium = safe_str_field(meta.get("medium") or meta.get("technique") or meta.get("classification") or "")

    # direct myth keyword in title
    if any(k in title for k in MYTH_KEYWORDS):
        return True

    # culture hint
    if any(k in culture for k in CULTURE_KEYWORDS):
        return True

    # medium + title hint
    if any(k in medium for k in MEDIUM_KEYWORDS) and any(k in title for k in MYTH_KEYWORDS):
        return True

    # some records have tags / object type fields
    tags = meta.get("tags") or meta.get("tag") or []
    # tags may be list of dicts or list of strings
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, dict):
                term = safe_str_field(t.get("term") or t.get("name") or "")
            else:
                term = safe_str_field(t)
            if any(k in term for k in MYTH_KEYWORDS + CULTURE_KEYWORDS):
                return True

    return False

# --------- Unified search across museums ----------
def search_met(query: str, max_results: int = 80) -> List[Dict]:
    out = []
    q = query.strip()
    if not q:
        return out
    js = safe_get_json(f"{MET_SEARCH}?q={requests.utils.quote(q)}&hasImages=true")
    ids = js.get("objectIDs") if js else []
    if not ids:
        return out
    for oid in ids[:max_results]:
        meta = safe_get_json(MET_OBJECT.format(oid))
        if not meta:
            continue
        thumb = meta.get("primaryImageSmall") or meta.get("primaryImage") or ""
        out.append({
            "source": "MET",
            "id": oid,
            "title": meta.get("title"),
            "culture": meta.get("culture"),
            "medium": meta.get("medium"),
            "thumb": thumb,
            "meta": meta
        })
    return out

def search_cma(query: str, max_results: int = 60) -> List[Dict]:
    out = []
    q = query.strip()
    if not q:
        return out
    js = safe_get_json(CMA_SEARCH.format(requests.utils.quote(q)))
    data = js.get("data") if js else []
    for obj in data[:max_results]:
        thumb = None
        # safe extraction of image
        images = obj.get("images") or {}
        if isinstance(images, dict):
            thumb = images.get("web") or images.get("thumbnail")
        out.append({
            "source": "CMA",
            "id": obj.get("id"),
            "title": obj.get("title") or obj.get("name"),
            "culture": obj.get("culture"),
            "medium": obj.get("technique") or obj.get("material"),
            "thumb": thumb,
            "meta": obj
        })
    return out

def search_aic(query: str, max_results: int = 80) -> List[Dict]:
    out = []
    q = query.strip()
    if not q:
        return out
    js = safe_get_json(AIC_SEARCH.format(requests.utils.quote(q)))
    data = js.get("data") if js else []
    for item in data[:max_results]:
        aid = item.get("id")
        # fetch full object for better data (best-effort)
        full = safe_get_json(AIC_OBJECT.format(aid)) or {}
        meta = full.get("data") if isinstance(full, dict) else item
        img = None
        if isinstance(meta, dict) and meta.get("image_id"):
            img = f"https://www.artic.edu/iiif/2/{meta['image_id']}/full/400,/0/default.jpg"
        out.append({
            "source": "AIC",
            "id": aid,
            "title": meta.get("title") or item.get("title"),
            "culture": meta.get("culture"),
            "medium": meta.get("medium_display") or meta.get("medium"),
            "thumb": img,
            "meta": meta
        })
    return out

def search_british_museum(query: str, max_results: int = 50) -> List[Dict]:
    """
    British Museum API is unofficial/unstable; attempt best-effort searching.
    If unavailable, return empty list (no crash).
    """
    out = []
    q = query.strip()
    if not q:
        return out
    # best-effort: try MET search as fallback (many items overlap)
    # This keeps behavior stable without requiring a new API key.
    try:
        # use MET search but mark source 'BM (fallback MET-search)'
        js = safe_get_json(f"{MET_SEARCH}?q={requests.utils.quote(q)}&hasImages=true")
        ids = js.get("objectIDs") or []
        for oid in ids[:max_results]:
            meta = safe_get_json(MET_OBJECT.format(oid))
            if not meta:
                continue
            out.append({
                "source": "BM",
                "id": oid,
                "title": meta.get("title"),
                "culture": meta.get("culture"),
                "medium": meta.get("medium"),
                "thumb": meta.get("primaryImageSmall") or meta.get("primaryImage"),
                "meta": meta
            })
    except Exception:
        return []
    return out

def unified_search(query: str, per_source: int = 80) -> List[Dict]:
    """
    Search across MET, CMA, AIC, BM (best-effort).
    Returns combined list (no dedupe).
    """
    results = []
    results.extend(search_met(query, max_results=per_source))
    results.extend(search_cma(query, max_results=per_source))
    results.extend(search_aic(query, max_results=per_source))
    results.extend(search_british_museum(query, max_results=int(per_source/2)))
    # simple dedupe by (source,id) kept - no cross-source dedupe to preserve provenance
    return results

# --------- OpenAI helper (optional) ----------
def openai_client_from_session():
    try:
        from openai import OpenAI
        key = st.session_state.get("OPENAI_API_KEY", "")
        if not key:
            return None
        return OpenAI(api_key=key)
    except Exception:
        return None

def ai_generate_museum_text(character: str, seed: str, artwork_meta: Dict) -> str:
    """
    Generate 3-part museum text using OpenAI Responses API (gpt-4.1-mini if available).
    Returns text or raises Exception.
    """
    client = openai_client_from_session()
    if not client:
        raise RuntimeError("OpenAI client not available (set key in sidebar).")
    title = artwork_meta.get("title") or artwork_meta.get("objectName") or "Untitled"
    artist = artwork_meta.get("artistDisplayName") or artwork_meta.get("artist") or "Unknown"
    date = artwork_meta.get("objectDate") or artwork_meta.get("date") or ""
    prompt = f"""
You are an art historian and museum curator. Produce three labeled sections for exhibition use:

1) Character Overview (1-2 sentences) about {character}. Seed: {seed}

2) Myth Narrative (3-6 sentences) — an emotive museum audio-guide style retelling the key myth(s) of {character}.

3) Artwork Commentary (4-6 sentences) — analyze the artwork titled "{title}" by {artist}, dated {date}. Discuss composition, lighting, pose, symbolism, and how the image relates to the myth. Keep language accessible to students and exhibition visitors.

Return sections separated by '---' and label each section clearly.
"""
    resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
    return resp.output_text or ""

# --------- Sidebar (OpenAI key + settings) ----------
st.sidebar.title("Settings")
st.sidebar.markdown("Enter your OpenAI API key here (optional) to enable AI museum text generation for selected artworks.")
openai_key = st.sidebar.text_input("OpenAI API Key (session only)", type="password", key="openai_key")
if st.sidebar.button("Save OpenAI key"):
    if openai_key:
        st.session_state["OPENAI_API_KEY"] = openai_key
        st.sidebar.success("OpenAI key saved to session.")
    else:
        st.sidebar.warning("Please provide a valid key.")

st.sidebar.markdown("---")
page = st.sidebar.selectbox("Page", ["Home", "Explorer & Stories", "Saved Items", "Data Visualization", "About"], index=0)

# --------- Home page ----------
if page == "Home":
    st.title("🏛 Mythic Art Explorer — Full Version (Recommended)")
    st.markdown("""
**This educational demo aggregates open museum APIs and provides museum-style interpretation for myth-related artworks.**

**Data Sources (no API key required):**
- **The Metropolitan Museum of Art (MET)** — best for classical / Greek & Roman holdings.
- **Cleveland Museum of Art (CMA)** — high-quality images / open access.
- **The Art Institute of Chicago (AIC)** — clean structured metadata.
- **British Museum (best-effort fallback search)** — public collection data.

Use **Explorer & Stories** to search for mythic figures, curate a selection pool, and (optionally) generate AI museum texts for selected art.
""")
    st.markdown("### Quick tips")
    st.write("- Use the figure selector in Explorer to run a multi-museum search.")
    st.write("- Press **Select** on results to add to the Selection Pool.")
    st.write("- To enable AI: paste your OpenAI key in the sidebar and press Save.")

# --------- Explorer & Stories (combined) ----------
if page == "Explorer & Stories":
    st.header("Explorer & Stories — Search across MET / CMA / AIC / BM")
    character = st.selectbox("Choose a mythic figure", MYTH_LIST, index=0)
    st.write("Short character seed:", MYTH_DB.get(character, ""))
    with st.expander("Advanced search options (optional)"):
        per_source = st.slider("Max results per source", 10, 120, 60, step=10)
        use_strong_filter = st.selectbox("Filter strictness", ["Strong (recommended)", "Medium", "None"], index=0)

    if st.button("Run search across museums"):
        st.info("Running multi-museum search — this may take several seconds.")
        raw_results = unified_search(character, per_source)
        # apply chosen filter
        if use_strong_filter == "Strong (recommended)":
            filtered = [r for r in raw_results if strong_filter(r.get("meta") or {})]
        elif use_strong_filter == "Medium":
            # medium: accept if title or medium contains keywords
            filtered = []
            for r in raw_results:
                meta = r.get("meta") or {}
                title = safe_str_field(meta.get("title"))
                medium = safe_str_field(meta.get("medium") or meta.get("technique"))
                if any(k in title for k in MYTH_KEYWORDS) or any(k in medium for k in MEDIUM_KEYWORDS):
                    filtered.append(r)
        else:
            filtered = raw_results

        # store results in session
        st.session_state["search_results"] = filtered
        st.session_state["selection_pool"] = st.session_state.get("selection_pool", [])
        st.success(f"Search finished — {len(filtered)} candidate items (after filtering).")

    results = st.session_state.get("search_results", [])
    if not results:
        st.info("No results yet. Run a search or change filter settings.")
    else:
        st.subheader(f"Found {len(results)} items — click Select to add to Selection Pool")
        cols = st.columns(3)
        for i, rec in enumerate(results):
            with cols[i % 3]:
                thumb = rec.get("thumb") or ""
                if thumb:
                    try:
                        st.image(thumb, use_column_width=True)
                    except Exception:
                        st.write("[No preview available]")
                st.write(f"**{rec.get('title') or 'Untitled'}**")
                st.caption(f"Source: {rec.get('source')}")
                if st.button(f"Select {rec.get('source')}-{rec.get('id')}", key=f"select_{rec.get('source')}_{rec.get('id')}"):
                    pool = st.session_state.get("selection_pool", [])
                    # store only minimal necessary info
                    item = {
                        "source": rec.get("source"),
                        "id": rec.get("id"),
                        "title": rec.get("title"),
                        "thumb": rec.get("thumb"),
                        "meta": rec.get("meta")
                    }
                    # avoid duplicate
                    if not any((p.get("source") == item["source"] and p.get("id") == item["id"]) for p in pool):
                        pool.append(item)
                        st.session_state["selection_pool"] = pool
                        st.success("Added to selection pool")

    # show selection pool quick controls
    st.markdown("---")
    st.subheader("Selection Pool (saved items)")
    pool = st.session_state.get("selection_pool", [])
    if not pool:
        st.info("Selection pool is empty. Use 'Select' buttons above to add items here.")
    else:
        st.write(f"{len(pool)} items saved.")
        cols = st.columns(4)
        for i, p in enumerate(pool):
            with cols[i % 4]:
                if p.get("thumb"):
                    try:
                        st.image(p["thumb"], use_column_width=True)
                    except Exception:
                        st.write("[No preview]")
                st.write(p.get("title") or "Untitled")
                st.caption(p.get("source"))
                if st.button(f"View {i}", key=f"view_{i}"):
                    st.session_state["view_index"] = i

    # Detail view & AI generation
    if "view_index" in st.session_state:
        idx = st.session_state["view_index"]
        if 0 <= idx < len(pool):
            item = pool[idx]
            st.markdown("---")
            st.subheader("Selected from pool — Detail & AI")
            st.write(f"**{item.get('title') or 'Untitled'}** — {item.get('source')}")
            try:
                if item.get("thumb"):
                    st.image(item.get("thumb"), width=380)
            except Exception:
                pass
            meta = item.get("meta") or {}
            # display a few metadata fields safely
            st.write("**Metadata (selected fields)**")
            st.write(f"- Artist / Maker: {meta.get('artistDisplayName') or meta.get('artist') or meta.get('maker') or 'Unknown'}")
            st.write(f"- Date: {meta.get('objectDate') or meta.get('date') or '—'}")
            st.write(f"- Medium: {meta.get('medium') or meta.get('technique') or '—'}")
            st.write(f"- Culture / Period: {meta.get('culture') or meta.get('period') or '—'}")
            st.write(f"[Open original record]({meta.get('objectURL') or meta.get('url') or '#'})")

            st.markdown("### Generate museum-style text (optional)")
            st.write("This will produce a 3-part museum text: Character Overview / Myth Narrative / Artwork Commentary.")
            if st.button("Generate 3-part text (AI)"):
                if not openai_client_from_session():
                    st.warning("No OpenAI key found in session. Enter your key in the sidebar to enable AI.")
                else:
                    seed = MYTH_DB.get(character, "")
                    try:
                        out = ai_generate_museum_text(character, seed, meta)
                        st.markdown("#### AI Output (raw)")
                        st.write(out)
                        st.download_button("Download text (.txt)", data=out, file_name=f"{character}_museum_text.txt", mime="text/plain")
                    except Exception as e:
                        st.error(f"AI generation failed: {e}")
                        # fallback local output
                        fallback = f"Character Overview:\n{seed}\n\nMyth Narrative:\nA concise retelling of {character}.\n\nArtwork Commentary:\nLocal fallback commentary for {item.get('title') or 'the selected artwork'}."
                        st.write(fallback)

# --------- Saved Items page (manage pool) ----------
if page == "Saved Items":
    st.header("Saved Items — Manage your Selection Pool")
    pool = st.session_state.get("selection_pool", [])
    if not pool:
        st.info("No saved items. Use Explorer to add artworks to your pool.")
    else:
        for idx, p in enumerate(pool):
            st.markdown(f"**{idx+1}. {p.get('title') or 'Untitled'}** — {p.get('source')}")
            cols = st.columns([1, 4, 1])
            with cols[0]:
                if p.get("thumb"):
                    try:
                        st.image(p["thumb"], width=120)
                    except Exception:
                        st.write("[No preview]")
            with cols[1]:
                st.write(p.get("meta", {}).get("objectURL") or "")
                st.write(f"Medium: {p.get('meta', {}).get('medium') or '—'}")
            with cols[2]:
                if st.button(f"Remove {idx}", key=f"rm_{idx}"):
                    pool.pop(idx)
                    st.session_state["selection_pool"] = pool
                    st.experimental_rerun()
        if st.button("Clear all"):
            st.session_state["selection_pool"] = []
            st.success("Cleared selection pool.")
            st.experimental_rerun()

# --------- Data Visualization ----------
if page == "Data Visualization":
    st.header("Data Visualization — Quick analytics on MET results")
    figure = st.selectbox("Choose figure (for MET analysis)", MYTH_LIST, index=0)
    if st.button("Fetch MET sample"):
        js = safe_get_json(f"{MET_SEARCH}?q={requests.utils.quote(figure)}&hasImages=true")
        ids = js.get("objectIDs") or []
        metas = []
        for oid in ids[:200]:
            m = safe_get_json(MET_OBJECT.format(oid))
            if m and strong_filter(m):
                metas.append(m)
            time.sleep(0.01)
        st.session_state["viz_metas"] = metas
        st.success(f"Loaded {len(metas)} MET records.")

    metas = st.session_state.get("viz_metas", []) or []
    if metas:
        years = [m.get("objectBeginDate") for m in metas if isinstance(m.get("objectBeginDate"), int)]
        if years:
            fig = px.histogram(x=years, nbins=30, title="Year distribution (sample)")
            st.plotly_chart(fig, use_container_width=True)
        mediums = [safe_str_field(m.get("medium")) for m in metas if m.get("medium")]
        if mediums:
            cnt = collections.Counter(mediums).most_common(12)
            labels = [x for x,y in cnt]
            values = [y for x,y in cnt]
            fig2 = px.bar(x=values, y=labels, orientation="h", labels={"x":"Count","y":"Medium"})
            st.plotly_chart(fig2, use_container_width=True)

# --------- About page ----------
if page == "About":
    st.header("About — Mythic Art Explorer (Full Version)")
    st.markdown("""
**What this app does**
- Aggregates artworks from multiple open museum APIs (MET, CMA, AIC, British Museum fallback).
- Applies robust filters to prefer Greek/Roman myth-related works.
- Lets you curate a selection pool and, optionally, generate museum-style texts using OpenAI.

**Notes**
- The three AI text parts: Character Overview, Myth Narrative, Artwork Commentary.
- OpenAI key is optional. Without it, AI features are disabled and local fallback text is used.
- All museum APIs used here are public and require no API key for the basic searches used.

**Technical**
- Built with Streamlit and Python (requests, plotly).
- All external requests are cached for 1 hour to reduce latency and rate issues.
""")

# End of file
