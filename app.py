# final_app.py
"""
Mythic Art Explorer — Multi-Museum (MET + AIC + Cleveland + British Museum + Rijksmuseum)
Mode: A — 全自动搜索 5 家博物馆（推荐）
Features:
 - Multi-source search: MET (no key), AIC (no key), Cleveland (no key), British Museum (public collection API), Rijksmuseum (needs free key)
 - Hybrid Tag+Medium filtering for Greek/Roman myth relevance
 - Selection pool, Stories (AI Museum Label / Myth Narrative / Artwork Commentary) — optional OpenAI
 - Visual analytics (simple)
 - Sidebar clearly shows which APIs require a key (Rijksmuseum only)
Notes:
 - Put keys in Streamlit secrets for production:
     st.secrets["OPENAI_API_KEY"] = "sk-..."
     st.secrets["RIJKSMUSEUM_KEY"] = "your-rijks-key"
 - Or paste them in the sidebar for the session.
"""

import streamlit as st
import requests
import time
import json
from collections import Counter
from typing import List, Dict, Optional, Tuple
import plotly.express as px
import io
from PIL import Image
import numpy as np

# -------------------------
# Page config & header
# -------------------------
st.set_page_config(page_title="Mythic Art Explorer — Multi-Museum", layout="wide")
st.title("🏛 Mythic Art Explorer — MET + AIC + Cleveland + British Museum + Rijksmuseum")

st.markdown("""
**Mode A — 全自动搜索 5 家博物馆（推荐）**  
本页会同时检索：MET（无需 key）、Art Institute of Chicago（无需 key）、Cleveland Museum Open Access（无需 key）、British Museum（公开 collection API）、Rijksmuseum（需免费注册 key）。  
在侧边栏中你可以把 **Rijksmuseum Key** 与 **OpenAI Key**（可选）放入 `st.secrets` 或临时输入来启用高级功能。
""")

# -------------------------
# network helpers (cached)
# -------------------------
@st.cache_data(ttl=60*60*24, show_spinner=False)
def safe_get_json(url: str, params: dict = None, timeout: int = 12) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

@st.cache_data(ttl=60*60*24, show_spinner=False)
def fetch_bytes(url: str, timeout: int = 10):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

# -------------------------
# MET helpers (no key)
# -------------------------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

def met_search_ids(q: str, max_results: int = 200) -> List[int]:
    res = safe_get_json(MET_SEARCH, params={"q": q, "hasImages": True})
    if not res:
        return []
    ids = res.get("objectIDs") or []
    return ids[:max_results]

def met_get_object(oid: int) -> Optional[dict]:
    return safe_get_json(MET_OBJECT.format(oid))

def normalize_met(meta: dict) -> dict:
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
# Art Institute of Chicago (AIC) helpers (no key)
# docs: https://api.artic.edu/docs/
# -------------------------
AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search"

def aic_search(q: str, max_results: int = 100) -> List[dict]:
    params = {"q": q, "limit": max_results, "fields": "id,title,artist_display,date_display,image_id,place_of_origin,classification,thumbnail"}
    res = safe_get_json("https://api.artic.edu/api/v1/artworks/search", params=params)
    if not res:
        return []
    ids = [d.get("id") for d in res.get("data", []) if d.get("id")]
    # fetch details for ids (batch)
    out = []
    for i in ids[:max_results]:
        rec = safe_get_json(f"https://api.artic.edu/api/v1/artworks/{i}", params={"fields":"id,title,artist_display,date_display,image_id,place_of_origin,classification,thumbnail"})
        if rec and rec.get("data"):
            out.append(rec["data"])
    return out

def normalize_aic(rec: dict) -> dict:
    image_id = rec.get("image_id")
    image = f"https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg" if image_id else None
    return {
        "source": "AIC",
        "objectID": rec.get("id"),
        "title": rec.get("title"),
        "artist": rec.get("artist_display"),
        "date": rec.get("date_display"),
        "culture": rec.get("place_of_origin"),
        "medium": rec.get("classification"),
        "dimensions": None,
        "primaryImage": image,
        "primaryImageSmall": image,
        "objectURL": f"https://www.artic.edu/artworks/{rec.get('id')}",
        "tags": [],
        "raw": rec
    }

