# app.py
"""
Mythic Art Explorer — Advanced UI (Modal + Prev/Next)
- Image-first gallery (thumbnails)
- Click "View details" -> opens st.modal with large image + metadata + AI (optional)
- Prev / Next inside modal
- Art Data (big-data summary), Interactive Tests, Mythic Lineages (network)
- Robust: handles missing libs or MET items gracefully
"""

import streamlit as st
import requests
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import os
import math
import time
import collections
import plotly.express as px
import plotly.graph_objects as go
from typing import List, Dict, Optional

# Optional libraries
try:
    import networkx as nx
    HAS_NETWORKX = True
except Exception:
    HAS_NETWORKX = False

try:
    import openai
    HAS_OPENAI = True
except Exception:
    openai = None
    HAS_OPENAI = False

# ---------------- Page config ----------------
st.set_page_config(page_title="Mythic Art Explorer — Advanced UI", layout="wide", initial_sidebar_state="expanded")

# ---------------- Constants ----------------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

MYTH_LIST = [
    "Zeus","Hera","Athena","Apollo","Artemis","Aphrodite","Hermes","Dionysus","Ares","Hephaestus",
    "Poseidon","Hades","Demeter","Persephone","Hestia","Heracles","Perseus","Achilles","Odysseus",
    "Theseus","Jason","Medusa","Minotaur","Sirens","Cyclops","Centaur","Prometheus","Orpheus",
    "Eros","Nike","The Muses","The Fates","The Graces","Hecate","Atlas","Pandora"
]

FIXED_BIOS = {
    "Zeus": "Zeus is the king of the Olympian gods, ruler of the sky and thunder. Often shown with a thunderbolt and eagle.",
    "Athena": "Athena (Pallas Athena) is goddess of wisdom, craft, and strategic warfare. Often shown armored with an owl as symbol.",
    "Medusa": "Medusa is one of the Gorgons whose gaze could turn viewers to stone; a complex symbol in ancient and modern art.",
    "Perseus": "Perseus is the hero who beheaded Medusa and rescued Andromeda; often shown with winged sandals and reflecting shield."
}

# ---------------- Helper: MET API ----------------
@st.cache_data(ttl=60*60*24, show_spinner=False)
def met_search_ids(query: str, max_results: int = 200) -> List[int]:
    try:
        resp = requests.get(MET_SEARCH, params={"q": query, "hasImages": True}, timeout=12)
        resp.raise_for_status()
        ids = resp.json().get("objectIDs") or []
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

def fetch_image_from_meta(meta: Dict, prefer_small: bool = True) -> Optional[Image.Image]:
    """Robust image fetcher; returns PIL Image or None."""
    urls = []
    if prefer_small and meta.get("primaryImageSmall"):
        urls.append(meta["primaryImageSmall"])
    if meta.get("primaryImage"):
        urls.append(meta["primaryImage"])
    if meta.get("additionalImages"):
        urls.extend(meta.get("additionalImages", []))
    for url in urls:
        if not url:
            continue
        try:
            r = requests.get(url, timeout=12)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB")
            return img
        except (requests.RequestException, UnidentifiedImageError):
            continue
    return None

def generate_aliases(name: str) -> List[str]:
    mapping = {
        "Athena": ["Pallas Athena", "Minerva"],
        "Zeus": ["Jupiter"],
        "Aphrodite": ["Venus"],
        "Hermes": ["Mercury"],
        "Heracles": ["Hercules"],
        "Persephone": ["Proserpina"],
        "Medusa": ["Gorgon"]
    }
    aliases = [name] + mapping.get(name, [])
    aliases += [f"{name} myth", f"{name} greek"]
    return list(dict.fromkeys(aliases))

# ---------------- OpenAI wrappers (optional) ----------------
def get_openai_client():
    key = st.session_state.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key or not HAS_OPENAI:
        return None
    openai.api_key = key
    return openai

