# app.py
"""
Mythic Art Explorer — Masonry Gallery + Modal (floating arrows) — Stable minimal-deps edition
A: automatic responsive columns (CSS media queries)
1: floating arrows left/right in modal
Notes:
 - Uses MET Collection API (no image downloading)
 - Minimal runtime deps to avoid build failures on Streamlit Cloud
 - OpenAI is optional (not installed by default)
"""

import streamlit as st
import requests
import math
import time
import collections
import json
from typing import List, Dict, Optional
import plotly.express as px

# ---------- Config ----------
st.set_page_config(page_title="Mythic Art Explorer", layout="wide")
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

MYTH_LIST = [
    "Zeus","Hera","Athena","Apollo","Artemis","Aphrodite","Hermes","Dionysus","Ares","Hephaestus",
    "Poseidon","Hades","Demeter","Persephone","Hestia","Heracles","Perseus","Achilles","Odysseus",
    "Theseus","Jason","Medusa","Minotaur","Sirens","Cyclops","Centaur","Prometheus","Orpheus",
    "Eros","Nike","The Muses","The Fates","The Graces","Hecate","Atlas","Pandora"
]

FIXED_BIOS = {
    "Zeus": "Zeus: king of the Olympian gods, lord of sky and thunder — often pictured with thunderbolt/eagle.",
    "Athena": "Athena: goddess of wisdom, craft and strategic warfare — often shown with an owl / helmet.",
    "Medusa": "Medusa: one of the Gorgons — a powerful, ambivalent symbol in ancient and modern art.",
    "Perseus": "Perseus: the hero who beheaded Medusa and rescued Andromeda."
}

# ---------- Helpers: MET API (no heavy libs) ----------
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
    aliases += [f"{name} myth", f"{name} greek"]
    # dedupe while preserving order
    seen = set(); out = []
    for a in aliases:
        if a not in seen:
            seen.add(a); out.append(a)
    return out

# ---------- Sidebar ----------
st.sidebar.title("Mythic Art Explorer")
st.sidebar.markdown("Browse MET artworks for Greek myths — Masonry gallery + modal viewer.")
st.sidebar.markdown("---")
page = st.sidebar.radio("Page", [
    "Home",
    "Mythic Art Explorer",
    "Art Data",
    "Interactive Tests",
    "Mythic Lineages",
    "Style Transfer"   # ⭐ 新增页面
], index=1)
st.sidebar.markdown("---")
st.sidebar.info("OpenAI integration is optional. For AI features, install `openai` and paste your key here.")
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
    st.write("Quick steps: Myhtic Art Explorer → choose figure → Fetch works → Click thumbnails.")