# -------------------------
# Cleveland Museum of Art (Open Access)
# docs: https://openaccess-api.clevelandart.org/
# -------------------------
CLEVELAND_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks"

def cleveland_search(q: str, max_results: int = 100) -> List[dict]:
    out = []
    page = 1
    per = 50
    collected = 0
    while collected < max_results:
        res = safe_get_json(CLEVELAND_SEARCH, params={"q": q, "limit": per, "page": page})
        if not res:
            break
        data = res.get("data") or []
        for r in data:
            out.append(r)
            collected += 1
            if collected >= max_results:
                break
        if not data:
            break
        page += 1
    return out

def normalize_cleveland(rec: dict) -> dict:
    img = None
    if rec.get("images"):
        first = rec.get("images")[0]
        if first.get("iiif_base"):
            img = first.get("iiif_base") + "/full/400,/0/default.jpg"
        else:
            img = first.get("publicCaption")
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
        "primaryImage": img,
        "primaryImageSmall": img,
        "objectURL": rec.get("url"),
        "tags": [{"term": t.get("term")} for t in tags if isinstance(t, dict)],
        "raw": rec
    }

# -------------------------
# British Museum (public collection API; no key)
# docs: https://collectionapi.britishmuseum.org/  (public endpoints)
# -------------------------
BM_SEARCH = "https://collectionapi.britishmuseum.org/object"  # note: sometimes returns single object; we'll use search-like endpoint via q param

def british_search(q: str, max_results: int = 100) -> List[dict]:
    # The BM API sometimes exposes search via 'q' param; fallback if fails
    out = []
    res = safe_get_json("https://collectionapi.britishmuseum.org/search", params={"q": q})
    if not res:
        return []
    hits = res.get("hits") or []
    ids = [h.get("object_id") for h in hits][:max_results]
    for oid in ids:
        rec = safe_get_json(f"https://collectionapi.britishmuseum.org/object/{oid}")
        if rec:
            out.append(rec)
    return out

def normalize_british(rec: dict) -> dict:
    # British Museum fields vary; be conservative
    img = None
    if rec.get("primaryImage"):
        img = rec.get("primaryImage")
    elif rec.get("images"):
        imgs = rec.get("images")
        if imgs and isinstance(imgs, list) and imgs[0].get("url"):
            img = imgs[0].get("url")
    return {
        "source": "BritishMuseum",
        "objectID": rec.get("object_id") or rec.get("id"),
        "title": rec.get("title"),
        "artist": rec.get("maker"),
        "date": rec.get("date"),
        "culture": rec.get("culture"),
        "medium": rec.get("materials"),
        "dimensions": rec.get("dimensions"),
        "primaryImage": img,
        "primaryImageSmall": img,
        "objectURL": rec.get("object_url") or rec.get("url"),
        "tags": rec.get("tags") or [],
        "raw": rec
    }

# -------------------------
# Rijksmuseum (requires free key) — optional
# docs: https://www.rijksmuseum.nl/en/api
# -------------------------
RIJK_BASE = "https://www.rijksmuseum.nl/api/en/collection"

def rijks_search(q: str, apikey: str, max_results: int = 100) -> List[dict]:
    out = []
    per_page = 50
    page = 1
    collected = 0
    while collected < max_results:
        params = {"key": apikey, "q": q, "p": page, "ps": per_page, "imgonly": True}
        res = safe_get_json(RIJK_BASE, params=params)
        if not res:
            break
        data = res.get("artObjects") or []
        for a in data:
            out.append(a)
            collected += 1
            if collected >= max_results:
                break
        if not data:
            break
        page += 1
    return out

