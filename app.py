# final_app.py
"""
Mythic Art Explorer — Multi-Museum (MET + Harvard + Cleveland)
Features:
 - Multi-source search: MET (no key), Harvard (requires key), Cleveland (open)
 - Hybrid filtering (tag-strict OR medium/title/culture heuristics)
 - Unified metadata normalization across sources
 - AI museum-text generation (Overview / Narrative / Artwork Commentary) via OpenAI (safe via st.secrets)
 - Visual analytics: year distribution, mediums, cultures, size scatter, dominant color estimation
 - Safe behavior: graceful fallbacks if Harvard/OpenAI keys missing
Notes:
 - Put keys in Streamlit secrets for security:
   st.secrets["OPENAI_API_KEY"] = "sk-..."
   st.secrets["HARVARD_API_KEY"] = "demo-or-your-key"
"""

import io
import time
import json
import math
import requests
import streamlit as st
import plotly.express as px
from typing import List, Dict, Optional, Tuple
from collections import Counter
from PIL import Image
import numpy as np

# -------------------------
# Page config
# -------------------------
st.set_page_config(page_title="Mythic Art Explorer", layout="wide")
st.title("🧿 Mythic Art Explorer — MET + Harvard + Cleveland")

# -------------------------
# Utilities & caching
# -------------------------
@st.cache_data(ttl=60*60*24, show_spinner=False)
def safe_get(url, params=None, timeout=12):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

@st.cache_data(ttl=60*60*24, show_spinner=False)
def fetch_bytes(url, timeout=10):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

# -------------------------
# MET API helpers (no key)
# -------------------------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

def met_search_ids(q: str, max_results: int = 200) -> List[int]:
    try:
        res = safe_get(MET_SEARCH, params={"q": q, "hasImages": True})
        ids = res.get("objectIDs") or []
        return ids[:max_results]
    except:
        return []

def met_get_object(oid: int) -> Optional[Dict]:
    try:
        data = safe_get(MET_OBJECT.format(oid))
        return data
    except:
        return None

# -------------------------
# Harvard Art Museums API (requires key)
# docs: https://www.harvardartmuseums.org/collections/api
# -------------------------
HARVARD_BASE = "https://api.harvardartmuseums.org/object"

def harvard_search(q: str, apikey: str, max_results: int = 100) -> List[Dict]:
    out = []
    page = 1
    per_page = 50
    collected = 0
    while collected < max_results:
        params = {"apikey": apikey, "q": q, "size": per_page, "page": page}
        j = safe_get(HARVARD_BASE, params=params)
        if not j:
            break
        records = j.get("records") or []
        for r in records:
            out.append(r)
            collected += 1
            if collected >= max_results:
                break
        if not j.get("info", {}).get("next"):
            break
        page += 1
    return out

def normalize_harvard(rec: Dict) -> Dict:
    # Convert Harvard record to unified schema
    return {
        "source": "Harvard",
        "objectID": rec.get("id"),
        "title": rec.get("title"),
        "artist": ", ".join([p.get("name") for p in (rec.get("people") or [])]) if rec.get("people") else rec.get("people"),
        "date": rec.get("dated"),
        "culture": rec.get("culture"),
        "medium": rec.get("medium"),
        "dimensions": rec.get("dimensions"),
        "primaryImage": rec.get("primaryimageurl"),
        "primaryImageSmall": rec.get("primaryimageurl"),
        "objectURL": rec.get("url"),
        "tags": [{"term": t} for t in ([rec.get("classification")] if rec.get("classification") else [])],  # rough
        "raw": rec
    }

# -------------------------
# Cleveland Museum Open Access API (no key)
# docs: https://openaccess-api.clevelandart.org/
# -------------------------
CLEVELAND_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks"

def cleveland_search(q: str, max_results: int = 100) -> List[Dict]:
    out = []
    page = 1
    per_page = 50
    collected = 0
    while collected < max_results:
        params = {"q": q, "limit": per_page, "page": page}
        j = safe_get(CLEVELAND_SEARCH, params=params)
        if not j:
            break
        records = j.get("data") or []
        for r in records:
            out.append(r)
            collected += 1
            if collected >= max_results:
                break
        if not records:
            break
        page += 1
    return out

