# final_app.py
"""
Mythic Art Explorer — Final project (Myth Stories + filtered MET search)
Features:
 - MET Museum browsing (masonry + modal)
 - Data visualization (Plotly)
 - Interactive myth network (PyVis)
 - Myth Stories (AI narrative + artwork commentary) — rewritten
 - Style Transfer (OpenAI images.generate)
Notes:
 - Add to requirements.txt: streamlit, requests, plotly, networkx, pyvis, pillow, openai>=1.0.0
 - Provide OpenAI API key via sidebar for AI features
"""

import streamlit as st
import requests
import time
import collections
import json
from typing import List, Dict, Optional
import plotly.express as px

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="Mythic Art Explorer", layout="wide")

# ---------- LOCAL MYTH SEEDS (expanded) ----------
MYTH_DB = {
    "Zeus": "Zeus, king of the Olympian gods, wielder of thunder, arbiter of vows and order among gods and humans.",
    "Hera": "Hera, queen of the gods, goddess of marriage, often depicted with regal bearing and peacock symbolism.",
    "Athena": "Athena, goddess of wisdom, craft, and strategic warfare; patroness of cities and heroes.",
    "Apollo": "Apollo, god of music, prophecy, and the sun; associated with lyres and oracles.",
    "Artemis": "Artemis, goddess of the hunt, wilderness, and the lunar sphere; protector of young women and animals.",
    "Aphrodite": "Aphrodite, goddess of love and beauty; associated with desire, sea-born imagery, and the mirror.",
    "Hermes": "Hermes, messenger of the gods, trickster, guide of travelers and souls to the underworld.",
    "Dionysus": "Dionysus, god of wine, ritual ecstasy, theatre, and the loosening of boundaries.",
    "Ares": "Ares, god of war and violent conflict, often shown in armor or battle scenes.",
    "Hephaestus": "Hephaestus, god of craft and metallurgy; creator of many divine objects.",
    "Poseidon": "Poseidon, god of the sea, earthquakes, and horses; often shown with trident and marine motifs.",
    "Hades": "Hades, ruler of the underworld and the domain of the dead; associated with chthonic imagery.",
    "Demeter": "Demeter, goddess of grain, agriculture, and seasonal cycles.",
    "Persephone": "Persephone, daughter of Demeter and queen of the underworld; her story links seasons and rebirth.",
    "Heracles": "Heracles, the famed hero of strength and labors, bridging divine and mortal worlds.",
    "Perseus": "Perseus, slayer of Medusa and rescuer of Andromeda; aided by divine gifts.",
    "Orpheus": "Orpheus, musician and poet whose song moved beasts and gods; journeyed to the underworld for Eurydice.",
    "Narcissus": "Narcissus, youth obsessed with his reflection, a myth about self-love and fate.",
    "Medusa": "Medusa, the Gorgon whose glance turns mortals to stone; complex symbol of otherness and power.",
    "Theseus": "Theseus, Athenian hero, slayer of the Minotaur and founder-figure of civic myths.",
}

# ---------- MET API ----------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

@st.cache_data(ttl=60*60*24, show_spinner=False)
def met_search_ids(q: str, max_results: int = 200) -> List[int]:
    """Search MET for q and return up to max_results object IDs (raw search)."""
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