def normalize_rijks(rec: dict) -> dict:
    img = rec.get("webImage", {}).get("url")
    return {
        "source": "Rijksmuseum",
        "objectID": rec.get("objectNumber"),
        "title": rec.get("title"),
        "artist": rec.get("principalMaker"),
        "date": rec.get("dating", {}).get("presentingDate"),
        "culture": None,
        "medium": rec.get("physicalMedium"),
        "dimensions": rec.get("dimensions"),
        "primaryImage": img,
        "primaryImageSmall": img,
        "objectURL": rec.get("links", {}).get("web"),
        "tags": [],
        "raw": rec
    }

# -------------------------
# Hybrid Filter for Greek/Roman myth relevance
# -------------------------
STRICT_TAGS = {"Greek Mythology", "Roman", "Zeus", "Athena", "Perseus", "Medusa", "Heracles", "Theseus", "Apollo", "Artemis", "Aphrodite", "Hermes", "Poseidon", "Hades", "Demeter", "Dionysus", "Orpheus", "Narcissus"}

CHAR_KEYWORDS = [k.lower() for k in ["zeus","athena","perseus","medusa","heracles","theseus","apollo","artemis","aphrodite","hermes","poseidon","hades","demeter","dionysus","orpheus","narcissus"]]
MEDIUM_KEYWORDS = ["greek","hellenistic","classical","roman","amphora","vase","terracotta","marble","bronze","attic","red-figure","black-figure"]

def rec_has_strict_tag(rec: dict) -> bool:
    tags = rec.get("tags") or []
    for t in tags:
        if isinstance(t, dict):
            term = t.get("term") or t.get("name")
        else:
            term = t
        if term and any(term.strip().lower() == s.lower() for s in STRICT_TAGS):
            return True
    return False

def rec_medium_title_heuristic(rec: dict) -> bool:
    title = (rec.get("title") or "").lower()
    culture = (rec.get("culture") or "").lower() if rec.get("culture") else ""
    medium = (rec.get("medium") or "").lower() if rec.get("medium") else ""
    if any(k in title for k in CHAR_KEYWORDS):
        return True
    if any(k in culture for k in MEDIUM_KEYWORDS):
        return True
    if any(k in medium for k in MEDIUM_KEYWORDS):
        return True
    return False

def passes_hybrid(rec: dict) -> bool:
    if rec_has_strict_tag(rec):
        return True
    if rec_medium_title_heuristic(rec):
        return True
    # reject obvious modern/non-art
    classification = str((rec.get("raw") or {}).get("classification") or "").lower()
    dept = str((rec.get("raw") or {}).get("department") or "").lower()
    rejects = ["costume","textile","photograph","musical","arms and armor","jewelry"]
    if any(r in classification for r in rejects) or any(r in dept for r in rejects):
        return False
    return False

# -------------------------
# OpenAI wrapper (optional) — read from st.secrets or session
# -------------------------
def openai_available() -> bool:
    try:
        if "OPENAI_API_KEY" in st.secrets and st.secrets["OPENAI_API_KEY"]:
            return True
    except Exception:
        pass
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
# Small utilities: dominant color
# -------------------------
def dominant_color_hex_from_image_bytes(b: bytes) -> str:
    try:
        im = Image.open(io.BytesIO(b)).convert("RGB")
        im = im.resize((64,64))
        arr = np.array(im).reshape((-1, 3))
        vals, counts = np.unique(arr, axis=0, return_counts=True)
        idx = counts.argmax()
        rgb = tuple(vals[idx].tolist())
        return '#%02x%02x%02x' % rgb
    except Exception:
        return "#888888"

# -------------------------
# Sidebar: keys & options
# -------------------------
st.sidebar.header("Config & Keys")
st.sidebar.markdown("Rijksmuseum requires a free API key (register on rijksmuseum.nl). Put it in Streamlit secrets under `RIJKSMUSEUM_KEY` or paste here for session.")
rijks_key_input = st.sidebar.text_input("Rijksmuseum key (session)", type="password")
if st.sidebar.button("Save Rijks key to session"):
    st.session_state["RIJKSMUSEUM_KEY"] = rijks_key_input
    st.sidebar.success("Rijks key saved to session (session only).")