def normalize_cleveland(rec: Dict) -> Dict:
    # Convert Cleveland record to unified schema
    image = None
    if rec.get("images"):
        first = rec.get("images")[0]
        image = first.get("publicCaption") or first.get("iiif_base")
        # prefer iiif image
        if first.get("iiif_base"):
            image = first.get("iiif_base") + "/full/400,/0/default.jpg"
    tags = rec.get("tags") or []
    return {
        "source": "Cleveland",
        "objectID": rec.get("id"),
        "title": rec.get("title"),
        "artist": rec.get("creators")[0].get("description") if rec.get("creators") else None,
        "date": rec.get("creation_date"),
        "culture": rec.get("culture"),
        "medium": rec.get("technique") or rec.get("classification"),
        "dimensions": rec.get("measurements"),
        "primaryImage": image,
        "primaryImageSmall": image,
        "objectURL": rec.get("url"),
        "tags": [{"term": t.get("term")} for t in tags if isinstance(t, dict)],
        "raw": rec
    }

# -------------------------
# MET normalization
# -------------------------
def normalize_met(meta: Dict) -> Dict:
    return {
        "source": "MET",
        "objectID": meta.get("objectID"),
        "title": meta.get("title"),
        "artist": meta.get("artistDisplayName"),
        "date": meta.get("objectDate"),
        "culture": meta.get("culture"),
        "medium": meta.get("medium"),
        "dimensions": meta.get("dimensions"),
        "primaryImage": meta.get("primaryImage"),
        "primaryImageSmall": meta.get("primaryImageSmall"),
        "objectURL": meta.get("objectURL"),
        "tags": meta.get("tags") or [],
        "raw": meta
    }

# -------------------------
# Hybrid filtering (tag-strict OR heuristics)
# -------------------------
STRICT_TAGS = {
    "Greek Mythology", "Zeus", "Athena", "Perseus", "Medusa", "Heracles", "Hercules", "Theseus", "Orpheus",
    "Aphrodite", "Apollo", "Artemis", "Hermes", "Poseidon", "Hades", "Demeter", "Dionysus"
}

CHAR_KEYWORDS = [k.lower() for k in ["Zeus","Athena","Perseus","Medusa","Heracles","Theseus","Apollo","Artemis","Aphrodite","Hermes","Poseidon","Hades","Demeter","Dionysus","Orpheus"]]
MEDIUM_KEYWORDS = ["greek","hellenistic","classical","roman","amphora","vase","attic","terracotta","marble","bronze"]

def has_strict_tag(rec: Dict) -> bool:
    tags = rec.get("tags") or []
    for t in tags:
        if isinstance(t, dict):
            term = t.get("term") or t.get("name")
        else:
            term = t
        if term and term in STRICT_TAGS:
            return True
    return False

def medium_title_heuristic(rec: Dict) -> bool:
    title = (rec.get("title") or "").lower()
    culture = (rec.get("culture") or "").lower()
    medium = (rec.get("medium") or "").lower()
    # keywords in title or culture/medium
    if any(k in title for k in CHAR_KEYWORDS):
        return True
    if any(k in culture for k in MEDIUM_KEYWORDS):
        return True
    if any(k in medium for k in MEDIUM_KEYWORDS):
        return True
    return False

def passes_hybrid_filter(rec: Dict) -> bool:
    # rec is normalized
    if has_strict_tag(rec):
        return True
    if medium_title_heuristic(rec):
        return True
    # optionally reject obvious non-art categories
    classification = (rec.get("raw") or {}).get("classification") or ""
    department = (rec.get("raw") or {}).get("department") or ""
    reject_terms = ["costume", "photograph", "textile", "musical", "arms and armor", "jewelry"]
    if any(r in str(classification).lower() for r in reject_terms) or any(r in str(department).lower() for r in reject_terms):
        return False
    return False

# -------------------------
# OpenAI wrapper (safe via st.secrets)
# -------------------------
def openai_available() -> bool:
    try:
        _ = st.secrets["OPENAI_API_KEY"]
        return True
    except Exception:
        return bool(st.session_state.get("OPENAI_API_KEY"))

def get_openai_client():
    try:
        from openai import OpenAI
    except Exception:
        return None
    api_key = st.secrets.get("OPENAI_API_KEY") if "OPENAI_API_KEY" in st.secrets else st.session_state.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

def ai_generate_text(prompt: str, model: str = "gpt-4.1-mini", max_tokens: int = 400) -> str:
    client = get_openai_client()
    if not client:
        raise RuntimeError("OpenAI client not available")
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text or ""