def is_greek_roman_meta(meta: Dict) -> bool:
    """
    Heuristic filter: return True if meta appears to be Greek/Roman/Hellenistic myth-related.
    We check culture, period, title, objectName and department/classification.
    This reduces false positives from the MET API.
    """
    if not meta:
        return False
    def has_any_field(keys, text):
        if not text:
            return False
        t = str(text).lower()
        return any(k in t for k in keys)

    culture = meta.get("culture") or ""
    period = meta.get("period") or ""
    title = meta.get("title") or ""
    objname = meta.get("objectName") or ""
    classification = meta.get("classification") or ""

    # positive signals
    positive = ["greek", "hellenistic", "roman", "classical", "greco-roman", "greek, hellenistic"]
    # words likely present in myth objects
    myth_keywords = ["herakles", "hercules", "zeus", "hera", "athena", "apollo", "artemis",
                     "poseidon", "hades", "perseus", "medusa", "orpheus", "persephone", "minotaur",
                     "narcissus", "echo", "theseus", "achilles", "heracles", "nike", "eros", "dionysus",
                     "venus", "jupiter", "roman god", "myth", "mythological", "gorgon", "hero"]
    # allowed classifications that are likely to illustrate myths (not exhaustive)
    allowed_class = ["sculpture", "vessel", "ceramics", "painting", "drawing", "print", "relief", "statuette", "stone", "marble"]

    # If culture or period strongly suggests greek/roman
    if has_any_field(positive, culture) or has_any_field(positive, period):
        return True

    # If title or objectName contains myth keywords
    if has_any_field(myth_keywords, title) or has_any_field(myth_keywords, objname):
        return True

    # classification heuristic
    if has_any_field(allowed_class, classification):
        # it's allowed classification but ensure title has at least some myth keyword or culture hint
        if has_any_field(myth_keywords, title) or has_any_field(positive, period) or has_any_field(positive, culture):
            return True

    # fallback False
    return False

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
    aliases += [f"{name} myth", f"{name} greek", f"{name} mythology"]
    seen = set(); out = []
    for a in aliases:
        if a not in seen:
            seen.add(a); out.append(a)
    return out

# ---------- Sidebar ----------
st.sidebar.title("Mythic Art Explorer")
st.sidebar.markdown("Browse MET artworks for Greek/Roman myths — Masonry gallery + modal.")
st.sidebar.markdown("---")
st.sidebar.markdown("### Main Pages")
main_pages = ["Home", "Mythic Art Explorer", "Art Data", "Interactive Tests", "Mythic Lineages", "Myth Stories", "Style Transfer", "About"]
sel_main = st.sidebar.selectbox("Main Pages", main_pages, index=1)
st.sidebar.markdown("### AI Tools")
ai_tools = ["AI Interpretation"]  # more tools available on pages
sel_tool = st.sidebar.selectbox("AI Tools (optional)", ["None"] + ai_tools, index=0)
page = sel_tool if sel_tool != "None" else sel_main

st.sidebar.markdown("---")
st.sidebar.info("OpenAI integration is optional. For AI features, add 'openai' to requirements and paste your key here.")
api_key = st.sidebar.text_input("OpenAI API Key (optional, session only)", type="password", key="openai_key")
if st.sidebar.button("Save API key", key="save_openai"):
    if api_key:
        st.session_state["OPENAI_API_KEY"] = api_key
        st.sidebar.success("API key saved to session.")
    else:
        st.sidebar.warning("Provide a valid key.")

# ---------- Home ----------
if page == "Home":
    st.title("🏛 Mythic Art Explorer")
    st.write("Explore Greek & Roman myth characters and artworks from The MET.")
    st.write("Use 'Mythic Art Explorer' to find images, or 'Myth Stories' to generate museum-style narratives.")

