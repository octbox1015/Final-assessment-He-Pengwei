# final_app.py
"""
Mythic Art Explorer — Version C (Full / "Super" — Tag + Medium Filter + Visual Analytics + Safe OpenAI via secrets)
Features:
 - MET API search (multi-keyword)
 - Tag + Medium combined filtering (recommended)
 - Myth Stories (3-part AI generation: Overview / Narrative / Artwork Commentary)
 - Visual Analytics (year distribution, mediums, culture, size scatter, dominant color estimation)
 - Safe OpenAI access via Streamlit secrets: st.secrets["OPENAI_API_KEY"]
 - Graceful fallbacks if OpenAI SDK or key missing
Notes:
 - Add to requirements.txt: streamlit requests plotly pillow numpy openai
 - To enable OpenAI, add to Streamlit secrets:
     OPENAI_API_KEY = "sk-...your key..."
"""

import io
import math
import time
import json
import collections
from typing import List, Dict, Optional, Tuple

import requests
import streamlit as st
import plotly.express as px

# Image processing
from PIL import Image
import numpy as np
from collections import Counter

# -------------------------
# Page config
# -------------------------
st.set_page_config(page_title="Mythic Art Explorer — Final (C)", layout="wide")
st.title("🧿 Mythic Art Explorer — Final (C)")

# -------------------------
# MET API endpoints + helpers
# -------------------------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

@st.cache_data(ttl=60*60*24, show_spinner=False)
def met_search_ids(q: str, max_results: int = 200) -> List[int]:
    try:
        r = requests.get(MET_SEARCH, params={"q": q, "hasImages": True}, timeout=12)
        r.raise_for_status()
        ids = r.json().get("objectIDs") or []
        return ids[:max_results]
    except Exception:
        return []