# -------------------------
# Image helpers: dominant color, simple size parse
# -------------------------
def dominant_color_from_bytes(img_bytes: bytes, resize=64) -> str:
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img = img.resize((resize, resize))
        arr = np.array(img).reshape((-1,3))
        vals, counts = np.unique(arr.reshape(-1,3), axis=0, return_counts=True)
        idx = counts.argmax()
        rgb = tuple(vals[idx].tolist())
        return '#%02x%02x%02x' % rgb
    except Exception:
        return "#888888"

def extract_dimensions_simple(meta: Dict) -> Tuple[Optional[float], Optional[float]]:
    dims = meta.get("dimensions") or ""
    if not dims or not isinstance(dims, str):
        # try alternative fields
        raw = meta.get("raw") or {}
        if isinstance(raw, dict):
            dims = raw.get("dimensions") or raw.get("measurements") or ""
    # naive parse, look for "cm"
    try:
        s = dims.replace("cm", " ").replace("×", "x").replace("—", "x")
        parts = []
        for tok in s.replace(",", " ").split():
            try:
                parts.append(float(tok))
            except:
                continue
        if len(parts) >= 2:
            return (parts[0], parts[1])
    except:
        pass
    return (None, None)

# -------------------------
# Sidebar: keys & settings
# -------------------------
st.sidebar.title("Settings")
st.sidebar.markdown("Place API keys in Streamlit Secrets for production (recommended). You can also paste them for this session.")

if "OPENAI_API_KEY" not in st.session_state:
    st.session_state["OPENAI_API_KEY"] = None
if "HARVARD_API_KEY" not in st.session_state:
    st.session_state["HARVARD_API_KEY"] = None

harv_key_input = st.sidebar.text_input("Harvard API key (session)", type="password")
if st.sidebar.button("Save Harvard key to session"):
    if harv_key_input:
        st.session_state["HARVARD_API_KEY"] = harv_key_input
        st.sidebar.success("Harvard key saved to session.")
    else:
        st.sidebar.warning("Provide a key.")

openai_key_input = st.sidebar.text_input("OpenAI key (session)", type="password")
if st.sidebar.button("Save OpenAI key to session"):
    if openai_key_input:
        st.session_state["OPENAI_API_KEY"] = openai_key_input
        st.sidebar.success("OpenAI key saved to session.")
    else:
        st.sidebar.warning("Provide a key.")

st.sidebar.markdown("---")
page = st.sidebar.selectbox("Page", ["Home", "Explorer", "Stories", "Visual Analytics", "Lineages", "About"])

# -------------------------
# Page: Home
# -------------------------
if page == "Home":
    st.header("Welcome")
    st.write("""
This project searches museum APIs (MET, Harvard, Cleveland) for Greek & Roman myth-related artworks,
applies a hybrid filtering strategy to ensure both precision and recall, and provides tools for
AI-powered museum texts and visual analytics.
""")
    st.write("Workflow: Explorer → (select artworks) → Stories (curated + AI) → Visual Analytics")