st.sidebar.markdown("---")
st.sidebar.markdown("OpenAI key (optional): place in st.secrets['OPENAI_API_KEY'] or paste here to enable AI features.")
openai_input = st.sidebar.text_input("OpenAI key (session)", type="password")
if st.sidebar.button("Save OpenAI key to session"):
    st.session_state["OPENAI_API_KEY"] = openai_input
    st.sidebar.success("OpenAI key saved to session.")

st.sidebar.markdown("---")
st.sidebar.markdown("Search mode: A (All 5 sources, automatic hybrid filter).")
page = st.sidebar.selectbox("Page", ["Home","Explorer","Stories","Analytics","Lineages","About"], index=1)

# -------------------------
# Home
# -------------------------
if page == "Home":
    st.header("About this multi-museum explorer")
    st.write("""
This app searches multiple open museum APIs for Greek & Roman myth-related artworks,
applies a hybrid Tag+Medium heuristic to filter results, and provides AI-assisted museum texts (optional).
Data sources: MET, Art Institute of Chicago (AIC), Cleveland Museum Open Access, British Museum (public), Rijksmuseum (optional key).
""")
    st.write("If you use Rijksmuseum or OpenAI features, please put keys into the sidebar or st.secrets for safety.")

# -------------------------
# Explorer (Mode A: auto search all five)
# -------------------------
elif page == "Explorer":
    st.header("Explorer — Search across 5 museums (Mode A)")
    q = st.text_input("Search term (example: Athena, Perseus, Zeus)", value="Athena")
    max_per_source = st.slider("Max results per source", 20, 100, 60, step=10)

    if st.button("Search all sources"):
        st.info("Searching MET / AIC / Cleveland / British Museum / Rijksmuseum (if key)...")
        results_unified = []

        # MET
        try:
            aliases = [q, f"{q} myth", f"{q} greek", f"{q} vase"]
            met_ids = []
            for a in aliases:
                ids = met_search_ids(a, max_results=max_per_source)
                for i in ids:
                    if i not in met_ids:
                        met_ids.append(i)
            for oid in met_ids[:max_per_source]:
                m = met_get_object(oid)
                if m:
                    results_unified.append(normalize_met(m))
        except Exception:
            pass

        # AIC
        try:
            aic_recs = aic_search(q, max_results=max_per_source)
            for r in aic_recs:
                results_unified.append(normalize_aic(r))
        except Exception:
            pass

        # Cleveland
        try:
            clev_recs = cleveland_search(q, max_results=max_per_source)
            for r in clev_recs:
                results_unified.append(normalize_cleveland(r))
        except Exception:
            pass

        # British Museum
        try:
            bm_recs = british_search(q, max_results=max_per_source)
            for r in bm_recs:
                results_unified.append(normalize_british(r))
        except Exception:
            pass

        # Rijksmuseum (optional)
        rijks_key = st.secrets.get("RIJKSMUSEUM_KEY") if "RIJKSMUSEUM_KEY" in st.secrets else st.session_state.get("RIJKSMUSEUM_KEY")
        if rijks_key:
            try:
                rijks_recs = rijks_search(q, apikey=rijks_key, max_results=max_per_source)
                for r in rijks_recs:
                    results_unified.append(normalize_rijks(r))
            except Exception:
                pass
        else:
            st.info("Rijksmuseum key not provided — skipping Rijksmuseum. (Put key in sidebar or st.secrets)")

        st.session_state["raw_unified"] = results_unified
        # de-duplicate by (source, objectID) or by title+artist
        unique = []
        seen = set()
        for r in results_unified:
            key = f"{r.get('source')}::{r.get('objectID')}" or (r.get('title','') + '::' + str(r.get('artist','')))
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
        st.session_state["unified_unique"] = unique
        st.success(f"Collected {len(results_unified)} raw records; {len(unique)} unique after basic dedupe.")

        # apply hybrid filter
        filtered = [r for r in unique if passes_hybrid(r)]
        st.session_state["filtered_results"] = filtered
        st.success(f"Filtered results (hybrid): {len(filtered)} artworks.")

    # show filtered
    filtered = st.session_state.get("filtered_results", [])
    if not filtered:
        st.info("No filtered results yet. Click 'Search all sources'.")
    else:
        st.write(f"Showing {len(filtered)} filtered artworks. Click Select to add to your session pool.")
        cols = st.columns(3)
        for i, rec in enumerate(filtered[:60]):
            with cols[i%3]:
                img = rec.get("primaryImageSmall") or rec.get("primaryImage")
                if img:
                    try:
                        st.image(img, use_column_width=True)
                    except:
                        st.write("[image load failed]")
                st.markdown(f"**{rec.get('title','Untitled')}**")
                st.write(f"{rec.get('artist') or ''} • {rec.get('date') or ''}")
                st.write(f"*{rec.get('medium') or ''}* • {rec.get('source')}")
                if st.button(f"Select {rec.get('source')}:{rec.get('objectID')}", key=f"sel_{i}"):
                    pool = st.session_state.get("selection_pool", [])
                    pool.append(rec)
                    st.session_state["selection_pool"] = pool
                    st.success("Added to selection pool")

    # session pool summary
    pool = st.session_state.get("selection_pool", [])
    if pool:
        st.markdown("---")
        st.subheader("Selection Pool")
        for idx, p in enumerate(pool):
            st.write(f"{idx+1}. {p.get('title')} — {p.get('source')}")