@st.cache_data(ttl=60*60*24, show_spinner=False)
def met_get_object_cached(object_id: int) -> Dict:
    try:
        r = requests.get(MET_OBJECT.format(object_id), timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

# -------------------------
# Filtering: Tag (strict) + Medium (medium)
# -------------------------
STRICT_MYTH_TAGS = {
    "Greek Mythology",
    "Zeus", "Hera", "Athena", "Apollo", "Artemis", "Aphrodite",
    "Hermes", "Poseidon", "Hades", "Demeter", "Dionysus",
    "Perseus", "Medusa", "Gorgon", "Minotaur",
    "Theseus", "Heracles", "Hercules", "Achilles",
    "Narcissus", "Orpheus", "Pan"
}

CHAR_KEYWORDS = [
    "zeus", "hera", "athena", "apollo", "artemis", "aphrodite",
    "hermes", "poseidon", "medusa", "perseus", "heracles",
    "theseus", "gorgon", "minotaur"
]

MEDIUM_KEYWORDS = [
    "greek", "attic", "hellenistic", "roman", "classical",
    "terracotta", "vase", "krater", "amphora", "marble", "bronze"
]

def passes_strict_tag_filter(meta: Dict) -> bool:
    tags = meta.get("tags") or []
    for t in tags:
        if isinstance(t, dict):
            term = t.get("term")
            if term and term in STRICT_MYTH_TAGS:
                return True
    return False

def passes_medium_filter(meta: Dict) -> bool:
    title = (meta.get("title") or "").lower()
    culture = (meta.get("culture") or "").lower()
    period = (meta.get("period") or "").lower()
    medium = (meta.get("medium") or "").lower()
    objname = (meta.get("objectName") or "").lower()

    if any(k in title for k in CHAR_KEYWORDS):
        return True
    if any(k in objname for k in CHAR_KEYWORDS):
        return True
    if "greek" in culture or "hellenistic" in culture or "classical" in period:
        return True
    if any(k in medium for k in MEDIUM_KEYWORDS):
        return True
    return False

def is_greek_myth_artwork(meta: Dict) -> bool:
    # Final combined filter: strict tag OR medium heuristic
    return passes_strict_tag_filter(meta) or passes_medium_filter(meta)

# -------------------------
# OpenAI wrapper (safe)
# -------------------------
def openai_available() -> bool:
    try:
        # prefer reading key from st.secrets for safety
        _ = st.secrets["OPENAI_API_KEY"]
        from openai import OpenAI  # type: ignore
        return True
    except Exception:
        return False

def get_openai_client():
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    api_key = st.secrets.get("OPENAI_API_KEY") if "OPENAI_API_KEY" in st.secrets else st.session_state.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

def ai_generate_text(prompt: str, model: str = "gpt-4.1-mini", max_tokens: int = 400) -> str:
    client = get_openai_client()
    if not client:
        raise RuntimeError("OpenAI client not available or API key missing.")
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text or ""

# -------------------------
# Small utilities: image color, size parsing
# -------------------------
def fetch_image_bytes(url: str, timeout: int = 8) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

def dominant_color_from_bytes(img_bytes: bytes, resize: int = 64) -> str:
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img = img.resize((resize, resize))
        arr = np.array(img).reshape((-1, 3))
        # Count most common RGB tuple
        counts = Counter([tuple(c) for c in arr])
        color = counts.most_common(1)[0][0]  # (r,g,b)
        return '#%02x%02x%02x' % color
    except Exception:
        return "#777777"

def extract_dimensions(meta: Dict) -> Tuple[Optional[float], Optional[float]]:
    """
    Try to extract numeric width & height in centimeters from dimensions string if present.
    This is heuristic and will often be None.
    """
    dims = meta.get("dimensions") or meta.get("measurements") or ""
    if not dims or not isinstance(dims, str):
        return (None, None)
    s = dims.replace("cm", "").replace("×", "x").replace("—", "x")
    # find numbers
    nums = []
    for part in s.replace(",", " ").split():
        try:
            val = float(part)
            nums.append(val)
        except:
            # strip trailing punctuation
            try:
                val = float(part.strip(".,;"))
                nums.append(val)
            except:
                continue
    if len(nums) >= 2:
        return (nums[0], nums[1])
    return (None, None)

# -------------------------
# UI: Sidebar / OpenAI key
# -------------------------
st.sidebar.title("Settings & OpenAI")
st.sidebar.markdown("You can place your OpenAI API key in Streamlit secrets (recommended) or paste it here (session only).")
if "OPENAI_API_KEY" not in st.session_state:
    st.session_state["OPENAI_API_KEY"] = None

key_input = st.sidebar.text_input("OpenAI API Key (session)", type="password")
if st.sidebar.button("Save key to session"):
    if key_input:
        st.session_state["OPENAI_API_KEY"] = key_input
        st.sidebar.success("Saved to session. For production, put your key in Streamlit secrets.")
    else:
        st.sidebar.warning("Provide an API key to save to session.")

if openai_available() or st.session_state.get("OPENAI_API_KEY"):
    st.sidebar.success("OpenAI ready" if openai_available() else "OpenAI available via session key")
else:
    st.sidebar.info("OpenAI not configured. AI features will be disabled until you add a key.")

# -------------------------
# Main navigation
# -------------------------
page = st.sidebar.selectbox("Page", [
    "Home", "Mythic Art Explorer (A)", "Myth Stories (D)", "Visual Analytics", "Mythic Lineages", "About"
])

# -------------------------
# Home
# -------------------------
if page == "Home":
    st.header("Welcome — Mythic Art Explorer (Final C)")
    st.write("""
        This application demonstrates:
        - API-driven retrieval from the MET Collection,
        - Tag + medium filtering to reliably surface Greek myth artworks,
        - AI-generated museum text (if OpenAI key provided),
        - Visual analytics including dominant color estimation and distribution charts.
    """)
    st.markdown("**Quick start**")
    st.write("- Go to **Mythic Art Explorer (A)** to fetch many candidates (medium-filtered).")
    st.write("- Go to **Myth Stories (D)** for tag-precise curated selection and 3-part AI text.")
    st.write("- Use **Visual Analytics** to analyze the dataset you fetched.")
    st.write("Place your OpenAI key in Streamlit secrets: `.streamlit/secrets.toml` or paste in sidebar (session only).")

# -------------------------
# Mythic Art Explorer (A) — broad + medium filter
# -------------------------
elif page == "Mythic Art Explorer (A)":
    st.header("Mythic Art Explorer — Broad search + Medium Filter (A)")
    st.write("This page uses multiple aliases and a medium-level heuristic filter to find likely Greek myth artworks (higher recall).")
    # selection
    default_choices = sorted(CHAR_KEYWORDS + ["Athena", "Zeus", "Perseus", "Medusa", "Theseus", "Heracles"])
    character = st.selectbox("Choose character (alias search)", default_choices, index=default_choices.index("athena") if "athena" in default_choices else 0)
    st.write("Search aliases (automatically generated):")
    def gen_aliases(name: str):
        name = name.strip()
        mapping = {"Athena":["Pallas Athena","Minerva"], "Zeus":["Jupiter"], "Perseus":["Perseus"], "Medusa":["Medusa","Gorgon"]}
        aliases = [name]
        aliases += mapping.get(name.capitalize(), [])
        aliases += [f"{name} myth", f"{name} greek", f"{name} mythology"]
        # dedupe
        out=[]; seen=set()
        for a in aliases:
            if a and a not in seen:
                seen.add(a); out.append(a)
        return out
    aliases = gen_aliases(character)
    st.write(", ".join(aliases))
    max_per_alias = st.slider("Max results per alias", 20, 600, 120, step=10)

    if st.button("Fetch & Filter (A)"):
        all_ids = []
        p = st.progress(0)
        for i, a in enumerate(aliases):
            ids = met_search_ids(a, max_results=max_per_alias)
            if ids:
                for oid in ids:
                    if oid not in all_ids:
                        all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} raw candidate IDs from MET. Fetching metadata and applying medium filter...")

        thumbs = []
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            meta = met_get_object_cached(oid)
            if not meta:
                continue
            if is_greek_myth_artwork(meta):
                thumb = meta.get("primaryImageSmall") or meta.get("primaryImage") or (meta.get("additionalImages") or [None])[0]
                thumbs.append({"id": oid, "meta": meta, "thumb": thumb})
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.002)
        p2.empty()
        st.session_state["explorer_thumbs"] = thumbs
        st.success(f"{len(thumbs)} filtered works ready (stored in session).")

    thumbs = st.session_state.get("explorer_thumbs", [])
    if not thumbs:
        st.info("No results yet. Use Fetch & Filter (A).")
    else:
        st.write(f"Displaying {len(thumbs)} works.")
        cols = st.columns(3)
        for idx, rec in enumerate(thumbs):
            with cols[idx % 3]:
                meta = rec["meta"]
                if rec["thumb"]:
                    try:
                        st.image(rec["thumb"], use_column_width=True)
                    except:
                        st.write("[Image failed to load]")
                st.markdown(f"**{meta.get('title','Untitled')}**")
                st.write(f"{meta.get('artistDisplayName','Unknown')} • {meta.get('objectDate','')}")
                st.write(f"*{meta.get('medium','')}*")
                st.write(f"[Open on MET]({meta.get('objectURL')})")
                if st.button(f"Select {rec['id']}", key=f"explore_sel_{rec['id']}"):
                    st.session_state["selected_explorer"] = rec
                    st.success("Selected!")

    if "selected_explorer" in st.session_state:
        rec = st.session_state["selected_explorer"]
        meta = rec["meta"]
        st.markdown("---")
        st.subheader("Selected artwork (Explorer)")
        if meta.get("primaryImage"):
            st.image(meta.get("primaryImage"), width=360)
        st.markdown(f"**{meta.get('title','Untitled')}**")
        st.write(f"{meta.get('artistDisplayName','Unknown')} • {meta.get('objectDate','')}")
        st.write(meta.get('medium',''))
        st.write(f"[Open on MET]({meta.get('objectURL')})")
        # AI label generation
        if st.button("Generate AI museum label (Explorer)"):
            if not openai_available() and not st.session_state.get("OPENAI_API_KEY"):
                st.warning("No OpenAI key available. Put it in Streamlit secrets or sidebar session input.")
            else:
                prompt = f"""You are an art historian. Write a concise museum label (50-110 words) for the artwork:
Title: {meta.get('title')}
Artist: {meta.get('artistDisplayName')}
Date: {meta.get('objectDate')}
Medium: {meta.get('medium')}
Make the text accessible to exhibition visitors and link image to the relevant myth."""
                try:
                    text = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=200)
                except Exception as e:
                    text = f"[AI generation failed: {e}]"
                st.markdown("### AI Museum Label (Explorer)")
                st.write(text)
                st.download_button("Download label (txt)", data=text, file_name="label_explorer.txt", mime="text/plain")

