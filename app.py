# app.py (final_app.py)
"""
Mythic Art Explorer — Final integrated app (cleaned & fixed)
- MET browsing (masonry + modal)
- Art Data (Plotly)
- Interactive Mythic Lineages (PyVis) + Museum-style relationship explanations
- Myth Stories (AI-generated narrative + artwork commentary)
- Style Transfer (gpt-image-1)
Notes:
- Add these to requirements.txt: streamlit, plotly, networkx, pyvis, requests, pillow, openai>=1.0.0
- Provide OpenAI API key in the sidebar for AI features
"""

import streamlit as st
import requests
import time
import collections
import json
from typing import List, Dict
import plotly.express as px

# ---------- Config ----------
st.set_page_config(page_title="Mythic Art Explorer", layout="wide")

# ---------- Basic data / seeds ----------
MYTH_DB = {
    "Zeus": "Zeus, king of the Olympian gods, wielding thunderbolts and ruling the sky.",
    "Athena": "Athena, goddess of wisdom and strategic warfare, often shown with an owl and armor.",
    "Medusa": "Medusa, the Gorgon whose gaze turns mortals to stone; a tragic figure with complex symbolism.",
    "Perseus": "Perseus, the hero who beheaded Medusa and rescued Andromeda, aided by the gods.",
    "Orpheus": "Orpheus, the musician who ventured into the Underworld to recover his wife Eurydice."
}

MYTH_LIST = [
    "Zeus","Hera","Athena","Apollo","Artemis","Aphrodite","Hermes","Dionysus","Ares","Hephaestus",
    "Poseidon","Hades","Demeter","Persephone","Hestia","Heracles","Perseus","Achilles","Odysseus",
    "Theseus","Jason","Medusa","Minotaur","Sirens","Cyclops","Centaur","Prometheus","Orpheus",
    "Eros","Nike","Hecate","Atlas","Pandora","Narcissus","Echo","Rhea","Cronus"
]

FIXED_BIOS = {
    "Zeus": "Zeus: king of the Olympian gods, lord of sky and thunder — often pictured with thunderbolt/eagle.",
    "Athena": "Athena: goddess of wisdom, craft and strategic warfare — often shown with an owl / helmet.",
    "Medusa": "Medusa: one of the Gorgons — a powerful, ambivalent symbol in ancient and modern art.",
    "Perseus": "Perseus: the hero who beheaded Medusa and rescued Andromeda."
}

# ---------- MET API helpers ----------
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
st.sidebar.markdown("Browse MET artworks for Greek myths — Masonry gallery + modal viewer.")
st.sidebar.markdown("---")
st.sidebar.markdown("### Main Pages")
main_pages = ["Home", "Mythic Art Explorer", "Art Data", "Interactive Tests", "Mythic Lineages", "About"]
sel_main = st.sidebar.selectbox("Main Pages", main_pages, index=1)
st.sidebar.markdown("### AI Tools")
ai_tools = ["AI Interpretation", "Style Transfer", "Myth Stories"]
sel_tool = st.sidebar.selectbox("AI Tools (choose one or None)", ["None"] + ai_tools, index=0)

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
    st.write("""
        Explore Greek myth characters and real artworks from The MET.  
        Gallery is Masonry-style (responsive) — click thumbnails to open a fullscreen modal with Prev/Next arrows.
    """)
    st.write("Quick steps: Mythic Art Explorer → choose figure → Fetch works → Click thumbnails.")
    st.write("Use the AI Tools for style transfer and myth storytelling.")

