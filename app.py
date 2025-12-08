# final_app.py
"""
Mythic Art Explorer — Unified Explorer + Stories (English UI)
Search across multiple open museum APIs (MET, AIC, Cleveland, British Museum, Rijksmuseum)
Mode: Automatic (all sources)
- Rijksmuseum requires a free key (put in st.secrets or sidebar)
- OpenAI is optional for AI text generation (put in st.secrets or sidebar)
"""

import streamlit as st
import requests
import time
import json
from typing import List, Dict, Optional
from collections import Counter
from PIL import Image
import io

# Optional plotting
try:
    import plotly.express as px
except Exception:
    px = None

# ---- Page config ----
st.set_page_config(page_title="Mythic Art Explorer — Unified", layout="wide")
st.title("🏛 Mythic Art Explorer — Unified Explorer & Stories")
st.markdown(
    "Search multiple museum APIs for Greek/Roman myth-related artworks and generate a museum-style Myth Narrative and Artwork Commentary (AI optional)."
)

# ---- Utilities: network with caching ----
@st.cache_data(ttl=60*60*24, show_spinner=False)
def safe_get_json(url: str, params: dict = None, timeout: int = 12) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

@st.cache_data(ttl=60*60*24, show_spinner=False)
def safe_get_bytes(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

# ---- Data sources endpoints & normalizers ----
# MET
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

def met_search_ids(q: str, max_results: int = 200) -> List[int]:
    res = safe_get_json(MET_SEARCH, params={"q": q, "hasImages": True})
    if not res:
        return []
    return (res.get("objectIDs") or [])[:max_results]

def met_get_object(oid: int) -> Optional[dict]:
    return safe_get_json(MET_OBJECT.format(oid))

def normalize_met(meta: dict) -> dict:
    return {
        "source": "MET",
        "id": meta.get("objectID"),
        "title": meta.get("title"),
        "artist": meta.get("artistDisplayName"),
        "date": meta.get("objectDate"),
        "culture": meta.get("culture"),
        "medium": meta.get("medium"),
        "image": meta.get("primaryImage") or meta.get("primaryImageSmall"),
        "objectURL": meta.get("objectURL"),
        "raw": meta
    }

# AIC
AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search"
AIC_DETAIL = "https://api.artic.edu/api/v1/artworks/{}"

def aic_search(q: str, max_results: int = 100) -> List[dict]:
    params = {"q": q, "limit": max_results, "fields": "id,title,artist_display,date_display,image_id,place_of_origin,classification"}
    res = safe_get_json(AIC_SEARCH, params=params)
    if not res:
        return []
    ids = [d.get("id") for d in res.get("data", []) if d.get("id")]
    out = []
    for i in ids[:max_results]:
        rec = safe_get_json(AIC_DETAIL.format(i), params={"fields":"id,title,artist_display,date_display,image_id,place_of_origin,classification"})
        if rec and rec.get("data"):
            out.append(rec["data"])
    return out

def normalize_aic(rec: dict) -> dict:
    image_id = rec.get("image_id")
    image = f"https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg" if image_id else None
    return {
        "source": "AIC",
        "id": rec.get("id"),
        "title": rec.get("title"),
        "artist": rec.get("artist_display"),
        "date": rec.get("date_display"),
        "culture": rec.get("place_of_origin"),
        "medium": rec.get("classification"),
        "image": image,
        "objectURL": f"https://www.artic.edu/artworks/{rec.get('id')}",
        "raw": rec
    }

# Cleveland (Open Access)
CLEVELAND_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks"

def cleveland_search(q: str, max_results: int = 80) -> List[dict]:
    out = []
    page = 1
    per = 50
    collected = 0
    while collected < max_results:
        params = {"q": q, "limit": per, "page": page}
        res = safe_get_json(CLEVELAND_SEARCH, params=params)
        if not res or not res.get("data"):
            break
        for r in res.get("data", []):
            out.append(r)
            collected += 1
            if collected >= max_results:
                break
        page += 1
    return out

def normalize_cleveland(rec: dict) -> dict:
    img = None
    images = rec.get("images") or []
    if images and isinstance(images, list):
        first = images[0]
        iiif = first.get("iiif_base")
        if iiif:
            img = iiif + "/full/400,/0/default.jpg"
        else:
            img = first.get("url")
    return {
        "source": "Cleveland",
        "id": rec.get("id"),
        "title": rec.get("title"),
        "artist": (rec.get("creators") or [{}])[0].get("description") if rec.get("creators") else None,
        "date": rec.get("creation_date"),
        "culture": rec.get("culture"),
        "medium": rec.get("technique") or rec.get("classification"),
        "image": img,
        "objectURL": rec.get("url"),
        "raw": rec
    }

# British Museum (public)
BRITISH_SEARCH = "https://collectionapi.britishmuseum.org/search"

def british_search(q: str, max_results: int = 100) -> List[dict]:
    res = safe_get_json(BRITISH_SEARCH, params={"q": q})
    if not res:
        return []
    hits = res.get("hits") or []
    ids = [h.get("object_id") for h in hits][:max_results]
    out = []
    for oid in ids:
        rec = safe_get_json(f"https://collectionapi.britishmuseum.org/object/{oid}")
        if rec:
            out.append(rec)
    return out

def normalize_british(rec: dict) -> dict:
    img = rec.get("primaryImage") or (rec.get("images") or [{}])[0].get("url") if rec.get("images") else None
    return {
        "source": "BritishMuseum",
        "id": rec.get("object_id") or rec.get("id"),
        "title": rec.get("title"),
        "artist": rec.get("maker"),
        "date": rec.get("date"),
        "culture": rec.get("culture"),
        "medium": rec.get("materials"),
        "image": img,
        "objectURL": rec.get("object_url") or rec.get("url"),
        "raw": rec
    }

# Rijksmuseum (requires free key)
RIJK_BASE = "https://www.rijksmuseum.nl/api/en/collection"

def rijks_search(q: str, apikey: str, max_results: int = 80) -> List[dict]:
    out = []
    per_page = 50
    page = 1
    collected = 0
    while collected < max_results:
        params = {"key": apikey, "q": q, "p": page, "ps": per_page, "imgonly": True}
        res = safe_get_json(RIJK_BASE, params=params)
        if not res:
            break
        items = res.get("artObjects") or []
        for itm in items:
            out.append(itm)
            collected += 1
            if collected >= max_results:
                break
        if not items:
            break
        page += 1
    return out

def normalize_rijks(rec: dict) -> dict:
    img = rec.get("webImage", {}).get("url")
    return {
        "source": "Rijksmuseum",
        "id": rec.get("objectNumber"),
        "title": rec.get("title"),
        "artist": rec.get("principalMaker"),
        "date": rec.get("dating", {}).get("presentingDate"),
        "culture": None,
        "medium": rec.get("physicalMedium"),
        "image": img,
        "objectURL": rec.get("links", {}).get("web"),
        "raw": rec
    }

# ---- Hybrid filter for Greek/Roman myth relevance ----
CHAR_KEYWORDS = [k.lower() for k in [
    "zeus","hera","athena","apollo","artemis","aphrodite","hermes","perseus","medusa",
    "heracles","theseus","achilles","poseidon","hades","demeter","persephone","dionysus","orpheus","narcissus"
]]
MEDIUM_KEYWORDS = ["greek","hellenistic","classical","roman","amphora","vase","terracotta","marble","bronze","red-figure","black-figure"]

STRICT_TAGS = {"Greek Mythology", "Roman", "Classical Antiquity", "Mythology", "Greek", "Roman"}

def rec_has_strict_tag(rec: dict) -> bool:
    tags = []
    raw = rec.get("raw") or {}
    # try multiple fields
    for key in ("tags","tag","objectTags","label","subject","subjects"):
        val = raw.get(key)
        if not val:
            continue
        if isinstance(val, list):
            for t in val:
                if isinstance(t, dict):
                    term = t.get("term") or t.get("name") or t.get("label")
                else:
                    term = str(t)
                tags.append(term)
        elif isinstance(val, str):
            tags.append(val)
    for t in tags:
        if not t:
            continue
        if any(t.strip().lower() == s.lower() for s in STRICT_TAGS):
            return True
    return False

def rec_medium_title_heuristic(rec: dict) -> bool:
    title = (rec.get("title") or "").lower()
    culture = (rec.get("culture") or "") if rec.get("culture") else ""
    medium = (rec.get("medium") or "") if rec.get("medium") else ""
    if any(k in title for k in CHAR_KEYWORDS):
        return True
    if any(k in culture.lower() for k in MEDIUM_KEYWORDS):
        return True
    if any(k in str(medium).lower() for k in MEDIUM_KEYWORDS):
        return True
    return False

def passes_hybrid(rec: dict) -> bool:
    if rec_has_strict_tag(rec):
        return True
    if rec_medium_title_heuristic(rec):
        return True
    # reject obvious non-art
    raw = rec.get("raw") or {}
    classification = str(raw.get("classification") or "").lower()
    dept = str(raw.get("department") or "").lower()
    rejects = ["costume","textile","photograph","musical","arms and armor","jewelry"]
    if any(r in classification for r in rejects) or any(r in dept for r in rejects):
        return False
    return False

# ---- OpenAI optional wrapper ----
def openai_client_available() -> bool:
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

# ---- Sidebar: keys and options (English) ----
st.sidebar.header("Configuration & Keys")
st.sidebar.markdown("Rijksmuseum requires a free API key (register at https://www.rijksmuseum.nl/en/api). Place it in `st.secrets['RIJKSMUSEUM_KEY']` or paste here for session use.")
rijks_input = st.sidebar.text_input("Rijksmuseum key (session)", type="password")
if st.sidebar.button("Save Rijks key to session"):
    if rijks_input:
        st.session_state["RIJKSMUSEUM_KEY"] = rijks_input
        st.sidebar.success("Rijks key saved to session (temporary).")
    else:
        st.sidebar.warning("No key entered.")

st.sidebar.markdown("---")
st.sidebar.markdown("OpenAI key (optional for AI text generation). Put in st.secrets['OPENAI_API_KEY'] or paste here for session.")
openai_input = st.sidebar.text_input("OpenAI key (session)", type="password", key="openai_in")
if st.sidebar.button("Save OpenAI key to session"):
    if openai_input:
        st.session_state["OPENAI_API_KEY"] = openai_input
        st.sidebar.success("OpenAI key saved to session (temporary).")
    else:
        st.sidebar.warning("No key entered.")

st.sidebar.markdown("---")
st.sidebar.markdown("Search mode: Automatic across all sources (recommended).")

# ---- Unified Explorer & Stories Page ----
st.header("Search & Generate — Explorer + Stories (Unified)")

# Search inputs
col1, col2 = st.columns([3,1])
with col1:
    q = st.text_input("Enter character or keyword (example: Athena, Perseus, Zeus)", value="Athena")
with col2:
    max_per_source = st.selectbox("Max per source", [20, 40, 60, 80], index=1)

search_btn = st.button("Search all sources")

if search_btn:
    st.info("Searching MET, AIC, Cleveland, British Museum, (Rijksmuseum if key provided)...")
    unified = []

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
                unified.append(normalize_met(m))
    except Exception:
        st.warning("MET search had an issue (continuing).")

    # AIC
    try:
        aic_recs = aic_search(q, max_results=max_per_source)
        for r in aic_recs:
            unified.append(normalize_aic(r))
    except Exception:
        st.warning("AIC search had an issue (continuing).")

    # Cleveland
    try:
        clev_recs = cleveland_search(q, max_results=max_per_source)
        for r in clev_recs:
            unified.append(normalize_cleveland(r))
    except Exception:
        st.warning("Cleveland search had an issue (continuing).")

    # British Museum
    try:
        bm_recs = british_search(q, max_results=max_per_source)
        for r in bm_recs:
            unified.append(normalize_british(r))
    except Exception:
        st.info("British Museum search may not return results for some queries (continuing).")

    # Rijksmuseum (optional)
    rijks_key = st.secrets.get("RIJKSMUSEUM_KEY") if "RIJKSMUSEUM_KEY" in st.secrets else st.session_state.get("RIJKSMUSEUM_KEY")
    if rijks_key:
        try:
            rijks_recs = rijks_search(q, apikey=rijks_key, max_results=max_per_source)
            for r in rijks_recs:
                unified.append(normalize_rijks(r))
        except Exception:
            st.warning("Rijksmuseum search failed (check your key).")

    st.session_state["unified_raw"] = unified

    # Deduplicate by (title+artist) or source+id
    unique = []
    seen = set()
    for r in unified:
        key = f"{r.get('source')}::{r.get('id')}" if r.get('source') and r.get('id') else (str(r.get('title','')).strip().lower() + '::' + str(r.get('artist','')).strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    st.session_state["unified_unique"] = unique
    st.success(f"Collected {len(unified)} raw records; {len(unique)} unique after dedupe.")

    # Apply hybrid filter
    filtered = [r for r in unique if passes_hybrid(r)]
    st.session_state["filtered_results"] = filtered
    st.success(f"Filtered results (hybrid Tag+Medium): {len(filtered)} artworks.")

# Display results (filtered)
filtered = st.session_state.get("filtered_results", [])
if filtered:
    st.markdown(f"### Results — {len(filtered)} filtered artworks (click 'Select' to pick for story generation)")
    cols = st.columns(3)
    for i, rec in enumerate(filtered[:60]):
        with cols[i % 3]:
            title = rec.get("title") or "Untitled"
            img = rec.get("image")
            if img:
                try:
                    st.image(img, use_column_width=True)
                except Exception:
                    st.write("[image load failed]")
            st.markdown(f"**{title}**")
            artist = rec.get("artist") or ""
            date = rec.get("date") or ""
            medium = rec.get("medium") or ""
            source = rec.get("source") or ""
            st.write(f"{artist} • {date}")
            st.write(f"*{medium}* — {source}")
            if st.button(f"Select {source}:{rec.get('id')}", key=f"select_{i}"):
                pool = st.session_state.get("selection_pool", [])
                pool.append(rec)
                st.session_state["selection_pool"] = pool
                st.success("Added to selection pool")

else:
    st.info("No filtered results available. Use the search box and click 'Search all sources' to fetch artworks.")

# Selection pool preview and action area
st.markdown("---")
pool = st.session_state.get("selection_pool", [])
st.subheader("Selection Pool")
if not pool:
    st.write("Selection pool is empty. Click 'Select' on any result above to add items here.")
else:
    for idx, item in enumerate(pool):
        st.write(f"{idx+1}. **{item.get('title','Untitled')}** — {item.get('source')}")
    sel_idx = st.number_input("Pick index of artwork to generate story", min_value=1, max_value=len(pool), value=1)
    selected = pool[sel_idx - 1]
    st.markdown("---")
    st.subheader("Selected Artwork")
    st.write(f"**{selected.get('title','Untitled')}** — {selected.get('source')}")
    if selected.get("image"):
        try:
            st.image(selected.get("image"), width=360)
        except:
            pass
    st.write(f"{selected.get('artist') or ''} • {selected.get('date') or ''} • {selected.get('medium') or ''}")
    st.write(f"[Open object]({selected.get('objectURL')})")

    # Character detection default
    t_low = (selected.get("title") or "").lower()
    detected = [k for k in CHAR_KEYWORDS if k in t_low]
    default_character = detected[0].capitalize() if detected else ""
    character = st.text_input("Character for narrative (auto-detected from title, edit if needed):", value=default_character)

    if st.button("Generate Myth Narrative & Artwork Commentary (AI if available)"):
        # Prepare prompt
        prompt = f"""You are an art historian and museum curator. Produce two labeled sections:

1) Myth Narrative — 3-6 sentences in a museum audio-guide tone about {character or 'the figure'}. Evocative but concise.

2) Artwork Commentary — 3-6 sentences analyzing this artwork and linking it to the myth. Use the metadata below.
Title: {selected.get('title')}
Artist: {selected.get('artist')}
Date: {selected.get('date')}
Medium: {selected.get('medium')}
Museum source: {selected.get('source')}

Keep language clear for museum visitors and students.
Return the two sections separated by '---'.
"""

        if not openai_client_available():
            st.warning("OpenAI key not found. Put it in st.secrets['OPENAI_API_KEY'] or paste it in the sidebar to enable AI generation.")
            # local fallback simple templates
            st.markdown("### Myth Narrative (fallback)")
            if character:
                st.write(f"{character} — a central figure in classical myth. (Fallback summary: add OpenAI key for richer text.)")
            else:
                st.write("Short myth summary (fallback). Add OpenAI key for richer text.")
            st.markdown("### Artwork Commentary (fallback)")
            st.write("This artwork depicts a scene related to classical myth. Add OpenAI key for a richer, detailed commentary.")
        else:
            try:
                out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=600)
            except Exception as e:
                st.error(f"AI generation failed: {e}")
                out = None
            if out:
                if '---' in out:
                    parts = [p.strip() for p in out.split('---') if p.strip()]
                    if len(parts) >= 1:
                        st.markdown("### Myth Narrative")
                        st.write(parts[0])
                    if len(parts) >= 2:
                        st.markdown("### Artwork Commentary")
                        st.write(parts[1])
                else:
                    st.markdown("### Generated Text")
                    st.write(out)

    # allow removing from pool
    if st.button("Remove selected from pool"):
        pool.pop(sel_idx - 1)
        st.session_state["selection_pool"] = pool
        st.success("Removed from selection pool.")

# ---- Small analytics (optional) ----
st.markdown("---")
st.subheader("Quick Analytics (selection pool)")
if pool:
    cultures = [p.get("culture") or p.get("source") for p in pool]
    mediums = [p.get("medium") or "Unknown" for p in pool]
    st.write(f"Artworks in pool: {len(pool)}")
    if px:
        try:
            fig = px.bar(x=[c for _, c in Counter(mediums).most_common(10)], y=[k for k, _ in Counter(mediums).most_common(10)], orientation='h', labels={"x":"Count","y":"Medium"})
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass
    else:
        st.write("Install plotly for richer analytics.")
else:
    st.write("No data in pool yet.")

# ---- Footer / About / Keys reminders ----
st.markdown("---")
st.header("About & Keys")
st.write(
    "Data sources: MET (no key), Art Institute of Chicago (no key), Cleveland Museum Open Access (no key), "
    "British Museum public API (no key), Rijksmuseum (free key needed)."
)
st.write(
    "To enable AI text generation, add your OpenAI API key to Streamlit secrets as `OPENAI_API_KEY` or paste in the sidebar."
)
st.write(
    "To enable Rijksmuseum searches, place your free Rijksmuseum key in Streamlit secrets as `RIJKSMUSEUM_KEY` or paste it in the sidebar."
)

# End of file