# -------------------------
# Myth Stories (D) — tag-precise + 3-part AI
# -------------------------
elif page == "Myth Stories (D)":
    st.header("Myth Stories — Tag-precise search + 3-part museum text (D)")
    st.write("This page prefers MET curator tags for high-precision retrieval (higher precision, lower recall).")
    characters = sorted(list(STRICT_MYTH_TAGS.intersection(set([t.capitalize() for t in CHAR_KEYWORDS])))) or ["Zeus","Athena","Perseus","Medusa","Theseus","Heracles"]
    character = st.selectbox("Choose character (tag-precise)", ["Zeus","Athena","Perseus","Medusa","Theseus","Heracles"], index=1)
    st.write("Searching MET for curator-tagged works for:", character)

    if st.button("Find tag-precise artworks (D)"):
        tag_terms = [character, "Greek Mythology", character.capitalize()]
        ids = []
        p = st.progress(0)
        for i, t in enumerate(tag_terms):
            res = met_search_ids(t, max_results=200)
            if res:
                for oid in res:
                    if oid not in ids:
                        ids.append(oid)
            p.progress(int((i+1)/len(tag_terms)*100))
        p.empty()
        st.info(f"Found {len(ids)} raw candidate IDs — validating tags...")
        results = []
        p2 = st.progress(0)
        total = max(1, len(ids))
        for i, oid in enumerate(ids):
            meta = met_get_object_cached(oid)
            if not meta:
                continue
            # Check tags
            tags = [t.get("term") for t in (meta.get("tags") or []) if isinstance(t, dict)]
            if any(term for term in tags if term and (term == character or term == "Greek Mythology" or term.lower() == character.lower())):
                thumb = meta.get("primaryImageSmall") or meta.get("primaryImage") or (meta.get("additionalImages") or [None])[0]
                results.append({"id": oid, "meta": meta, "thumb": thumb})
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.002)
        p2.empty()
        st.session_state["story_tag_results"] = results
        st.success(f"{len(results)} validated tag-precise artworks found.")

    results = st.session_state.get("story_tag_results", [])
    if not results:
        st.info("No tag-precise results yet. Click the button above.")
    else:
        st.write(f"Displaying {len(results)} tag-precise artworks.")
        cols = st.columns(3)
        for idx, rec in enumerate(results):
            with cols[idx % 3]:
                meta = rec["meta"]
                if rec["thumb"]:
                    try:
                        st.image(rec["thumb"], use_column_width=True)
                    except:
                        st.write("[Image failed]")
                st.markdown(f"**{meta.get('title','Untitled')}**")
                st.write(meta.get('artistDisplayName','Unknown'))
                st.write(meta.get('objectDate',''))
                if st.button(f"Select {rec['id']}", key=f"story_sel_{rec['id']}"):
                    st.session_state["story_selected"] = rec
                    st.success("Selected.")

    selected = st.session_state.get("story_selected")
    if selected:
        meta = selected["meta"]
        st.markdown("---")
        st.subheader(f"Selected: {meta.get('title','Untitled')}")
        if meta.get("primaryImage"):
            st.image(meta.get("primaryImage"), width=360)
        st.write(f"{meta.get('artistDisplayName','Unknown')} • {meta.get('objectDate','')} • {meta.get('medium','')}")
        st.write(f"[Open on MET]({meta.get('objectURL')})")

        if st.button("Generate AI 3-part museum text (Overview / Narrative / Commentary)"):
            if not openai_available() and not st.session_state.get("OPENAI_API_KEY"):
                st.warning("No OpenAI key configured. Add to Streamlit secrets or paste in sidebar.")
            else:
                seed = ""  # optional local seed could be used here
                prompt = f"""
You are an art historian and museum curator. Produce three labeled sections:

1) Character Overview — 1-2 sentences about {character}.

2) Myth Narrative — 3-6 short sentences in an evocative museum audio-guide tone.

3) Artwork Commentary — 3-6 short sentences analyzing:
Title: {meta.get('title')}
Artist: {meta.get('artistDisplayName')}
Date: {meta.get('objectDate')}
Discuss composition, lighting, symbolism, and how the image relates to the myth.

Return sections separated by '---' and label each.
"""
                try:
                    out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=600)
                except Exception as e:
                    out = f"[AI generation failed: {e}]"
                if isinstance(out, str) and '---' in out:
                    parts = [p.strip() for p in out.split('---') if p.strip()]
                    for p in parts:
                        if "Overview" in p or p.startswith("1"):
                            st.markdown("### 🧾 Character Overview")
                            st.write(p)
                        elif "Narrative" in p or p.startswith("2"):
                            st.markdown("### 📖 Myth Narrative")
                            st.write(p)
                        elif "Artwork" in p or p.startswith("3"):
                            st.markdown("### 🖼 Artwork Commentary")
                            st.write(p)
                        else:
                            st.write(p)
                else:
                    st.markdown("### AI Output")
                    st.write(out)
                st.download_button("Download museum text", data=out, file_name=f"{character}_museum_text.txt", mime="text/plain")