# -------------------------
# Stories: generate 3-part museum text (AI optional)
# -------------------------
elif page == "Stories":
    st.header("Stories — AI-assisted museum texts (Character Overview / Myth Narrative / Artwork Commentary)")
    st.write("Choose one artwork from your selection pool or use tag-precise searches in Explorer first.")

    pool = st.session_state.get("selection_pool", [])
    if not pool:
        st.info("Selection pool is empty. Go to Explorer and add items.")
    else:
        idx = st.selectbox("Pick an artwork from selection pool", list(range(len(pool))), format_func=lambda i: f"{pool[i].get('title')} — {pool[i].get('source')}")
        selected = pool[idx]
        st.subheader(selected.get("title"))
        if selected.get("primaryImage"):
            try:
                st.image(selected.get("primaryImage"), width=360)
            except:
                pass
        st.write(f"{selected.get('artist')} • {selected.get('date')} • {selected.get('medium')} • {selected.get('source')}")
        st.markdown("---")

        # auto-detect character by title keywords
        title_text = (selected.get("title") or "").lower()
        detected = [k for k in CHAR_KEYWORDS if k in title_text]
        default_character = detected[0].capitalize() if detected else "Athena"
        character = st.text_input("Character for narrative (detected by title or type manually)", value=default_character)

        if st.button("Generate 3-part museum text (AI)"):
            # prepare prompt
            seed = f"Short label seed for {character}."  # simple fallback
            prompt = f"""
You are an art historian and museum curator. Produce three labeled sections separated by '---':

1) Character Overview — 1-2 sentences introducing {character} (concise).

2) Myth Narrative — 3-6 sentences, evocative museum audio-guide tone retelling a key myth of {character}.

3) Artwork Commentary — 3-6 sentences analyzing the selected artwork:
Title: {selected.get('title')}
Artist: {selected.get('artist')}
Date: {selected.get('date')}
Medium: {selected.get('medium')}
Discuss composition, lighting, symbolism, and link to the myth. Keep language accessible to students and visitors.

Return the three sections separated by '---'.
"""
            if not openai_available():
                st.warning("OpenAI key missing. Put it into st.secrets['OPENAI_API_KEY'] or paste in sidebar to enable AI.")
                # local fallback
                st.markdown("### Character Overview")
                st.write(f"{character}: brief overview (fallback — AI not available).")
                st.markdown("### Myth Narrative")
                st.write(f"Short myth summary about {character} (fallback).")
                st.markdown("### Artwork Commentary")
                st.write("Short commentary linking image and myth (fallback).")
            else:
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