# ---------- Mythic Art Explorer: Masonry gallery + HTML modal ----------
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
            # prefer primaryImageSmall for thumbnails, fallback to primaryImage or additionalImages
            thumb_url = meta.get("primaryImageSmall") or meta.get("primaryImage")
            # full image: prefer primaryImage, else additionalImages[0]
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
        # Prepare items to pass into embedded HTML
        items_json = json.dumps(thumbs)
        # Masonry HTML/CSS/JS (responsive columns via media queries)
        html = f"""
        <style>
        /* Masonry using CSS columns + simple card styles */
        .masonry-container {{
          column-gap: 16px;
          padding: 6px;
        }}
        /* Responsive column counts: A = automatic by viewport */
        @media (min-width: 1400px) {{ .masonry-container {{ column-count: 4; }} }}
        @media (min-width: 1000px) and (max-width: 1399px) {{ .masonry-container {{ column-count: 3; }} }}
        @media (min-width: 700px) and (max-width: 999px) {{ .masonry-container {{ column-count: 2; }} }}
        @media (max-width: 699px) {{ .masonry-container {{ column-count: 1; }} }}

        .masonry-item {{
          display: inline-block;
          width: 100%;
          margin: 0 0 16px;
          break-inside: avoid;
          box-shadow: 0 2px 8px rgba(0,0,0,0.08);
          border-radius: 6px;
          overflow: hidden;
          background: #fff;
        }}
        .masonry-item img {{
          width: 100%;
          height: auto;
          display: block;
          cursor: pointer;
        }}
        .masonry-meta {{
          padding: 8px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
          font-size: 13px;
        }}
        /* Modal overlay */
        .m-modal {{
          position: fixed;
          z-index: 9999;
          left: 0; top: 0;
          width: 100%; height: 100%;
          background: rgba(0,0,0,0.8);
          display: none;
          align-items: center;
          justify-content: center;
        }}
        .m-modal.open {{ display: flex; }}
        .m-modal-content {{
          max-width: 92%;
          max-height: 92%;
          position: relative;
          display:flex;
          gap:16px;
          color: #111;
        }}
        .m-modal-image {{
          max-width: 72vw;
          max-height: 88vh;
          overflow: hidden;
          background: #111;
          border-radius: 6px;
        }}
        .m-modal-image img {{
          display:block;
          max-width:100%;
          height:auto;
          margin: 0 auto;
        }}
        .m-modal-meta {{
          width: 340px;
          max-height: 88vh;
          overflow:auto;
          background: #fff;
          padding: 16px;
          border-radius: 6px;
        }}
        /* Floating arrows (A + 1 style) */
        .m-arrow {{
          position: absolute;
          top: 50%;
          transform: translateY(-50%);
          width: 56px;
          height: 56px;
          border-radius: 28px;
          background: rgba(255,255,255,0.18);
          color: #fff;
          display:flex;
          align-items:center;
          justify-content:center;
          font-size: 28px;
          cursor:pointer;
          user-select:none;
          transition: background .12s;
        }}
        .m-arrow:hover {{ background: rgba(255,255,255,0.28); }}
        .m-arrow.left {{ left: 8px; }}
        .m-arrow.right {{ right: 8px; }}
        .m-close {{
          position:absolute; right:8px; top:8px;
          background: rgba(0,0,0,0.4); color:#fff; border-radius:6px; padding:6px 8px; cursor:pointer;
        }}
        @media (max-width:900px){{
          .m-modal-content{{flex-direction:column; align-items:center}}
          .m-modal-meta{{width:100%; max-height:40vh}}
          .m-modal-image{{max-width:92vw}}
          .m-arrow{{width:44px;height:44px;font-size:22px}}
        }}
        </style>

        <div id="gallery" class="masonry-container"></div>

        <!-- Modal -->
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

        // build gallery
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

        // Modal logic
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

        // initial build
        buildGallery();
        </script>
        """
        st.components.v1.html(html, height=700, scrolling=True)
# ---------- ART DATA ----------
elif page == "Art Data":
    st.header("Art Data — Lightweight dataset summary (no pandas required)")
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
        # lightweight stats
        def stats_from(ds):
            years=[]; mediums=[]; cultures=[]; tags=[]
            gvr = {"greek":0,"roman":0,"other":0}
            for m in ds:
                y = m.get("objectBeginDate")
                if isinstance(y,int): years.append(y)
                od = (m.get("objectDate") or "") 
                # naive parse
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

        # CSV export using built-in csv module (no pandas)
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
    st.write("Two short tests — richer interpretation than before.")
    st.subheader("Quick Deity (short)")
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

    st.markdown("---")
    st.subheader("Short archetype (8 items)")
    qs = [
        "I prefer leading groups.", "I trust logic over feelings.", "I feel energized by creativity.",
        "I protect people close to me.", "I seek new experiences even if risky.", "I rely on rituals/tradition.",
        "I act quickly in crises.", "I enjoy deep discussion about meaning."
    ]
    answers = []
    for i, q in enumerate(qs):
        answers.append(st.slider(f"{i+1}. {q}", 1, 5, 3, key=f"t{i}"))
    if st.button("Reveal archetype"):
        s_leader = answers[0] + answers[6]
        s_logic = answers[1] + answers[7]
        s_creative = answers[2] + answers[4]
        s_protect = answers[3] + answers[5]
        scores = {"Guardian": s_protect + s_leader, "Sage": s_logic, "Seeker": s_creative, "Warrior": s_leader + s_creative}
        arche = max(scores, key=scores.get)
        st.markdown(f"## {arche}")
        if arche=="Guardian":
            st.write("Guardian — order, protection, duty. Visual: thrones, ritual objects.")
        elif arche=="Sage":
            st.write("Sage — knowledge, strategy. Visual: owls, teaching scenes.")
        elif arche=="Seeker":
            st.write("Seeker — experience, ecstasy. Visual: feasts, music.")
        else:
            st.write("Warrior — challenge, mastery. Visual: battle scenes.")