def chat_complete_simple(client, prompt: str, max_tokens: int = 300):
    if client is None:
        return "OpenAI not configured. Paste API key in sidebar to enable."
    try:
        resp = client.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":"You are a museum curator."},{"role":"user","content":prompt}],
            max_tokens=max_tokens,
            temperature=0.2
        )
        # resp.choices[0].message.content usually
        return getattr(resp.choices[0].message, "content", str(resp))
    except Exception as e:
        return f"OpenAI error: {e}"

# ---------------- Sidebar / Navigation ----------------
st.sidebar.title("Mythic Art Explorer")
st.sidebar.markdown("Image-first gallery → modal details → AI curator (optional).")
st.sidebar.markdown("---")
page = st.sidebar.radio("Go to", ["Home", "Mythic Art Explorer", "Art Data", "Interactive Tests", "Mythic Lineages"], index=1)
st.sidebar.markdown("---")
st.sidebar.subheader("OpenAI (optional)")
api_key = st.sidebar.text_input("OpenAI API Key (session only)", type="password", key="openai_key")
if st.sidebar.button("Save API key", key="save_key"):
    if api_key:
        st.session_state["OPENAI_API_KEY"] = api_key
        st.sidebar.success("API Key saved to session.")
    else:
        st.sidebar.warning("Provide an API key to enable AI features.")
st.sidebar.markdown("---")
st.sidebar.markdown("Data source: The MET Museum Open Access API")

# ---------------- HOME ----------------
if page == "Home":
    st.title("🏛️ Mythic Art Explorer — Advanced UI")
    st.markdown(
        "Explore Greek mythology with real MET artworks. Click a thumbnail to open a detailed modal (large image, metadata, optional AI-curator text)."
    )
    st.markdown("Quick steps:\n1. Myhtic Art Explorer → select a figure → Fetch works. \n2. Click **View details** to open modal with Prev / Next. \n3. Use Art Data to run dataset-level analysis.")