# ---------- Mythic Art Explorer ----------
elif page == "Mythic Art Explorer":
    st.header("Mythic Art Explorer — Greek Figures & Artworks")
    selected = st.selectbox("Choose a mythic figure", MYTH_LIST, index=0)
    st.write(FIXED_BIOS.get(selected, f"{selected} — canonical figure in Greek myth."))
    st.markdown("**Search aliases (used when querying MET):**")
    st.write(generate_aliases(selected))

    max_results = st.slider("Max MET records per alias", 30, 600, 200, step=10)
    if st.button("Fetch related works (image URLs)"):
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
        st.info(f"Found {len(all_ids)} candidate object IDs. Building thumbnail list...")

        thumbs = []
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            meta = met_get_object_cached(oid)
            if not meta:
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
        st.success(f"Prepared {len(thumbs)} thumbnail records (URLs).")

    thumbs = st.session_state.get("thumbs_data", [])
    if not thumbs:
        st.info("No thumbnails yet. Click 'Fetch related works (image URLs)'.")
    else:
        st.write(f"Showing {len(thumbs)} artworks — the gallery below uses a responsive masonry layout.")
        items_json = json.dumps(thumbs)
        # Masonry + modal HTML (same as earlier)
        html = f"""
        <style>
        .masonry-container {{ column-gap: 16px; padding: 6px; }}
        @media (min-width: 1400px) {{ .masonry-container {{ column-count: 4; }} }}
        @media (min-width: 1000px) and (max-width: 1399px) {{ .masonry-container {{ column-count: 3; }} }}
        @media (min-width: 700px) and (max-width: 999px) {{ .masonry-container {{ column-count: 2; }} }}
        @media (max-width: 699px) {{ .masonry-container {{ column-count: 1; }} }}
        .masonry-item {{ display: inline-block; width: 100%; margin: 0 0 16px; break-inside: avoid; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-radius: 6px; overflow: hidden; background: #fff; }}
        .masonry-item img {{ width: 100%; height: auto; display: block; cursor: pointer; }}
        .masonry-meta {{ padding: 8px; font-size: 13px; }}
        .m-modal {{ position: fixed; z-index: 9999; left: 0; top:0; width:100%; height:100%; background: rgba(0,0,0,0.8); display:none; align-items:center; justify-content:center; }}
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
          modal.setAttribute('aria-hidden', 'false');
        }}
        function closeModal() {{
          modal.classList.remove('open');
          modal.setAttribute('aria-hidden', 'true');
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
            if m:
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

# ---------- Mythic Lineages (PyVis + explanations) ----------
elif page == "Mythic Lineages":
    st.header("Mythic Lineages — Interactive Force-directed Network")
    st.write("Interactive network of mythic figures — drag nodes, hover for short bio, click a node to highlight relations.")

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

    BIO = {
        "Zeus":"King of the Olympian gods; thunder, authority.",
        "Athena":"Goddess of wisdom and strategic warfare; associated with the owl.",
        "Perseus":"Hero who beheaded Medusa and rescued Andromeda.",
        "Medusa":"One of the Gorgons; her gaze turns mortals to stone.",
        "Orpheus":"Legendary musician; journeyed to the Underworld for Eurydice.",
        "Narcissus":"A youth who fell in love with his reflection.",
        "Gaia":"Primordial Earth goddess.",
        "Cronus":"Titan who fathered the first generation of Olympians.",
        "Hera":"Queen of the gods; marriage and women.",
        "Poseidon":"God of the sea."
    }

    # Try importing pyvis/networkx; show friendly message if absent
    try:
        import networkx as nx
        from pyvis.network import Network
        import streamlit.components.v1 as components
    except Exception:
        st.error("Interactive network requires 'pyvis' and 'networkx'. Add them to requirements.txt and redeploy.")
        st.stop()

    # build graph
    G = nx.Graph()
    for a,b,rel in RELS:
        G.add_node(str(a))
        G.add_node(str(b))
        G.add_edge(str(a), str(b), relation=rel)

    nt = Network(height="700px", width="100%", bgcolor="#ffffff", font_color="black", notebook=False)
    try:
        nt.force_atlas_2based()
    except Exception:
        pass

    for n in G.nodes():
        title = BIO.get(n, "No bio available.")
        nt.add_node(n, label=n, title=title, value=2)

    for u,v,data in G.edges(data=True):
        rel = data.get("relation", "")
        nt.add_edge(u, v, title=rel, value=1)

    tmpfile = "/tmp/myth_network.html"
    try:
        nt.show(tmpfile)
        with open(tmpfile, "r", encoding="utf-8") as f:
            components_html = f.read()
        st.components.v1.html(components_html, height=720)
    except Exception as e:
        st.error(f"Failed to render interactive network: {e}")

    # Fallback: show adjacency list (also used to build explanations)
    parents = {}
    for a,b,_ in RELS:
        parents.setdefault(a, []).append(b)

    st.markdown("### Parent → Children")
    for p, children in parents.items():
        st.markdown(f"**{p}** → {', '.join(children)}")

    # --- Relationship explanations (Museum-style) ---
    st.markdown("---")

    def local_relation_explanation(a, b, rel):
        if rel == "parent":
            return f"🔹 {a} → {b}\n\n{a} and {b} share a parent-child relationship. {a} represents a progenitor or ancestral figure in myth, while {b} inherits specific domains or roles (e.g., governance, the sea, the underworld, or wisdom)."
        if rel == "conflict":
            return f"🔹 {a} → {b}\n\nThe relationship between {a} and {b} is primarily adversarial or conflictual. Such narratives often highlight trials, contests, or moral lessons within the mythic tradition."
        if rel == "influence":
            return f"🔹 {a} → {b}\n\n{a} exerts notable narrative or symbolic influence on {b}, representing the transmission of heroism, cultural patterns, or skills and symbols."
        if rel == "associate":
            return f"🔹 {a} → {b}\n\n{a} and {b} share an associative relationship, often appearing together as deities of similar domains, kin, or recurring paired figures in myth."
        return f"🔹 {a} → {b}\n\nRelationship type: {rel}. This connection carries specific meaning within mythic traditions and helps interpret narrative structures and symbolic correspondences."

    raw_items = [{"a": a, "b": b, "rel": rel} for a,b,rel in RELS]

    if st.button("Explain Mythic Relationships (Museum style)"):
        with st.spinner("Generating relationship explanations..."):
            explanations = []
            # Use OpenAI to refine if key provided
            if "OPENAI_API_KEY" in st.session_state and st.session_state["OPENAI_API_KEY"]:
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
                    items_text = "\n".join([f"{i+1}. {it['a']} -> {it['b']} (relation: {it['rel']})" for i, it in enumerate(raw_items)])
                    prompt = f"""