# -------------------------
# Analytics: simple visual summary of selection pool
# -------------------------
elif page == "Analytics":
    st.header("Visual Analytics — selection pool summary")
    pool = st.session_state.get("selection_pool", [])
    if not pool:
        st.info("No artworks selected yet.")
    else:
        st.write(f"Analyzing {len(pool)} artworks.")
        years = []
        cultures = []
        mediums = []
        colors = []
        for rec in pool:
            try:
                raw = rec.get("raw") or {}
                year = raw.get("objectBeginDate") or raw.get("creation_date") or raw.get("dated")
                if isinstance(year, int):
                    years.append(year)
                elif isinstance(year, str) and year.strip().isdigit():
                    years.append(int(year.strip()))
            except:
                pass
            if rec.get("culture"):
                cultures.append(rec.get("culture"))
            if rec.get("medium"):
                mediums.append(rec.get("medium"))
            img_url = rec.get("primaryImageSmall") or rec.get("primaryImage")
            if img_url:
                b = fetch_bytes(img_url)
                if b:
                    colors.append(dominant_color_hex_from_image_bytes(b))
        if years:
            fig = px.histogram(x=years, nbins=20, title="Year distribution")
            st.plotly_chart(fig, use_container_width=True)
        if cultures:
            top = Counter(cultures).most_common(8)
            fig = px.pie(values=[c for _,c in top], names=[k for k,_ in top], title="Cultures (top)")
            st.plotly_chart(fig, use_container_width=True)
        if mediums:
            topm = Counter(mediums).most_common(12)
            fig = px.bar(x=[c for _,c in topm], y=[k for k,_ in topm], orientation='h', labels={"x":"Count","y":"Medium"})
            st.plotly_chart(fig, use_container_width=True)
        if colors:
            st.markdown("### Dominant color swatches (sample)")
            cols = st.columns(min(8, len(colors)))
            for i, c in enumerate(colors[:8]):
                with cols[i]:
                    st.markdown(f"<div style='height:80px;background:{c};border-radius:6px;'></div>", unsafe_allow_html=True)
                    st.write(c)

# -------------------------
# Lineages: simple museum-style bullets
# -------------------------
elif page == "Lineages":
    st.header("Mythic Lineages — concise museum bullets")
    RELS = [
        ("Chaos","Gaia","parent"),
        ("Gaia","Uranus","parent"),
        ("Uranus","Cronus","parent"),
        ("Cronus","Zeus","parent"),
        ("Zeus","Athena","parent"),
        ("Zeus","Apollo","parent"),
        ("Zeus","Artemis","parent"),
    ]
    for a,b,r in RELS:
        if r == "parent":
            st.markdown(f"🔹 **{a} → {b}** — {a} is a progenitor whose attributes inform the domains embodied by {b}.")
        else:
            st.markdown(f"🔹 **{a} → {b}** — {r}")

    if st.button("Generate AI panel intro"):
        if not openai_available():
            st.warning("OpenAI key missing — showing local fallback.")
            st.write("This panel shows a compact genealogy from primordial beings to early Olympians. Parent-child lines indicate transmission of roles and attributes.")
        else:
            try:
                prompt = "Write a concise museum-panel introduction (3-5 sentences) about Greek myth genealogy connecting primordial beings to Olympians."
                out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=200)
                st.write(out)
            except Exception as e:
                st.error(f"AI failed: {e}")

# -------------------------
# About
# -------------------------
elif page == "About":
    st.header("About & Keys")
    st.markdown("""
**Data sources included:**  
- MET Museum API (no key)  
- Art Institute of Chicago API (no key)  
- Cleveland Museum Open Access API (no key)  
- British Museum public collection API (no key)  
- Rijksmuseum API (**requires free key**)

**Keys:**  
- **Rijksmuseum**: obtain a free key at https://www.rijksmuseum.nl/en/api (put key in Streamlit secrets as `RIJKSMUSEUM_KEY` or paste into sidebar)  
- **OpenAI** (optional, for AI text generation): place your `OPENAI_API_KEY` in Streamlit secrets as `OPENAI_API_KEY` or paste into sidebar to enable AI features.

If you want, I can also:
- Convert AI outputs to bilingual (EN/中文) automatically.
- Change gallery layout to masonry/pinterest style.
- Produce a printable PDF presentation summarizing the project.
""")

# -------------------------
# End of file
# -------------------------