# ---------- Mythic Art Explorer (gallery) ----------
elif page == "Mythic Art Explorer":
    st.header("Mythic Art Explorer — Greek & Roman Figures")
    selected = st.selectbox("Choose a mythic figure", MYTH_LIST, index=0)
    st.write(MYTH_DB.get(selected, ""))
    st.markdown("**Search aliases:**"); st.write(generate_aliases(selected))
    max_results = st.slider("Max MET records per alias", 20, 400, 120, step=10)

    if st.button("Fetch related works (filtered)"):
        aliases = generate_aliases(selected)
        all_ids = []
        p = st.progress(0)
        for i, a in enumerate(aliases):
            ids = met_search_ids(a, max_results=max_results)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate object IDs. Fetching metadata and applying Greek/Roman filters...")

        thumbs = []
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            meta = met_get_object_cached(oid)
            if not meta:
                continue
            # apply heuristic filter
            if not is_greek_roman_meta(meta):
                continue
            thumb_url = meta.get("primaryImageSmall") or meta.get("primaryImage")
            full_url = meta.get("primaryImage") or (meta.get("additionalImages") or [None])[0]
            if thumb_url:
                thumbs.append({
                    "objectID": oid,
                    "title": meta.get("title"),
                    "artist": meta.get("artistDisplayName"),
                    "date": meta.get("objectDate"),
                    "medium": meta.get("medium"),
                    "dimensions": meta.get("dimensions"),
                    "objectURL": meta.get("objectURL"),
                    "thumb": thumb_url,
                    "full": full_url
                })
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.01)
        p2.empty()
        st.session_state["thumbs_data"] = thumbs
        st.success(f"Prepared {len(thumbs)} filtered thumbnail records (likely Greek/Roman).")

    thumbs = st.session_state.get("thumbs_data", [])
    if not thumbs:
        st.info("No filtered thumbnails yet. Click 'Fetch related works (filtered)'.")
    else:
        st.write(f"Showing {len(thumbs)} artworks — filtered for Greek/Roman relevance.")
        items_json = json.dumps(thumbs)
        # Masonry HTML + modal (same structure as earlier)
        html = f"""
        <style>
        .masonry-container {{ column-gap: 16px; padding: 6px; }}
        @media (min-width: 1400px) {{ .masonry-container {{ column-count: 4; }} }}
        @media (min-width: 1000px) and (max-width: 1399px) {{ .masonry-container {{ column-count: 3; }} }}
        @media (min-width: 700px) and (max-width: 999px) {{ .masonry-container {{ column-count: 2; }} }}
        @media (max-width: 699px) {{ .masonry-container {{ column-count: 1; }} }}
        .masonry-item {{ display: inline-block; width:100%; margin:0 0 16px; break-inside: avoid; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-radius:6px; overflow:hidden; background:#fff; }}
        .masonry-item img {{ width:100%; height:auto; display:block; cursor:pointer; }}
        .masonry-meta {{ padding:8px; font-size:13px; }}
        .m-modal {{ position:fixed; z-index:9999; left:0; top:0; width:100%; height:100%; background: rgba(0,0,0,0.8); display:none; align-items:center; justify-content:center; }}
        .m-modal.open {{ display:flex; }}
        .m-modal-content {{ max-width:92%; max-height:92%; position:relative; display:flex; gap:16px; color:#111; }}
        .m-modal-image {{ max-width:72vw; max-height:88vh; overflow:hidden; background:#111; border-radius:6px; }}
        .m-modal-image img {{ display:block; max-width:100%; height:auto; margin:0 auto; }}
        .m-modal-meta {{ width:340px; max-height:88vh; overflow:auto; background:#fff; padding:16px; border-radius:6px; }}
        .m-arrow {{ position:absolute; top:50%; transform:translateY(-50%); width:56px; height:56px; border-radius:28px; background: rgba(255,255,255,0.18); color:#fff; display:flex; align-items:center; justify-content:center; font-size:28px; cursor:pointer; }}
        .m-close {{ position:absolute; right:8px; top:8px; background: rgba(0,0,0,0.4); color:#fff; border-radius:6px; padding:6px 8px; cursor:pointer; }}
        @media (max-width:900px){{ .m-modal-content{{flex-direction:column; align-items:center}} .m-modal-meta{{width:100%; max-height:40vh}} .m-modal-image{{max-width:92vw}} .m-arrow{{width:44px;height:44px;font-size:22px}} }}
        </style>

        <div id="gallery" class="masonry-container"></div>

        <div id="mModal" class="m-modal" role="dialog" aria-hidden="true">
          <div class="m-modal-content" id="mContent">
            <div class="m-modal-image" id="mImageWrap"><img id="mImage" src="" alt="Artwork"/></div>
            <div class="m-modal-meta" id="mMeta">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <h3 id="mTitle" style="margin:0;font-size:18px;"></h3>
                <div id="mClose" class="m-close">✕</div>
              </div>
              <p id="mArtist" style="margin:.6em 0 .2em 0;color:#444;"></p>
              <p id="mDate" style="margin:.2em 0;color:#666;font-size:13px;"></p>
              <p id="mMedium" style="margin:.6em 0;color:#333;font-size:13px;"></p>
              <a id="mLink" href="#" target="_blank" style="font-size:13px;color:#0b66ff;">Open on MET</a>
            </div>
            <div class="m-arrow left" id="arrowLeft" title="Previous">◀</div>
            <div class="m-arrow right" id="arrowRight" title="Next">▶</div>
          </div>
        </div>

        <script>
        const items = {items_json};

        const gallery = document.getElementById('gallery');
        function buildGallery() {{
          gallery.innerHTML = '';
          items.forEach((it, idx) => {{
            const card = document.createElement('div');
            card.className = 'masonry-item';
            const img = document.createElement('img');
            img.src = it.thumb;
            img.loading = 'lazy';
            img.alt = it.title || 'Artwork';
            img.onclick = () => openModal(idx);
            const meta = document.createElement('div');
            meta.className = 'masonry-meta';
            meta.innerHTML = `<strong>${{(it.title||'Untitled')}} </strong><br/><small>${{it.artist||'Unknown'}} • ${{it.date||'—'}}</small>`;
            card.appendChild(img);
            card.appendChild(meta);
            gallery.appendChild(card);
          }});
        }}

        let curIndex = 0;
        const modal = document.getElementById('mModal');
        const mImage = document.getElementById('mImage');
        const mTitle = document.getElementById('mTitle');
        const mArtist = document.getElementById('mArtist');
        const mDate = document.getElementById('mDate');
        const mMedium = document.getElementById('mMedium');
        const mLink = document.getElementById('mLink');
        const arrowLeft = document.getElementById('arrowLeft');
        const arrowRight = document.getElementById('arrowRight');
        const mClose = document.getElementById('mClose');

        function renderModal(index) {{
          const it = items[index];
          curIndex = index;
          mImage.src = it.full || it.thumb;
          mTitle.textContent = it.title || 'Untitled';
          mArtist.textContent = it.artist || 'Unknown';
          mDate.textContent = it.date || '';
          mMedium.textContent = it.medium || '';
          mLink.href = it.objectURL || '#';
        }}

        function openModal(index) {{
          renderModal(index);
          modal.classList.add('open');
          modal.setAttribute('aria-hidden','false');
        }}
        function closeModal() {{
          modal.classList.remove('open');
          modal.setAttribute('aria-hidden','true');
        }}
        arrowLeft.onclick = () => {{ if(items.length>0) {{ curIndex = (curIndex-1+items.length)%items.length; renderModal(curIndex); }} }};
        arrowRight.onclick = () => {{ if(items.length>0) {{ curIndex = (curIndex+1)%items.length; renderModal(curIndex); }} }};
        mClose.onclick = closeModal;
        modal.onclick = (e) => {{ if(e.target === modal) closeModal(); }};
        document.addEventListener('keydown', (e) => {{
          if(modal.classList.contains('open')) {{
            if(e.key === 'ArrowLeft') arrowLeft.click();
            if(e.key === 'ArrowRight') arrowRight.click();
            if(e.key === 'Escape') closeModal();
          }}
        }});
        buildGallery();
        </script>
        """
        st.components.v1.html(html, height=700, scrolling=True)