# -------------------------
# Visual Analytics
# -------------------------
elif page == "Visual Analytics":
    st.header("Visual Analytics — analyze your fetched dataset")
    st.write("Use this page after fetching artworks in Explorer (A) or Stories (D). It computes distributions and simple visual features (dominant color).")

    dataset_choice = st.selectbox("Analyze dataset from:", ["Explorer (A) - last fetch", "Stories (D) - last tag-precise fetch"], index=0)
    if dataset_choice.startswith("Explorer"):
        ds = st.session_state.get("explorer_thumbs", [])
    else:
        ds = st.session_state.get("story_tag_results", [])

    if not ds:
        st.info("No dataset available in session. Fetch artworks first from Explorer (A) or Stories (D).")
    else:
        st.write(f"Analyzing {len(ds)} records.")
        # Basic metadata lists
        years = []
        cultures = []
        mediums = []
        sizes = []
        colors = []
        p = st.progress(0)
        for i, rec in enumerate(ds):
            meta = rec["meta"]
            # years
            y = meta.get("objectBeginDate") or meta.get("objectDate")
            try:
                if isinstance(y, int):
                    years.append(y)
                elif isinstance(y, str) and y.strip().isdigit():
                    years.append(int(y.strip()))
            except:
                pass
            # culture / medium
            cult = (meta.get("culture") or "").strip()
            if cult:
                cultures.append(cult)
            med = (meta.get("medium") or "").strip()
            if med:
                mediums.append(med)
            # dimensions heuristic
            w, h = extract_dimensions(meta)
            if w or h:
                sizes.append((w or 0, h or 0))
            # dominant color (try)
            img_url = meta.get("primaryImageSmall") or meta.get("primaryImage")
            color_hex = None
            if img_url:
                b = fetch_image_bytes(img_url)
                if b:
                    color_hex = dominant_color_from_bytes(b)
            colors.append(color_hex or "#888888")
            if i % 5 == 0:
                p.progress(min(100, int((i+1)/len(ds)*100)))
            time.sleep(0.001)
        p.empty()

        # Year distribution
        if years:
            fig = px.histogram(x=years, nbins=30, title="Year / Period Distribution", labels={"x":"Year","y":"Count"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No reliable year data available for this dataset.")

        # Culture pie
        if cultures:
            ccount = collections.Counter(cultures).most_common(12)
            labels = [k for k,_ in ccount]
            vals = [v for _,v in ccount]
            fig2 = px.pie(values=vals, names=labels, title="Culture / Origin (top)")
            st.plotly_chart(fig2, use_container_width=True)
        # Mediums bar
        if mediums:
            mcount = collections.Counter(mediums).most_common(12)
            fig3 = px.bar(x=[c for _,c in mcount], y=[k for k,_ in mcount], orientation='h', labels={"x":"Count","y":"Medium"}, title="Mediums (top)")
            st.plotly_chart(fig3, use_container_width=True)

        # Sizes scatter
        if sizes:
            w_vals = [s[0] for s in sizes if s[0] and s[1]]
            h_vals = [s[1] for s in sizes if s[0] and s[1]]
            if w_vals and h_vals:
                fig4 = px.scatter(x=w_vals, y=h_vals, labels={"x":"Width (cm)","y":"Height (cm)"}, title="Dimensions scatter (approx.)")
                st.plotly_chart(fig4, use_container_width=True)
        # Dominant color swatches
        st.markdown("### Dominant color swatches (sample)")
        sw_cols = st.columns(8)
        sample_colors = colors[:8]
        for i, col in enumerate(sw_cols):
            with col:
                hexc = sample_colors[i] if i < len(sample_colors) else "#777777"
                st.markdown(f"<div style='background:{hexc}; width:100%; height:80px; border-radius:6px;'></div>", unsafe_allow_html=True)
                st.write(hexc)

        # Download CSV summary
        if st.button("Export summary CSV"):
            import csv, io
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["objectID","title","artist","date","culture","medium","primaryImage","dominantColor"])
            for rec, c in zip(ds, colors):
                m = rec["meta"]
                w.writerow([m.get("objectID"), m.get("title"), m.get("artistDisplayName"), m.get("objectDate"), m.get("culture"), m.get("medium"), m.get("primaryImageSmall") or m.get("primaryImage"), c])
            st.download_button("Download CSV", data=out.getvalue(), file_name="visual_analysis_summary.csv", mime="text/csv")

# -------------------------
# Mythic Lineages (simple explanations)
# -------------------------
elif page == "Mythic Lineages":
    st.header("Mythic Lineages — Museum-style panel")
    st.write("A compact panel with key mythic parentage & relationships. Use 'Generate AI panel' to let OpenAI craft a museum-style introduction.")
    RELS = [
        ("Chaos","Gaia","parent"),
        ("Gaia","Uranus","parent"),
        ("Uranus","Cronus","parent"),
        ("Cronus","Zeus","parent"),
        ("Cronus","Hera","parent"),
        ("Cronus","Poseidon","parent"),
        ("Cronus","Hades","parent"),
        ("Zeus","Athena","parent"),
        ("Zeus","Apollo","parent"),
        ("Zeus","Artemis","parent"),
        ("Zeus","Ares","parent"),
        ("Zeus","Hermes","parent"),
        ("Zeus","Dionysus","parent"),
        ("Zeus","Perseus","parent"),
        ("Zeus","Heracles","parent")
    ]
    # local fallback explanation generator
    def local_relation_explanation(a,b,rel):
        if rel=="parent":
            return f"🔹 {a} → {b}\n{a} is a progenitor figure whose attributes shape {b}."
        if rel=="conflict":
            return f"🔹 {a} → {b}\nThe relation is adversarial, often dramatised in myth."
        return f"🔹 {a} → {b}\nRelation: {rel}."

    if st.button("Generate AI panel (intro + bullets)"):
        if not openai_available() and not st.session_state.get("OPENAI_API_KEY"):
            st.warning("No OpenAI key — producing local panel text.")
            panel = "A compact genealogy of key mythic figures (local fallback)."
            st.markdown("### Panel")
            st.write(panel)
            st.markdown("---")
            for a,b,r in RELS:
                st.markdown(local_relation_explanation(a,b,r))
        else:
            items_text = "\n".join([f"{i+1}. {a} -> {b} (rel: {rel})" for i,(a,b,rel) in enumerate(RELS)])
            prompt = f"""You are a curator writing a museum panel introduction (3-5 sentences) about Greek myth genealogy, followed by short bullet explanations for each relation listed below. Keep language formal and accessible.

Relations:
{items_text}
"""
            try:
                out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=600)
            except Exception as e:
                st.error(f"AI failed: {e}")
                out = None
            if out:
                # naive split: first paragraph as panel, then bullets
                parts = out.strip().split("\n")
                st.markdown("### AI Panel")
                st.write("\n".join(parts[:5]))
                st.markdown("---")
                st.markdown("### Relations")
                for line in parts[5:]:
                    if line.strip():
                        st.markdown(line)

# -------------------------
# About
# -------------------------
elif page == "About":
    st.header("About — Mythic Art Explorer (Final C)")
    st.write("""
        This app demonstrates a pipeline for combining museum APIs (MET), rule-based filtering (tag + medium),
        simple image feature extraction, and optional AI-generated museum text.

        Deployment notes:
        - Add `openai`, `pillow`, `numpy`, `plotly` to requirements.txt for full functionality.
        - Put OPENAI_API_KEY in Streamlit secrets (recommended) or paste into sidebar for session use.
    """)
    st.markdown("**Resources & tips**")
    st.write("- If too many non-myth images appear, use the 'Myth Stories (D)' page (tag-precise).")
    st.write("- Visual Analytics estimates color & size heuristically — for production you may want robust parsing & color clustering.")

# End of file