You are an art historian writing museum-label style explanations. Given the following mythic relations, produce a clear, academic museum-text explanation for each item. Use one paragraph per relation. Keep each paragraph concise (2-4 sentences), formal and accessible to museum visitors.

Data:
{items_text}

Return only the explanations in plain text, each starting with the '🔹' bullet followed by the relation line.
"""
                    resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
                    refined = resp.output_text or ""
                    if "🔹" in refined:
                        parts = [p.strip() for p in refined.split("🔹") if p.strip()]
                        for p in parts:
                            explanations.append("🔹 " + p)
                    else:
                        explanations = [refined]
                except Exception as e:
                    st.warning(f"OpenAI refinement failed: {e}. Using local templates.")
                    explanations = [local_relation_explanation(it['a'], it['b'], it['rel']) for it in raw_items]
            else:
                explanations = [local_relation_explanation(it['a'], it['b'], it['rel']) for it in raw_items]

            st.subheader("Mythic Relationship Explanations (Museum-style)")
            out_text = ""
            for ex in explanations:
                st.markdown(ex.replace("\n\n", "\n\n"))
                out_text += ex + "\n\n"
            st.download_button("Download relationship explanations (txt)", data=out_text, file_name="mythic_relationships.txt")

# ---------- Style Transfer ----------
elif page == "Style Transfer":
    st.header("🎨 AI Style Transfer — Blend two images into new art")
    st.write("Upload a content image and a style image. The AI model will blend them into a stylized artwork.")

    if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
        st.warning("Please enter your OpenAI API key in the sidebar to use this feature.")
    else:
        try:
            from openai import OpenAI
        except Exception:
            st.error("The OpenAI SDK is not installed in the environment. Add 'openai>=1.0.0' to requirements.txt.")
            st.stop()

        import base64
        client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])

        content_img = st.file_uploader("Content Image", type=["png","jpg","jpeg"], key="content")
        style_img = st.file_uploader("Style Image", type=["png","jpg","jpeg"], key="style")

        if content_img:
            st.image(content_img, caption="Content Image", width=300)
        if style_img:
            st.image(style_img, caption="Style Image", width=300)

        if content_img and style_img and st.button("Generate Style Transfer Image"):
            with st.spinner("Generating stylized image..."):
                try:
                    content_bytes = content_img.read()
                    style_bytes = style_img.read()
                    content_b64 = base64.b64encode(content_bytes).decode()
                    style_b64 = base64.b64encode(style_bytes).decode()
                    # Note: images.generate may accept different args depending on OpenAI SDK version
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
    question = st.text_input("Ask AI about your network or dataset:")
    if question:
        if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
            st.warning("Please enter your OpenAI API key in the sidebar to use this feature.")
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
                    answer = resp.output_text
                except Exception as e:
                    answer = f"[AI query failed: {e}]"
            st.markdown("### Answer")
            st.write(answer)

# ---------- Myth Stories ----------
elif page == "Myth Stories":
    st.header("📘 Myth Stories — Character Narratives & Artwork Commentary")
    character = st.selectbox("Choose a mythic figure", sorted(MYTH_LIST))
    st.write("Myth seed (local):")
    st.info(MYTH_DB.get(character, "No seed available; AI will craft the story."))

    if st.button("Search related artworks (MET)"):
        st.info("Searching MET for related artworks...")
        all_ids = []
        p = st.progress(0)
        aliases = generate_aliases(character)
        for i, a in enumerate(aliases):
            ids = met_search_ids(a, max_results=40)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.session_state["myth_story_ids"] = all_ids
        st.success(f"Found {len(all_ids)} artworks for {character}.")

    ids = st.session_state.get("myth_story_ids", [])
    meta = None
    if ids:
        chosen_id = st.selectbox("Choose an artwork (optional)", ["None"] + ids)
        if chosen_id and chosen_id != "None":
            try:
                chosen_id = int(chosen_id)
                meta = met_get_object_cached(chosen_id)
            except Exception:
                meta = None
            if meta:
                img_url = meta.get("primaryImageSmall") or meta.get("primaryImage") or ""
                if img_url:
                    st.image(img_url, caption=meta.get("title"), width=360)
                st.markdown(f"### 🖼️ {meta.get('title') or 'Untitled'}")
                st.write(f"**Artist**: {meta.get('artistDisplayName') or 'Unknown'}")
                st.write(f"**Date**: {meta.get('objectDate') or 'Unknown'}")
                st.write(f"**Medium**: {meta.get('medium') or 'Unknown'}")
                st.write(f"[View on MET]({meta.get('objectURL')})")

    st.markdown("---")
    st.subheader("Generate Story & Commentary")
    st.write("You can generate (A) just the myth narrative, or (B) narrative + artwork commentary if a work is selected.")

    if st.button("Generate (AI)"):
        seed = MYTH_DB.get(character, "")
        if not seed:
            st.warning("No myth seed found for this character.")
        else:
            safe_seed = seed.replace("{", "{{").replace("}", "}}")
            # prepare artwork metadata safely
            title = meta.get("title", "Untitled") if meta else "Untitled"
            artist = meta.get("artistDisplayName", "Unknown") if meta else "Unknown"
            date = meta.get("objectDate", "Unknown") if meta else "Unknown"

            if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
                st.warning("Enter your OpenAI API Key in the sidebar to enable AI generation.")
            else:
                try:
                    from openai import OpenAI
                except Exception:
                    st.error("OpenAI SDK not installed. Please add 'openai>=1.0.0' to requirements.txt and redeploy.")
                    st.stop()

                client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])

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
You are an art historian and museum narrator. Produce a concise, emotive museum audio-guide style narrative about {character} based on this seed: {safe_seed}
"""

                with st.spinner("Generating..."):
                    try:
                        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
                        text_out = resp.output_text
                    except Exception as e:
                        text_out = f"[Generation failed: {e}]"

                    st.markdown("### 📖 Generated Text")
                    st.write(text_out)
                    st.download_button("Download story (txt)", data=text_out, file_name=f"{character}_story.txt")

# ---------- About ----------
elif page == "About":
    st.header("About")
    st.write("Created by Pengwei He for the Final Assessment — Mythic Art Explorer.")
    st.write("Features: MET API browsing, data visualization, interactive network, AI story generation, and style-transfer image synthesis.")

# End of app