# ---------- Mythic Lineages ----------
elif page == "Mythic Lineages":
    st.header("Mythic Lineages — Simplified network view")
    edges = [
        ("Chaos","Gaia"),("Gaia","Uranus"),("Uranus","Cronus"),("Cronus","Zeus"),
        ("Cronus","Hera"),("Cronus","Poseidon"),("Cronus","Hades"),
        ("Zeus","Athena"),("Zeus","Apollo"),("Zeus","Artemis"),("Zeus","Ares"),
        ("Zeus","Hermes"),("Zeus","Dionysus"),("Zeus","Perseus"),("Zeus","Heracles"),
        ("Perseus","Theseus"),("Theseus","Achilles"),("Medusa","Perseus"),
        ("Minotaur","Theseus"),("Cyclops","Poseidon")
    ]
    try:
        import networkx as nx
        import plotly.graph_objects as go
        G = nx.DiGraph()
        G.add_edges_from(edges)
        pos = nx.spring_layout(G, seed=42, k=0.6)
        edge_x=[]; edge_y=[]
        for s, t in G.edges():
            x0,y0 = pos[s]; x1,y1 = pos[t]
            edge_x += [x0, x1, None]; edge_y += [y0, y1, None]
        node_x=[]; node_y=[]; labels=[]
        for n in G.nodes():
            x,y = pos[n]; node_x.append(x); node_y.append(y); labels.append(n)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1,color='#999'), hoverinfo='none'))
        fig.add_trace(go.Scatter(x=node_x, y=node_y, mode='markers+text', text=labels, textposition='top center',
                                 marker=dict(size=18, color='#3A8DFF')))
        fig.update_layout(showlegend=False, xaxis=dict(visible=False), yaxis=dict(visible=False), height=700)
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.info("Interactive network libs not available — showing adjacency lists instead.")
        parents = {}
        for a,b in edges:
            parents.setdefault(a, []).append(b)
        for p, children in parents.items():
            st.markdown(f"**{p}** → " + ", ".join(children))
# ---------- Style Transfer (NEW PAGE) ----------
elif page == "Style Transfer":
    st.header("🎨 AI Style Transfer — Blend two images into new art")

    st.write("""
        Upload a **content image** and a **style image**.  
        The AI model will generate a new artwork combining both.  
        Best results examples:
        - Portrait + Van Gogh  
        - Landscape + Ukiyo-e  
        - Statue + Modern painting  
    """)

    if "OPENAI_API_KEY" not in st.session_state:
        st.warning("Please enter your OpenAI API key in the sidebar to use this feature.")
    else:
        # ------------------------------------
        # NEW OPENAI SDK (2024+)  <-- FIXED
        # ------------------------------------
        from openai import OpenAI
        import base64
        client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])

        st.subheader("1. Upload Images")
        content_img = st.file_uploader("Content Image", type=["png", "jpg", "jpeg"], key="content")
        style_img = st.file_uploader("Style Image", type=["png", "jpg", "jpeg"], key="style")

        if content_img:
            st.image(content_img, caption="Content Image", width=300)
        if style_img:
            st.image(style_img, caption="Style Image", width=300)

        if content_img and style_img:
            if st.button("Generate Style Transfer Image"):
                with st.spinner("Generating stylized image..."):

                    # ---- Convert both images to base64 ----
                    content_bytes = content_img.read()
                    style_bytes = style_img.read()

                    content_b64 = base64.b64encode(content_bytes).decode()
                    style_b64 = base64.b64encode(style_bytes).decode()

                    # ---- Call GPT-Image Model ----
                    result = client.images.generate(
                        model="gpt-image-1",
                        prompt="Blend the content image with the style image into a single stylized artwork.",
                        size="1024x1024",
                        image=[
                            {"data": content_b64},
                            {"data": style_b64}
                        ]
                    )

                    # ---- Decode result ----
                    image_base64 = result.data[0].b64_json
                    final_image = base64.b64decode(image_base64)

                    st.subheader("🎉 Result")
                    st.image(final_image, caption="Stylized Output", use_column_width=True)

                    # ---- Download ----
                    st.download_button(
                        label="Download Stylized Image",
                        data=final_image,
                        file_name="style_transfer.png",
                        mime="image/png"
                    )

                    c_bytes = content_img.read()
                    s_bytes = style_img.read()

                    c_b64 = base64.b64encode(c_bytes).decode("utf-8")
                    s_b64 = base64.b64encode(s_bytes).decode("utf-8")

                    result = openai.images.generate(
                        model="gpt-image-1",
                        prompt="Blend these two images: use the first image as content and second image as style.",
                        images=[c_b64, s_b64],
                        size="1024x1024"
                    )

                    final_b64 = result.data[0].b64_json
                    final_img = base64.b64decode(final_b64)

                    st.subheader("🎉 Result")
                    st.image(final_img, use_column_width=True)

                    st.download_button(
                        "Download Result",
                        final_img,
                        file_name="style_transfer_result.png",
                        mime="image/png"
                    )