# ---------- Art Data ----------
elif page == "Art Data":
    st.header("Art Data — Lightweight dataset summary")
    figure = st.selectbox("Choose figure", MYTH_LIST)
    aliases = generate_aliases(figure)
    max_results = st.slider("Max per alias", 30, 800, 200, step=10)
    if st.button("Fetch dataset & analyze"):
        all_ids = []
        p = st.progress(0)
        for i, a in enumerate(aliases):
            ids = met_search_ids(a, max_results=max_results)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate objects; fetching metadata...")
        metas = []
        p2 = st.progress(0)
        for i, oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m and is_greek_roman_meta(m):
                metas.append(m)
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/len(all_ids)*100)))
            time.sleep(0.005)
        p2.empty()
        st.session_state["analysis_dataset"] = metas
        st.success(f"Dataset ready: {len(metas)} records.")

    dataset = st.session_state.get("analysis_dataset")
    if not dataset:
        st.info("No dataset loaded yet.")
    else:
        st.write(f"Analyzing {len(dataset)} records")
        def stats_from(ds):
            years=[]; mediums=[]; cultures=[]
            gvr = {"greek":0,"roman":0,"other":0}
            for m in ds:
                y = m.get("objectBeginDate")
                if isinstance(y,int): years.append(y)
                od = (m.get("objectDate") or "")
                try:
                    if isinstance(od,str) and od.strip().isdigit():
                        years.append(int(od.strip()))
                except: pass
                med = (m.get("medium") or "").strip().lower()
                if med: mediums.append(med)
                cult = (m.get("culture") or "").strip()
                if cult: cultures.append(cult)
                period = (m.get("period") or "").lower()
                title = (m.get("title") or m.get("objectName") or "").lower()
                if "roman" in period or "roman" in title: gvr["roman"]+=1
                elif "greek" in period or "classical" in period or "hellenistic" in period or "greek" in title: gvr["greek"]+=1
                else: gvr["other"]+=1
            return {"years":years,"mediums":collections.Counter(mediums),"cultures":collections.Counter(cultures),"gvr":gvr}
        stats = stats_from(dataset)
        if stats["years"]:
            fig = px.histogram(x=stats["years"], nbins=30, labels={"x":"Year","y":"Count"}, title="Time distribution (heuristic)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No reliable year data.")
        if stats["mediums"]:
            top = stats["mediums"].most_common(15)
            fig2 = px.bar(x=[c for _,c in top], y=[k for k,_ in top], orientation='h', labels={"x":"Count","y":"Medium"})
            st.plotly_chart(fig2, use_container_width=True)
        g = stats["gvr"]
        fig3 = px.pie(values=[g["greek"], g["roman"], g["other"]], names=["Greek","Roman","Other"], title="Greek vs Roman vs Other (heuristic)")
        st.plotly_chart(fig3, use_container_width=True)
        if st.button("Export CSV (clean)"):
            import csv, io
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["objectID","title","objectDate","objectBeginDate","medium","culture","classification","period","accessionYear","objectURL"])
            for m in dataset:
                w.writerow([
                    m.get("objectID"), m.get("title"), m.get("objectDate"), m.get("objectBeginDate"),
                    m.get("medium"), m.get("culture"), m.get("classification"), m.get("period"),
                    m.get("accessionYear"), m.get("objectURL")
                ])
            st.download_button("Download CSV", data=out.getvalue(), file_name=f"met_{figure}_dataset.csv", mime="text/csv")