# -------------------------
# Page: Explorer (multi-source, medium filter)
# -------------------------
elif page == "Explorer":
    st.header("Explorer — Multi-source search (medium recall, good precision)")
    character = st.text_input("Search term (person/keyword)", value="Athena")
    max_per_source = st.slider("Max per source", 20, 200, 100, step=10)
    use_met = st.checkbox("Search MET", True)
    use_harvard = st.checkbox("Search Harvard", True)
    use_cleveland = st.checkbox("Search Cleveland", True)

    if st.button("Search across sources"):
        unified = []
        progress = st.progress(0)
        sources = []
        if use_met:
            sources.append("MET")
            # search MET for several aliases
            aliases = [character, f"{character} myth", f"{character} greek", character + " vase"]
            met_ids = []
            for a in aliases:
                ids = met_search_ids(a, max_results=max_per_source)
                if ids:
                    for i in ids:
                        if i not in met_ids:
                            met_ids.append(i)
            # fetch MET objects
            for i, oid in enumerate(met_ids):
                m = met_get_object(oid)
                if m:
                    unified.append(normalize_met(m))
                progress.progress(min(100, int((len(unified)/ (max_per_source*3 + 1))*100)))
            time.sleep(0.1)

        if use_harvard:
            sources.append("Harvard")
            harv_key = st.secrets.get("HARVARD_API_KEY") if "HARVARD_API_KEY" in st.secrets else st.session_state.get("HARVARD_API_KEY")
            if not harv_key:
                st.warning("Harvard key missing — skipping Harvard. Put HARVARD_API_KEY in Streamlit secrets or session field.")
            else:
                harv_recs = harvard_search(f"title:{character} OR person:{character} OR {character}", apikey=harv_key, max_results=max_per_source)
                for rec in harv_recs:
                    unified.append(normalize_harvard(rec))
                time.sleep(0.1)

        if use_cleveland:
            sources.append("Cleveland")
            clev_recs = cleveland_search(character, max_results=max_per_source)
            for rec in clev_recs:
                unified.append(normalize_cleveland(rec))
            time.sleep(0.1)

        st.success(f"Collected {len(unified)} raw records from: {', '.join(sources)}")
        # now filter with hybrid
        filtered = []
        for rec in unified:
            if passes_hybrid_filter(rec):
                filtered.append(rec)
        st.session_state["last_unified"] = unified
        st.session_state["last_filtered"] = filtered
        st.write(f"After hybrid filtering: {len(filtered)} records")

    # Display results if available
    filtered = st.session_state.get("last_filtered", [])
    if not filtered:
        st.info("No filtered records yet. Use Search across sources.")
    else:
        st.write("Showing filtered artworks (click Select to mark for Stories / Visual Analytics)")
        cols = st.columns(3)
        for idx, rec in enumerate(filtered):
            with cols[idx % 3]:
                img = rec.get("primaryImageSmall") or rec.get("primaryImage")
                if img:
                    try:
                        st.image(img, use_column_width=True)
                    except:
                        st.write("[Image cannot load]")
                st.markdown(f"**{rec.get('title','Untitled')}**")
                st.write(f"{rec.get('artist') or ''} • {rec.get('date') or ''}")
                st.write(f"*{rec.get('medium') or ''}*")
                if st.button(f"Select {rec.get('source')}:{rec.get('objectID')}", key=f"sel_{rec.get('source')}_{rec.get('objectID')}"):
                    # store selected in session pool
                    pool = st.session_state.get("selection_pool", [])
                    pool.append(rec)
                    st.session_state["selection_pool"] = pool
                    st.success("Added to selection pool")

    # show selection pool
    pool = st.session_state.get("selection_pool", [])
    if pool:
        st.markdown("---")
        st.subheader("Selection pool (for Stories / Analytics)")
        for s in pool:
            st.write(f"- {s.get('title')} ({s.get('source')})")