# ---------------- MYTHIC ART EXPLORER (Gallery + Modal) ----------------
elif page == "Mythic Art Explorer":
    st.header("Mythic Art Explorer — Greek Figures & Artworks")
    selected = st.selectbox("Choose a mythic figure:", MYTH_LIST, key="select_figure")
    st.subheader(selected)
    st.write(FIXED_BIOS.get(selected, f"{selected} is a canonical figure in Greek myth."))

    st.markdown("**Search aliases (used for MET queries):**")
    st.write(generate_aliases(selected))

    max_results = st.slider("Max MET records per alias", 30, 600, 200, step=10, key="max_results")
    if st.button("Fetch related works (images)", key="fetch_btn"):
        aliases = generate_aliases(selected)
        all_ids = []
        prog = st.progress(0)
        for i, alias in enumerate(aliases):
            ids = met_search_ids(alias, max_results=max_results)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            prog.progress(int((i+1)/len(aliases)*100))
        prog.empty()
        st.success(f"Found {len(all_ids)} candidate works. Loading images (may take a moment)...")
        thumbs = []
        prog2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            meta = met_get_object_cached(oid)
            if meta and (meta.get("primaryImageSmall") or meta.get("primaryImage")):
                img = fetch_image_from_meta(meta, prefer_small=True)
                if img:
                    thumbs.append({"objectID": oid, "meta": meta, "img": img})
            if i % 10 == 0:
                prog2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.002)
        prog2.empty()
        st.session_state["thumbs"] = thumbs
        st.success(f"Loaded {len(thumbs)} artworks with images.")

    thumbs = st.session_state.get("thumbs", [])
    if not thumbs:
        st.info("No artworks loaded yet. Use 'Fetch related works (images)'.")
    else:
        per_page = st.number_input("Thumbnails per page", 6, 48, 12, step=6, key="per_page")
        pages = math.ceil(len(thumbs) / per_page)
        page_idx = st.number_input("Page", 1, max(1, pages), 1, key="page_idx")
        start = (page_idx - 1) * per_page
        page_items = thumbs[start:start + per_page]

        # waterfall-like 3-column layout with slight jittered heights
        cols = st.columns(3)
        for i, item in enumerate(page_items):
            col = cols[i % 3]
            with col:
                try:
                    img = item["img"]
                    w_target = 320
                    w, h = img.size
                    ratio = w_target / w
                    new_h = max(140, int(h * ratio))
                    thumb = img.resize((w_target, new_h))
                    st.image(thumb, use_column_width=False)
                except Exception:
                    st.write("Image preview unavailable")
                meta = item["meta"]
                st.markdown(f"**{meta.get('title') or meta.get('objectName') or 'Untitled'}**")
                st.write(meta.get("artistDisplayName") or "Unknown")
                st.write(meta.get("objectDate") or "—")
                # unique key per object for the button
                if st.button("View details", key=f"view_{item['objectID']}"):
                    # store modal context
                    st.session_state["modal_list"] = thumbs
                    st.session_state["modal_index"] = start + i
                    st.session_state["modal_open"] = True

        # Modal — outside grid; controlled by session_state
        if st.session_state.get("modal_open", False):
            idx = int(st.session_state.get("modal_index", 0))
            modal_list = st.session_state.get("modal_list", thumbs)
            idx = max(0, min(idx, len(modal_list)-1))
            st.session_state["modal_index"] = idx
            with st.modal("Artwork details", key=f"modal_{idx}"):
                record = modal_list[idx]
                oid = record["objectID"]
                meta = met_get_object_cached(oid) or record["meta"]
                img_full = fetch_image_from_meta(meta, prefer_small=False) or record["img"]

                left, right = st.columns([0.64, 0.36])
                with left:
                    if img_full:
                        w, h = img_full.size
                        max_w = 980
                        if w > max_w:
                            img_full = img_full.resize((max_w, int(h * (max_w / w))))
                        st.image(img_full, use_column_width=False)
                    else:
                        st.info("Large image unavailable.")
                with right:
                    st.subheader(meta.get("title") or meta.get("objectName") or "Untitled")
                    st.write(f"**Object ID:** {oid}")
                    st.write(f"**Artist:** {meta.get('artistDisplayName') or 'Unknown'}")
                    st.write(f"**Date:** {meta.get('objectDate') or '—'}")
                    st.write(f"**Medium:** {meta.get('medium') or '—'}")
                    st.write(f"**Dimensions:** {meta.get('dimensions') or '—'}")
                    st.write(f"**Classification:** {meta.get('classification') or '—'}")
                    if meta.get("objectURL"):
                        st.markdown(f"[Open on MET]({meta.get('objectURL')})")
                    st.markdown("---")
                    # AI curator optional
                    client = get_openai_client()
                    if client:
                        if st.button("Generate AI curator text", key=f"ai_{oid}"):
                            with st.spinner("Generating curator text..."):
                                prompt = f"Write a concise curator overview and one-paragraph iconography for this artwork. Metadata: {meta}"
                                out = chat_complete_simple(client, prompt, max_tokens=400)
                                st.write(out)
                    else:
                        st.write("(Enable OpenAI API key in sidebar to use AI features)")
                    st.markdown("---")
                    nav_prev, nav_close, nav_next = st.columns([1, 1, 1])
                    with nav_prev:
                        if st.button("← Previous", key=f"prev_{oid}"):
                            new_idx = max(0, idx - 1)
                            st.session_state["modal_index"] = new_idx
                            st.experimental_rerun()
                    with nav_close:
                        if st.button("Close", key=f"close_{oid}"):
                            st.session_state["modal_open"] = False
                    with nav_next:
                        if st.button("Next →", key=f"next_{oid}"):
                            new_idx = min(len(modal_list) - 1, idx + 1)
                            st.session_state["modal_index"] = new_idx
                            st.experimental_rerun()