# ---------- Interactive Tests ----------
elif page == "Interactive Tests":
    st.header("Interactive Tests — Mythic Personality")
    q1 = st.radio("In a group you:", ["Lead","Support","Create","Plan"])
    q2 = st.radio("You value:", ["Power","Wisdom","Love","Joy"])
    q3 = st.radio("Pick symbol:", ["Thunderbolt","Owl","Dove","Lyre"])
    if st.button("Reveal deity"):
        if q2=="Wisdom" or q3=="Owl":
            st.markdown("### Athena — Strategy & Wisdom")
            st.write("Themes: owls, armor, protective symbols")
        elif q2=="Love" or q3=="Dove":
            st.markdown("### Aphrodite — Love & Beauty")
            st.write("Themes: love-narratives, beauty cult images")
        elif q2=="Power" or q3=="Thunderbolt":
            st.markdown("### Zeus — Authority")
            st.write("Themes: thrones, lightning, oath scenes")
        else:
            st.markdown("### Apollo — Harmony, prophecy, arts")
            st.write("Themes: lyres, prophetic scenes, sun imagery")

# ---------- Mythic Lineages (explanations first + network) ----------
elif page == "Mythic Lineages":
    st.header("Mythic Lineages — Explanations (museum style)")
    st.write("Below are concise museum-style explanations for core mythic relations. The network visualization follows as a complementary interactive view.")

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
        ("Zeus","Heracles","parent"),
        ("Perseus","Theseus","influence"),
        ("Theseus","Achilles","influence"),
        ("Medusa","Perseus","conflict"),
        ("Minotaur","Theseus","conflict"),
        ("Cyclops","Poseidon","associate"),
    ]

    def local_relation_explanation(a,b,rel):
        if rel=="parent":
            return f"🔹 {a} → {b}\n\n{a} is an ancestor or progenitor figure; {b} inherits a domain or role that shapes later mythic narratives."
        if rel=="conflict":
            return f"🔹 {a} → {b}\n\nConflict or antagonism defines their relation; such stories often stage trials and moral lessons."
        if rel=="influence":
            return f"🔹 {a} → {b}\n\nA narrative or symbolic influence: one figure's story shapes the other's attributes, reputation, or heroic lineage."
        if rel=="associate":
            return f"🔹 {a} → {b}\n\nAn associative link: the two figures often appear together or share a domain in mythic iconography."
        return f"🔹 {a} → {b}\n\nRelationship: {rel}."

    # Immediately display explanations (no click required)
    for a,b,rel in RELS:
        st.markdown(local_relation_explanation(a,b,rel))

    st.markdown("---")
    st.write("Interactive network (supplementary). If pyvis/networkx is available, an interactive view will appear below.")
    try:
        import networkx as nx
        from pyvis.network import Network
    except Exception:
        st.info("Interactive network not available (pyvis/networkx missing). Install them to enable the visualization.")
    else:
        G = nx.Graph()
        for a,b,rel in RELS:
            G.add_node(a); G.add_node(b); G.add_edge(a,b,relation=rel)
        from pyvis.network import Network as PyNet
        nt = PyNet(height="600px", width="100%", bgcolor="#ffffff", font_color="black", notebook=False)
        for n in G.nodes():
            nt.add_node(n, label=n, title=n)
        for u,v,data in G.edges(data=True):
            nt.add_edge(u, v, title=data.get("relation",""))
        tmpfile = "/tmp/myth_network.html"
        try:
            nt.show(tmpfile)
            with open(tmpfile, "r", encoding="utf-8") as f:
                html = f.read()
            st.components.v1.html(html, height=650, scrolling=True)
        except Exception as e:
            st.error(f"Failed to render interactive network: {e}")