# -------------------------
# Page: Stories (tag-precise + AI 3-part)
# -------------------------
elif page == "Stories":
    st.header("Stories — Curated (tag-precise) selection & AI 3-part text")
    st.write("This page prefers tag-precise retrieval; when tags are absent it falls back to our hybrid scoring.")

    # let user pick from selection_pool or search tag-precise
    pool = st.session_state.get("selection_pool", [])
    st.write("Selected artworks (session pool) or use 'Find by strict tags' to perform tag-precise search.")
    if pool:
        idx = st.selectbox("Choose from selection pool", list(range(len(pool))), format_func=lambda i: f"{pool[i].get('title')} — {pool[i].get('source')}")
        selected = pool[idx]
        st.markdown(f"**Selected: {selected.get('title')}**")
        if selected.get("primaryImage"):
            st.image(selected.get("primaryImage"), width=360)
    else:
        selected = None

    # Tag-precise search (user may want to search strictly by tag)
    tag_query = st.text_input("Tag-precise search (e.g., 'Athena' or 'Greek Mythology')", value="")
    if st.button("Find by strict tag"):
        results = []
        # search MET and Cleveland (Harvard is also searched if key present)
        met_ids = met_search_ids(tag_query, max_results=200)
        for oid in met_ids:
            m = met_get_object(oid)
            if m:
                n = normalize_met(m)
                if has_strict_tag := any(((t.get("term") if isinstance(t, dict) else t) in STRICT_TAGS) for t in n.get("tags", [])):
                    results.append(n)
                else:
                    # include if title/culture/medium match (secondary)
                    if medium_title_heuristic(n):
                        results.append(n)
        # Cleveland
        clev = cleveland_search(tag_query, max_results=200)
        for r in clev:
            n = normalize_cleveland(r)
            if has_strict_tag := any(((t.get("term") if isinstance(t, dict) else t) in STRICT_TAGS) for t in n.get("tags", [])):
                results.append(n)
            else:
                if medium_title_heuristic(n):
                    results.append(n)
        st.session_state["tag_strict_results"] = results
        st.success(f"Found {len(results)} results for tag-precise query")
    tag_results = st.session_state.get("tag_strict_results", [])
    if tag_results:
        for i, r in enumerate(tag_results[:30]):
            st.markdown(f"**{r.get('title')}** — {r.get('source')}")
            if r.get("primaryImageSmall"):
                try:
                    st.image(r.get("primaryImageSmall"), width=220)
                except:
                    st.write("[image failed]")
            if st.button(f"Select tag result {i}", key=f"tagsel_{i}"):
                pool = st.session_state.get("selection_pool", [])
                pool.append(r)
                st.session_state["selection_pool"] = pool
                st.success("Added to selection pool")

    # If selected, allow AI generation
    selected = st.session_state.get("selection_pool", [None])[0] if pool else None
    if selected:
        st.markdown("---")
        st.subheader("Generate museum texts for selected artwork")
        st.write("Will produce: Character Overview (short), Myth Narrative (evocative), Artwork Commentary (analysis).")
        if st.button("Generate AI 3-part text"):
            if not openai_available() and not st.session_state.get("OPENAI_API_KEY"):
                st.warning("OpenAI key missing. Add to Streamlit secrets or enter in sidebar.")
            else:
                # prepare character hint by trying to extract likely character keywords
                title = (selected.get("title") or "").lower()
                likely = [k for k in CHAR_KEYWORDS if k in title]
                hero = likely[0].capitalize() if likely else st.text_input("If not detected, type the character for narrative:", value="Athena")
                prompt = f"""
You are an art historian and museum curator. Produce three labeled sections separated by '---':

1) Character Overview — 1-2 sentences introducing {hero} suitable for a museum panel.

2) Myth Narrative — 3-6 sentences, emotive audio-guide tone retelling a key myth of {hero}.

3) Artwork Commentary — 3-6 sentences analyzing the selected artwork:
Title: {selected.get('title')}
Artist: {selected.get('artist')}
Date: {selected.get('date')}
Medium: {selected.get('medium')}
Discuss composition, lighting, symbolism, and link to the myth. Keep language accessible.

Return sections separated by '---'.
"""
                try:
                    out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=700)
                except Exception as e:
                    out = f"[AI generation failed: {e}]"
                if isinstance(out, str) and '---' in out:
                    parts = [p.strip() for p in out.split('---') if p.strip()]
                    for p in parts:
                        if p.lower().startswith("1") or "overview" in p.lower():
                            st.markdown("### Character Overview")
                            st.write(p)
                        elif p.lower().startswith("2") or "narrative" in p.lower():
                            st.markdown("### Myth Narrative")
                            st.write(p)
                        elif p.lower().startswith("3") or "commentary" in p.lower():
                            st.markdown("### Artwork Commentary")
                            st.write(p)
                        else:
                            st.write(p)
                else:
                    st.write(out)
                st.download_button("Download museum text", data=out, file_name="museum_text.txt", mime="text/plain")