# ---------------- ART DATA (big-data) ----------------
elif page == "Art Data":
    st.header("Art Data — Dataset Analysis (MET)")
    figure_for_analysis = st.selectbox("Choose a figure to analyze:", MYTH_LIST, key="ad_figure")
    aliases = generate_aliases(figure_for_analysis)
    max_results = st.slider("Max MET records per alias", 50, 800, 200, 50, key="ad_max")

    if st.button("Fetch dataset & analyze", key="ad_fetch"):
        all_ids = []
        p = st.progress(0)
        for i, a in enumerate(aliases):
            ids = met_search_ids(a, max_results=max_results)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate works — fetching metadata...")
        metas = []
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m:
                metas.append(m)
            if i % 10 == 0:
                p2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.002)
        p2.empty()
        st.session_state["analysis_dataset"] = metas
        st.success(f"Dataset built: {len(metas)} records.")

    dataset = st.session_state.get("analysis_dataset", None)
    if not dataset:
        st.info("No dataset. Click 'Fetch dataset & analyze'.")
    else:
        st.success(f"Analyzing {len(dataset)} records...")
        # extract stats
        def extract_stats(ds):
            import re
            years = []; mediums = []; cultures = []; classifications = []; tags = []
            vases = []; acquisitions = []; gvr = {"greek": 0, "roman": 0, "other": 0}
            for m in ds:
                y = m.get("objectBeginDate")
                if isinstance(y, int):
                    years.append(y)
                else:
                    od = m.get("objectDate") or ""
                    mo = re.search(r"-?\d{1,4}", od)
                    if mo:
                        try:
                            years.append(int(mo.group(0)))
                        except: pass
                med = (m.get("medium") or "").strip().lower()
                if med: mediums.append(med)
                cult = (m.get("culture") or "").strip()
                if cult: cultures.append(cult)
                cl = (m.get("classification") or "").strip()
                if cl: classifications.append(cl)
                tg = m.get("tags") or []
                if isinstance(tg, list):
                    for t in tg:
                        term = t.get("term") if isinstance(t, dict) else str(t)
                        if term: tags.append(term.lower())
                title = (m.get("title") or m.get("objectName") or "").lower()
                if any(k in med for k in ["vase", "amphora", "ceramic", "terracotta", "pottery"]):
                    vases.append(m.get("title") or m.get("objectName") or "")
                acc = m.get("accessionYear")
                if isinstance(acc, int): acquisitions.append(acc)
                elif isinstance(acc, str) and acc.isdigit(): acquisitions.append(int(acc))
                period = (m.get("period") or "").lower()
                if "roman" in period or "roman" in title:
                    gvr["roman"] += 1
                elif "greek" in period or "hellenistic" in period or "classical" in period or "greek" in title:
                    gvr["greek"] += 1
                else:
                    gvr["other"] += 1
            return {
                "years": years,
                "mediums": collections.Counter(mediums),
                "cultures": collections.Counter(cultures),
                "classifications": collections.Counter(classifications),
                "tags": collections.Counter(tags),
                "vases": vases,
                "acquisitions": acquisitions,
                "gvr": gvr
            }

        stats = extract_stats(dataset)

        st.subheader("Timeline (object dates / heuristics)")
        if stats["years"]:
            fig = px.histogram(x=stats["years"], nbins=40, labels={"x":"Year","y":"Count"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No reliable year data for this dataset.")

        st.subheader("Top mediums / materials")
        if stats["mediums"]:
            topm = stats["mediums"].most_common(20)
            fig2 = px.bar(x=[c for _,c in topm], y=[k for k,_ in topm], orientation="h", labels={"x":"Count","y":"Medium"})
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No medium data.")

        st.subheader("Geography / Culture")
        if stats["cultures"]:
            topc = stats["cultures"].most_common(20)
            fig3 = px.bar(x=[c for _,c in topc], y=[k for k,_ in topc], orientation="h", labels={"x":"Count","y":"Culture"})
            st.plotly_chart(fig3, use_container_width=True)

        st.subheader("Tags / Themes (top 20)")
        if stats["tags"]:
            topt = stats["tags"].most_common(20)
            fig4 = px.bar(x=[c for _,c in topt], y=[k for k,_ in topt], orientation="h", labels={"x":"Count","y":"Tag"})
            st.plotly_chart(fig4, use_container_width=True)

        st.subheader("Greek vs Roman vs Other (heuristic)")
        g = stats["gvr"]
        fig5 = px.pie(values=[g["greek"], g["roman"], g["other"]], names=["Greek","Roman","Other"])
        st.plotly_chart(fig5, use_container_width=True)

        st.subheader("Vase / Vessel examples (raw titles)")
        if stats["vases"]:
            for i, v in enumerate(stats["vases"][:30]): st.write(f"{i+1}. {v}")
        else:
            st.info("No vase-like items detected.")

        st.subheader("Acquisition years")
        if stats["acquisitions"]:
            fig6 = px.histogram(x=stats["acquisitions"], nbins=30, labels={"x":"Year","y":"Count"})
            st.plotly_chart(fig6, use_container_width=True)

        if st.button("Export cleaned dataset (CSV)"):
            import pandas as pd
            rows = []
            for m in dataset:
                rows.append({
                    "objectID": m.get("objectID"),
                    "title": m.get("title"),
                    "objectDate": m.get("objectDate"),
                    "objectBeginDate": m.get("objectBeginDate"),
                    "medium": m.get("medium"),
                    "culture": m.get("culture"),
                    "classification": m.get("classification"),
                    "period": m.get("period"),
                    "accessionYear": m.get("accessionYear"),
                    "objectURL": m.get("objectURL")
                })
            df = pd.DataFrame(rows)
            csv = df.to_csv(index=False)
            st.download_button("Download CSV", data=csv, file_name=f"met_{figure_for_analysis}_dataset.csv", mime="text/csv")

# ---------------- INTERACTIVE TESTS ----------------
elif page == "Interactive Tests":
    st.header("Interactive Tests — Mythic Personality")
    st.markdown("Two quick interactive tests with richer interpretations.")

    st.subheader("Test A — Which Greek Deity Are You? (short)")
    q1 = st.radio("In a group you:", ["Lead","Support","Create","Plan"], key="tA_q1")
    q2 = st.radio("You value most:", ["Power","Wisdom","Love","Joy"], key="tA_q2")
    q3 = st.radio("Pick a symbol:", ["Thunderbolt","Owl","Dove","Lyre"], key="tA_q3")
    if st.button("Reveal (Test A)"):
        if q2=="Wisdom" or q3=="Owl":
            deity="Athena"
            text = ("Athena: strategic intelligence and protective insight. "
                    "You prefer thoughtful action, plan for contingencies, and value knowledge as power.")
        elif q2=="Love" or q3=="Dove":
            deity="Aphrodite"
            text = ("Aphrodite: aesthetics, relational intelligence, and emotional nuance. "
                    "You are driven by connection and the subtle social arts.")
        elif q2=="Power" or q3=="Thunderbolt":
            deity="Zeus"
            text = ("Zeus: leadership and social authority. You take responsibility for outcomes and command presence.")
        else:
            deity="Apollo"
            text = ("Apollo: balanced artistry, reason, and harmony. You combine craft with clarity.")
        st.markdown(f"### You resemble **{deity}**")
        st.write(text)
        st.markdown("**Recommended art themes:**")
        if deity=="Athena":
            st.write("- Scenes of councils, weaving, protective symbols (owl, aegis).")
        elif deity=="Aphrodite":
            st.write("- Love narratives, ritual images of beauty and marriage.")
        elif deity=="Zeus":
            st.write("- Thrones, thunderbolt iconography, oath-taking scenes.")
        else:
            st.write("- Lyres, oracular motifs, sun imagery.")

    st.markdown("---")
    st.subheader("Test B — Short Jungian-Myth Archetype (8 items)")
    Qs = [
        "I prefer leading groups.",
        "I trust logic over feelings.",
        "I feel energized by creativity and music.",
        "I protect people close to me.",
        "I seek new experiences even if risky.",
        "I rely on rituals/tradition.",
        "I quickly act in crises.",
        "I enjoy deep discussion about meaning."
    ]
    answers = []
    for i, q in enumerate(Qs):
        a = st.slider(f"{i+1}. {q}", 1, 5, 3, key=f"tb_{i}")
        answers.append(a)
    if st.button("Reveal (Test B)"):
        s_leader = answers[0] + answers[6]
        s_logic = answers[1] + answers[7]
        s_creative = answers[2] + answers[4]
        s_protect = answers[3] + answers[5]
        # decide
        scores = {"Guardian": s_protect + s_leader, "Sage": s_logic, "Seeker": s_creative, "Warrior": s_leader + s_creative}
        arche = max(scores, key=scores.get)
        if arche == "Guardian":
            st.markdown("## Archetype: **Guardian (Zeus / Hera)**")
            st.write("You value order, duties, and protective responsibility. Visual themes: ritual objects, thrones, familial scenes.")
        elif arche == "Sage":
            st.markdown("## Archetype: **Sage (Athena / Prometheus)**")
            st.write("You seek clarity, strategies, and long-term knowledge. Visual themes: teaching scenes, wisdom symbols (owl, scroll).")
        elif arche == "Seeker":
            st.markdown("## Archetype: **Seeker (Dionysus / Orpheus)**")
            st.write("You pursue intense experience and transformation. Visual themes: feasts, music, ecstatic rituals.")
        else:
            st.markdown("## Archetype: **Warrior (Ares / Achilles)**")
            st.write("You pursue challenge and mastery. Visual themes: battle scenes, heroic trophies.")

# ---------------- MYTHIC LINEAGES ----------------
elif page == "Mythic Lineages":
    st.header("Mythic Lineages — Network")
    st.write("Directed relationships: Primordials → Titans → Olympians → Heroes → Creatures")

    # simple edge list (expand as you like)
    edges = [
        ("Chaos","Gaia"),("Gaia","Uranus"),("Uranus","Cronus"),("Cronus","Zeus"),
        ("Cronus","Hera"),("Cronus","Poseidon"),("Cronus","Hades"),
        ("Zeus","Athena"),("Zeus","Apollo"),("Zeus","Artemis"),("Zeus","Ares"),
        ("Zeus","Hermes"),("Zeus","Dionysus"),("Zeus","Perseus"),("Zeus","Heracles"),
        ("Perseus","Theseus"),("Theseus","Achilles"),("Medusa","Perseus"),
        ("Minotaur","Theseus"),("Cyclops","Poseidon")
    ]

    # create network visualization — prefer networkx if available, fallback to simple Plotly nodes
    if HAS_NETWORKX:
        G = nx.DiGraph()
        G.add_edges_from(edges)
        pos = nx.spring_layout(G, seed=42)
        edge_x=[]; edge_y=[]
        for src, dst in G.edges():
            x0,y0 = pos[src]
            x1,y1 = pos[dst]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
        node_x=[]; node_y=[]; labels=[]
        for node in G.nodes():
            x,y = pos[node]
            node_x.append(x); node_y.append(y); labels.append(node)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#999'), hoverinfo='none'))
        fig.add_trace(go.Scatter(x=node_x, y=node_y, mode='markers+text', text=labels, textposition='top center',
                                 marker=dict(size=18, color='#3A8DFF')))
        fig.update_layout(showlegend=False, xaxis=dict(visible=False), yaxis=dict(visible=False), height=700)
        st.plotly_chart(fig, use_container_width=True)
    else:
        # fallback: adjacency list
        st.info("NetworkX not installed in this runtime — showing adjacency lists")
        parents = {}
        for a,b in edges:
            parents.setdefault(a, []).append(b)
        for p, children in parents.items():
            st.markdown(f"**{p}** → " + ", ".join(children))

# ---------------- End ----------------