# ---------- Myth Stories (rewritten page) ----------
elif page == "Myth Stories":
    st.header("📘 Myth Stories — Museum-style Narrative & Artwork Commentary")
    st.write("Select a character, then search MET for filtered works; choose one artwork and generate a museum-style Myth Narrative and Art Commentary (in English).")

    character = st.selectbox("Choose a character", sorted(MYTH_DB.keys()))
    st.write("Local seed (if available):")
    st.info(MYTH_DB.get(character, "No local seed stored — AI can generate one on demand."))

    # Step: Search MET (filtered) for related works
    if st.button("Search MET for this character (filtered)"):
        aliases = generate_aliases(character)
        all_ids = []
        p = st.progress(0)
        for i, a in enumerate(aliases):
            ids = met_search_ids(a, max_results=120)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate objects; fetching and filtering metadata...")

        filtered = []
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m and is_greek_roman_meta(m):
                thumb = m.get("primaryImageSmall") or m.get("primaryImage") or (m.get("additionalImages") or [None])[0]
                filtered.append({"id": oid, "meta": m, "thumb": thumb})
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.005)
        p2.empty()
        st.session_state["myth_search_results"] = filtered
        st.success(f"{len(filtered)} likely Greek/Roman works found.")

    results = st.session_state.get("myth_search_results", [])
    meta = None
    if results:
        cols = st.columns(3)
        st.write("Click a thumbnail to select artwork for commentary:")
        for idx, rec in enumerate(results):
            thumb = rec.get("thumb")
            mid = rec.get("id")
            with cols[idx % 3]:
                if thumb:
                    if st.button(f"Select {mid}", key=f"sel_{mid}"):
                        try:
                            meta = rec.get("meta")
                            st.session_state["myth_selected_meta"] = meta
                        except Exception:
                            meta = None
                    st.image(thumb, caption=f"{rec['meta'].get('title','Untitled')} ({mid})", use_column_width=True)
                else:
                    st.write(f"No image for {mid}")
    else:
        st.info("No search results. Click 'Search MET for this character (filtered)'.")
    # Load selected meta (if user selected)
    if "myth_selected_meta" in st.session_state:
        meta = st.session_state.get("myth_selected_meta")

    if meta:
        st.markdown("---")
        st.markdown(f"### Selected artwork — {meta.get('title') or 'Untitled'}")
        img_url = meta.get("primaryImage") or meta.get("primaryImageSmall") or ""
        if img_url:
            st.image(img_url, width=360)
        st.write(f"**Artist**: {meta.get('artistDisplayName') or 'Unknown'}")
        st.write(f"**Date**: {meta.get('objectDate') or 'Unknown'}")
        st.write(f"**Medium**: {meta.get('medium') or 'Unknown'}")
        st.write(f"[Open on MET]({meta.get('objectURL')})")

    st.markdown("---")
    st.subheader("Generate museum-style narrative & commentary")
    st.write("If no local seed exists for the character, the app can generate a concise myth seed automatically (via AI) before producing full narrative + commentary.")

    generate_seed_if_missing = st.checkbox("Auto-generate seed if missing", value=True)
    if st.button("Generate Story & Commentary (AI)"):
        # prepare seed
        seed = MYTH_DB.get(character, "")
        if not seed and generate_seed_if_missing:
            # call OpenAI to generate a brief seed (if API key provided)
            if "OPENAI_API_KEY" in st.session_state and st.session_state["OPENAI_API_KEY"]:
                try:
                    from openai import OpenAI
                    oa = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
                    prompt_seed = f"Write a 1-2 sentence myth seed about the Greek/Roman figure '{character}', suitable for a museum audio-guide summary."
                    resp_seed = oa.responses.create(model="gpt-4.1-mini", input=prompt_seed)
                    seed = (resp_seed.output_text or "").strip()
                except Exception as e:
                    st.warning(f"Auto-seed generation failed: {e}. Proceeding without seed.")
                    seed = ""
            else:
                st.info("No OpenAI key — cannot auto-generate seed. You can proceed without a seed.")
                seed = ""

        if not seed and not meta:
            st.warning("No seed available and no artwork selected — generate a seed or choose an artwork.")
        else:
            safe_seed = (seed or "").replace("{", "{{").replace("}", "}}")
            # prepare meta variables
            title = meta.get("title", "Untitled") if meta else None
            artist = meta.get("artistDisplayName", "Unknown") if meta else None
            date = meta.get("objectDate", "Unknown") if meta else None

            if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
                st.warning("Enter your OpenAI API Key in the sidebar and click Save to enable AI generation.")
            else:
                try:
                    from openai import OpenAI
                except Exception:
                    st.error("OpenAI SDK not installed. Add 'openai>=1.0.0' to requirements.txt and redeploy.")
                    st.stop()

                client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])

                # Build prompt depending on whether an artwork is selected
                if meta:
                    prompt = f"""
You are an art historian and museum narrator. Using the myth seed and the artwork metadata, produce two sections:

1) Myth Narrative — a concise, emotive museum audio-guide style narrative about {character}.
Based on this seed: {safe_seed}

2) Art Commentary — analyze the selected artwork titled "{title}", by {artist}, dated {date}.
Discuss composition, lighting, pose, symbolism, and how the image relates to the myth. Keep language accessible to students and exhibition visitors.
"""
                else:
                    prompt = f"""
You are an art historian and museum narrator. Produce a concise, emotive museum audio-guide style narrative about {character}.
Based on this seed: {safe_seed}
"""

                with st.spinner("Generating..."):
                    try:
                        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
                        text_out = resp.output_text or "[No output]"
                    except Exception as e:
                        text_out = f"[Generation failed: {e}]"

                # Present result split if possible
                if meta and "---" in text_out:
                    parts = [p.strip() for p in text_out.split("---") if p.strip()]
                    if len(parts) >= 1:
                        st.markdown("### ✨ Myth Narrative")
                        st.write(parts[0])
                    if len(parts) >= 2:
                        st.markdown("### ✨ Art Commentary")
                        st.write(parts[1])
                else:
                    st.markdown("### 📖 Generated Text")
                    st.write(text_out)

                st.download_button("Download story (txt)", data=text_out, file_name=f"{character}_story.txt", mime="text/plain")