# -------------------------
# Page: Visual Analytics
# -------------------------
elif page == "Visual Analytics":
    st.header("Visual Analytics — analyze selected dataset")
    pool = st.session_state.get("selection_pool", [])
    if not pool:
        st.info("No artworks in selection pool. Use Explorer or Stories to add artworks.")
    else:
        st.write(f"Analyzing {len(pool)} selected artworks.")
        # compute distributions
        years = []
        cultures = []
        mediums = []
        colors = []
        sizes_w = []
        sizes_h = []
        p = st.progress(0)
        for i, rec in enumerate(pool):
            meta = rec
            # year
            y = None
            try:
                raw = (meta.get("raw") or {})
                yval = raw.get("objectBeginDate") or raw.get("creation_date") or raw.get("dated") or meta.get("date")
                if isinstance(yval, int):
                    y = yval
                elif isinstance(yval, str) and yval.strip().isdigit():
                    y = int(yval.strip())
                if y:
                    years.append(y)
            except:
                pass
            # culture/medium
            if meta.get("culture"):
                cultures.append(meta.get("culture"))
            if meta.get("medium"):
                mediums.append(meta.get("medium"))
            # dimensions
            w,h = extract_dimensions_simple(meta)
            if w: sizes_w.append(w)
            if h: sizes_h.append(h)
            # dominant color
            img = meta.get("primaryImageSmall") or meta.get("primaryImage")
            if img:
                b = fetch_bytes(img)
                if b:
                    colors.append(dominant_color_from_bytes(b))
                else:
                    colors.append("#888888")
            else:
                colors.append("#888888")
            if i % 2 == 0:
                p.progress(min(100, int((i+1)/len(pool)*100)))
            time.sleep(0.001)
        p.empty()

        if years:
            fig = px.histogram(x=years, nbins=20, labels={"x":"Year","y":"Count"}, title="Year distribution")
            st.plotly_chart(fig, use_container_width=True)
        if cultures:
            topc = Counter(cultures).most_common(10)
            fig2 = px.pie(values=[v for _,v in topc], names=[k for k,_ in topc], title="Culture / Origin (top)")
            st.plotly_chart(fig2, use_container_width=True)
        if mediums:
            topm = Counter(mediums).most_common(12)
            fig3 = px.bar(x=[v for _,v in topm], y=[k for k,_ in topm], orientation='h', labels={"x":"Count","y":"Medium"}, title="Mediums (top)")
            st.plotly_chart(fig3, use_container_width=True)
        if sizes_w and sizes_h:
            fig4 = px.scatter(x=sizes_w, y=sizes_h, labels={"x":"Width (approx)","y":"Height (approx)"}, title="Dimensions scatter (approx)")
            st.plotly_chart(fig4, use_container_width=True)

        # show color swatches
        st.markdown("### Dominant color swatches")
        cols = st.columns(min(8, len(colors)))
        for i, c in enumerate(colors[:8]):
            with cols[i]:
                st.markdown(f"<div style='height:80px;background:{c};border-radius:6px;'></div>", unsafe_allow_html=True)
                st.write(c)

        # export CSV
        if st.button("Export selection summary CSV"):
            import csv, io
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["source","objectID","title","artist","date","culture","medium","image","dominantColor"])
            for rec, c in zip(pool, colors):
                w.writerow([rec.get("source"), rec.get("objectID"), rec.get("title"), rec.get("artist"), rec.get("date"), rec.get("culture"), rec.get("medium"), rec.get("primaryImageSmall") or rec.get("primaryImage"), c])
            st.download_button("Download CSV", data=out.getvalue(), file_name="selection_summary.csv", mime="text/csv")

# -------------------------
# Page: Lineages
# -------------------------
elif page == "Lineages":
    st.header("Mythic Lineages — concise panel")
    st.write("Key parentage & relationships (museum-style bullets).")
    RELS = [
        ("Chaos","Gaia","parent"),
        ("Gaia","Uranus","parent"),
        ("Uranus","Cronus","parent"),
        ("Cronus","Zeus","parent"),
        ("Zeus","Athena","parent"),
        ("Zeus","Apollo","parent"),
        ("Zeus","Artemis","parent"),
        ("Zeus","Ares","parent"),
        ("Zeus","Hermes","parent"),
    ]
    for a,b,r in RELS:
        st.markdown(f"🔹 **{a} → {b}**  —  { 'Parentage' if r=='parent' else r }")

    if st.button("Generate AI panel intro"):
        if not openai_available() and not st.session_state.get("OPENAI_API_KEY"):
            st.warning("OpenAI key missing. Showing local fallback panel.")
            st.write("This panel shows a compact genealogy of early Greek mythic figures; parental lines indicate transmission of domains and functions.")
        else:
            prompt = "Write a concise museum-panel introduction (3-5 sentences) about Greek myth genealogy connecting primordial beings to Olympians."
            try:
                out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=200)
                st.markdown("### AI Panel Intro")
                st.write(out)
            except Exception as e:
                st.error(f"AI failed: {e}")

# -------------------------
# Page: About
# -------------------------
elif page == "About":
    st.header("About this app")
    st.write("""
    Mythic Art Explorer — multi-source edition.
    Sources: MET (no key), Harvard (requires key), Cleveland Open Access (no key).
    Filtering: hybrid (strict tag OR medium/title/culture heuristics).
    AI: optional via OpenAI (put OPENAI_API_KEY in Streamlit secrets or paste into sidebar for session).
    """)
    st.write("If you want, I can now (A) change layout to waterfall, (B) add slideshow, or (C) further tune filters.")

# End of file