# ---------- Style Transfer ----------
elif page == "Style Transfer":
    st.header("🎨 AI Style Transfer — Blend Content + Style Images")
    st.write("Upload a content image and a style image. Provide OpenAI API key (sidebar) to use this feature.")
    if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
        st.warning("Please enter your OpenAI API key in the sidebar to use this feature.")
    else:
        try:
            from openai import OpenAI
        except Exception:
            st.error("OpenAI SDK is not installed in this environment. Add 'openai>=1.0.0' to requirements.txt and redeploy.")
            st.stop()
        import base64
        client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
        content_img = st.file_uploader("Content Image", type=["png","jpg","jpeg"], key="content")
        style_img = st.file_uploader("Style Image", type=["png","jpg","jpeg"], key="style")
        if content_img:
            st.image(content_img, caption="Content Image", width=300)
        if style_img:
            st.image(style_img, caption="Style Image", width=300)
        if content_img and style_img and st.button("Generate Style Transfer"):
            with st.spinner("Generating stylized image..."):
                try:
                    content_bytes = content_img.read()
                    style_bytes = style_img.read()
                    content_b64 = base64.b64encode(content_bytes).decode()
                    style_b64 = base64.b64encode(style_bytes).decode()
                    result = client.images.generate(
                        model="gpt-image-1",
                        prompt="Blend the content image with the style image into a single stylized artwork.",
                        size="1024x1024",
                        image=[
                            {"data": content_b64},
                            {"data": style_b64}
                        ]
                    )
                    image_base64 = result.data[0].b64_json
                    final_image = base64.b64decode(image_base64)
                    st.image(final_image, caption="Stylized Output", use_column_width=True)
                    st.download_button("Download Stylized Image", data=final_image, file_name="style_transfer.png", mime="image/png")
                except Exception as e:
                    st.error(f"Failed to generate image: {e}")

# ---------- AI Interpretation ----------
elif page == "AI Interpretation":
    st.header("AI Interpretation for Dataset")
    question = st.text_input("Ask AI about your dataset or network:")
    if question:
        if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
            st.warning("Please enter your OpenAI API key in the sidebar.")
        else:
            try:
                from openai import OpenAI
            except Exception:
                st.error("OpenAI SDK not installed. Add 'openai>=1.0.0' to requirements.txt.")
                st.stop()
            client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
            dataset = st.session_state.get("analysis_dataset") or []
            summary_text = json.dumps([{"objectID": m.get("objectID"), "title": m.get("title")} for m in dataset[:10]], ensure_ascii=False)
            prompt = f"You are an art historian and data analyst. Dataset sample:\n{summary_text}\nQuestion: {question}"
            with st.spinner("Querying AI..."):
                try:
                    resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
                    answer = resp.output_text or "[No answer]"
                except Exception as e:
                    answer = f"[AI query failed: {e}]"
            st.markdown("### Answer")
            st.write(answer)

# ---------- About ----------
elif page == "About":
    st.header("About")
    st.write("Created by Pengwei He for the Final Assessment — Mythic Art Explorer.")
    st.write("This version improves Myth Stories (museum narration) and filters MET results to better match Greek/Roman myth contexts.")

# ---------- END ----------

