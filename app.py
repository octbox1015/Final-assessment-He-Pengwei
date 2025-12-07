# final_app.py
"""
Mythic Art Explorer — Final project (medium-filter MET + 3-part Myth Stories)
- Medium filtering (recommended)
- Myth Stories: 3 parts (Character Overview, Myth Narrative, Artwork Commentary)
- Thumbnails show title, artist, date, medium and MET link
Notes:
- requirements.txt should include:
  streamlit, requests, plotly, networkx, pyvis, pillow, openai>=1.0.0
- Provide OpenAI API key in the sidebar for AI features
"""

import streamlit as st
import requests
import time
import collections
import json
from typing import List, Dict, Optional
import plotly.express as px

# ---------- Page config ----------
st.set_page_config(page_title="Mythic Art Explorer", layout="wide")

# ---------- Local myth seeds (expanded) ----------
MYTH_DB = {
    "Zeus": "Zeus, king of the Olympian gods, wielder of thunder, arbiter of vows and order among gods and humans.",
    "Hera": "Hera, queen of the gods, goddess of marriage, often depicted with regal bearing and peacock symbolism.",
    "Athena": "Athena, goddess of wisdom, craft, and strategic warfare; patroness of cities and heroes.",
    "Apollo": "Apollo, god of music, prophecy, and the sun; associated with lyres and oracles.",
    "Artemis": "Artemis, goddess of the hunt, wilderness, and the lunar sphere; protector of young women and animals.",
    "Aphrodite": "Aphrodite, goddess of love and beauty; associated with desire, sea-born imagery, and the mirror.",
    "Hermes": "Hermes, messenger of the gods; trickster and guide of travelers, merchants, and souls.",
    "Dionysus": "Dionysus, god of wine, ritual ecstasy, theatre, and the loosening of boundaries.",
    "Ares": "Ares, god of war and violent conflict, depicted in battle scenes.",
    "Hephaestus": "Hephaestus, god of craft and metallurgy; maker of divine tools and weapons.",
    "Poseidon": "Poseidon, god of the sea, earthquakes and horses; often shown with a trident.",
    "Hades": "Hades, ruler of the underworld; associated with chthonic imagery and the realm of the dead.",
    "Demeter": "Demeter, goddess of grain and agriculture; her myth explains seasonal cycles.",
    "Persephone": "Persephone, daughter of Demeter and queen of the underworld; her abduction and return explain the seasons.",
    "Heracles": "Heracles, the hero known for his Twelve Labors; a liminal figure between gods and humans.",
    "Perseus": "Perseus, slayer of Medusa and rescuer of Andromeda; aided by divine gifts.",
    "Orpheus": "Orpheus, musician and poet who traveled to the underworld to recover his wife Eurydice.",
    "Narcissus": "Narcissus, youth who fell in love with his own reflection; a tale about vanity and fate.",
    "Medusa": "Medusa, one of the Gorgons whose gaze turns mortals to stone; complex symbol of otherness.",
    "Theseus": "Theseus, Athenian hero who slew the Minotaur and consolidated civic myths.",
    "Achilles": "Achilles, hero of the Trojan War; famed for strength and tragic vulnerability.",
    "Jason": "Jason, leader of the Argonauts in the quest for the Golden Fleece.",
    "Eros": "Eros, god of desire and attraction; often shown as a young figure with bow and arrows.",
    "Nike": "Nike, personification of victory, frequently depicted with wings.",
    "Prometheus": "Prometheus, Titan who gave fire to humanity and suffered divine punishment.",
    "Echo": "Echo, a nymph punished to repeat others' words; associated with love and loss.",
    "Pandora": "Pandora, the first woman in myth whose curiosity leads to the release of troubles upon the world.",
}

# create sorted list for UI
MYTH_LIST = sorted(MYTH_DB.keys())

# ---------- MET API ----------
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

# ---------- Heuristic filter: medium (recommended) ----------
def is_greek_roman_meta_medium(meta: Dict) -> bool:
    """
    Medium-level heuristic:
    - Accept strongly Greek/Roman/Hellenistic by culture/period.
    - Accept works with myth keywords in title/objectName even if period is later (Renaissance/Baroque)
      — this keeps important narrative paintings (e.g., Renaissance Orpheus paintings).
    - Reject clearly unrelated departmental classifications (e.g., modern machinery, textiles without myth keywords).
    """
    if not meta:
        return False

    def contains_any(text, keys):
        if not text:
            return False
        t = str(text).lower()
        return any(k in t for k in keys)

    culture = meta.get("culture") or ""
    period = meta.get("period") or ""
    title = meta.get("title") or ""
    objname = meta.get("objectName") or ""
    classification = meta.get("classification") or ""
    department = meta.get("department") or ""

    positive_culture = ["greek", "hellenistic", "roman", "classical", "greco-roman"]
    myth_keywords = [
        "zeus","hera","athena","apollo","artemis","aphrodite","hermes","dionysus","ares",
        "hephaestus","poseidon","hades","demeter","persephone","heracles","perseus","orpheus",
        "narcissus","medusa","theseus","achilles","jason","eros","nike","prometheus","minotaur",
        "gorgon","eurydice","andromeda","trojan","achilles","cerberus","nymph","myth","mythological"
    ]
    # allowed classifications that often show myth subjects
    allowed_classes = ["sculpture","vessel","ceramics","painting","drawing","print","relief","statuette","stone","marble","bronze","oil on canvas"]

    # Strong positive: culture/period indicates Greek/Roman/Hellenistic
    if contains_any(culture, positive_culture) or contains_any(period, positive_culture):
        return True

    # Title/objectName contains myth keyword -> accept (covers later-period myth paintings)
    if contains_any(title, myth_keywords) or contains_any(objname, myth_keywords):
        return True

    # If classification suggests imagery and title contains some classical words like "god", "hero" rarely
    if contains_any(classification, allowed_classes) and (contains_any(title, ["god","hero","myth","goddess"]) or contains_any(objname, ["god","hero","myth","goddess"])):
        return True

    # Reject if department/classification indicates unrelated collection
    reject_signals = ["costume", "arms and armor", "photographs", "modern and contemporary", "musical instruments", "audio", "textiles"]
    if contains_any(department, reject_signals) or contains_any(classification, reject_signals):
        return False

    return False

# ---------- Helpers ----------
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
st.sidebar.markdown("Explore Greek & Roman myth characters and artworks from The MET.")
st.sidebar.markdown("---")
st.sidebar.markdown("### Main Pages")
main_pages = ["Home", "Mythic Art Explorer", "Art Data", "Interactive Tests", "Mythic Lineages", "Myth Stories", "Style Transfer", "About"]
sel_main = st.sidebar.selectbox("Main Pages", main_pages, index=1)
st.sidebar.markdown("### AI Tools")
ai_tools = ["AI Interpretation"]
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
    st.write("""
        Explore Greek & Roman myth characters and real artworks from The MET.  
        Use 'Mythic Art Explorer' to find relevant images, or 'Myth Stories' to generate museum-style narratives.
    """)

# ---------- Mythic Art Explorer ----------
elif page == "Mythic Art Explorer":
    st.header("Mythic Art Explorer — Browse filtered MET results")
    selected = st.selectbox("Choose a mythic figure", MYTH_LIST, index=0)
    st.write(MYTH_DB.get(selected, ""))
    st.markdown("**Search aliases (used when querying MET):**")
    st.write(generate_aliases(selected))

    max_results = st.slider("Max MET records per alias", 20, 400, 120, step=10)
    if st.button("Fetch related works (medium-filtered)"):
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
        st.info(f"Found {len(all_ids)} candidate object IDs. Fetching metadata and applying medium filter...")

        thumbs = []
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            meta = met_get_object_cached(oid)
            if not meta:
                continue
            if not is_greek_roman_meta_medium(meta):
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
        st.success(f"Prepared {len(thumbs)} thumbnail records (medium-filtered).")

    thumbs = st.session_state.get("thumbs_data", [])
    if not thumbs:
        st.info("No filtered thumbnails yet. Click 'Fetch related works (medium-filtered)'.")
    else:
        st.write(f"Showing {len(thumbs)} artworks — thumbnails include title, artist, date, medium and MET link.")
        items_json = json.dumps(thumbs)
        html = f"""
        <style>
        .masonry-container {{ column-gap: 16px; padding: 6px; }}
        @media (min-width:1400px) {{ .masonry-container {{ column-count:4; }} }}
        @media (min-width:1000px) and (max-width:1399px) {{ .masonry-container {{ column-count:3; }} }}
        @media (min-width:700px) and (max-width:999px) {{ .masonry-container {{ column-count:2; }} }}
        @media (max-width:699px) {{ .masonry-container {{ column-count:1; }} }}
        .masonry-item {{ display:inline-block; width:100%; margin:0 0 16px; break-inside:avoid; box-shadow:0 2px 8px rgba(0,0,0,0.08); border-radius:6px; overflow:hidden; background:#fff; }}
        .masonry-item img {{ width:100%; height:auto; display:block; cursor:pointer; }}
        .masonry-meta {{ padding:8px; font-size:13px; }}
        .m-modal {{ position:fixed; z-index:9999; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.8); display:none; align-items:center; justify-content:center; }}
        .m-modal.open {{ display:flex; }}
        .m-modal-content {{ max-width:92%; max-height:92%; position:relative; display:flex; gap:16px; color:#111; }}
        .m-modal-image {{ max-width:72vw; max-height:88vh; overflow:hidden; background:#111; border-radius:6px; }}
        .m-modal-image img {{ display:block; max-width:100%; height:auto; margin:0 auto; }}
        .m-modal-meta {{ width:340px; max-height:88vh; overflow:auto; background:#fff; padding:16px; border-radius:6px; }}
        .m-arrow {{ position:absolute; top:50%; transform:translateY(-50%); width:56px; height:56px; border-radius:28px; background:rgba(255,255,255,0.18); color:#fff; display:flex; align-items:center; justify-content:center; font-size:28px; cursor:pointer; }}
        .m-close {{ position:absolute; right:8px; top:8px; background:rgba(0,0,0,0.4); color:#fff; border-radius:6px; padding:6px 8px; cursor:pointer; }}
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
            // show title, artist, date, medium, and link
            const title = it.title || 'Untitled';
            const artist = it.artist || 'Unknown';
            const date = it.date || '—';
            const medium = it.medium || '';
            meta.innerHTML = `<strong>${{title}}</strong><br/><small>${{artist}} • ${{date}}</small><br/><small>${{medium}}</small>`;
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
        st.components.v1.html(html, height=720, scrolling=True)

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
            if m and is_greek_roman_meta_medium(m):
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
    st.header("Mythic Lineages — Museum-style Explanations")
    st.write("Explanations appear first for quick reading; the interactive network is provided below as a supplementary view.")

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

    def relation_explanation_text(a,b,rel):
        if rel == "parent":
            return f"🔹 {a} → {b}\n\n{a} is a progenitor figure whose actions and attributes inform the domains, responsibilities, or mythic roles later embodied by {b}."
        if rel == "conflict":
            return f"🔹 {a} → {b}\n\nThe connection is adversarial: narratives between {a} and {b} often stage trials, moral tests, or dramatic confrontations."
        if rel == "influence":
            return f"🔹 {a} → {b}\n\nA narrative or symbolic influence: {a} shapes the legend, iconography, or cultural meaning surrounding {b}."
        if rel == "associate":
            return f"🔹 {a} → {b}\n\nAn associative relation: the figures appear in related spheres of mythic practice or share symbolic attributes."
        return f"🔹 {a} → {b}\n\nRelation: {rel}."

    for a,b,rel in RELS:
        st.markdown(relation_explanation_text(a,b,rel))

    st.markdown("---")
st.write("Interactive network (supplementary). Install `pyvis` and `networkx` to enable it.")

try:
    import networkx as nx
    from pyvis.network import Network
except Exception:
    st.info("pyvis/networkx not installed — interactive network not available.")
else:
    # Build the graph
    G = nx.Graph()
    for a, b, rel in RELS:
        G.add_node(a)
        G.add_node(b)
        G.add_edge(a, b, relation=rel)

    # Create PyVis network (must be INSIDE the else)
    nt = Network(
        height="600px",
        width="100%",
        bgcolor="#ffffff",
        font_color="black",
        notebook=False
    )

    # Build nodes
    for n in G.nodes():
        nt.add_node(n, label=n, title=n)

    # Build edges
    for u, v, data in G.edges(data=True):
        nt.add_edge(u, v, title=data.get("relation", ""))

    # SAFE rendering method
    try:
        html_str = nt.generate_html()
        st.components.v1.html(html_str, height=650, scrolling=True)
    except Exception as e:
        st.error(f"Failed to render interactive network: {e}")

# ---------- Myth Stories (rewritten) ----------
elif page == "Myth Stories":
    st.header("📘 Myth Stories — Museum-style 3-part output")
    st.write("Workflow: 1) Choose a character. 2) Search MET (medium filter). 3) Select one artwork (optional). 4) Generate three-part museum-style output: Character Overview / Myth Narrative / Artwork Commentary.")
    character = st.selectbox("Choose a character", MYTH_LIST, index=0)
    st.write("Local Character Overview (seed):")
    st.info(MYTH_DB.get(character, "No local seed stored — the app can auto-generate a short seed."))

    # Search MET for character (medium filter)
    if st.button("Search MET for this character (medium-filtered)"):
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
        st.info(f"Found {len(all_ids)} candidate IDs. Fetching metadata and applying medium filter...")

        filtered = []
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m and is_greek_roman_meta_medium(m):
                thumb = m.get("primaryImageSmall") or m.get("primaryImage") or (m.get("additionalImages") or [None])[0]
                filtered.append({"id": oid, "meta": m, "thumb": thumb})
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.005)
        p2.empty()
        st.session_state["myth_search_results"] = filtered
        st.success(f"{len(filtered)} likely myth-related works found.")

    results = st.session_state.get("myth_search_results", [])
    selected_meta = st.session_state.get("myth_selected_meta")
    meta = selected_meta if selected_meta else None

    if results:
        st.markdown("### Results (click a Select button under a thumbnail to choose artwork for commentary)")
        cols = st.columns(3)
        for idx, rec in enumerate(results):
            with cols[idx % 3]:
                thumb = rec.get("thumb")
                mid = rec.get("id")
                title = rec["meta"].get("title", "Untitled")
                artist = rec["meta"].get("artistDisplayName", "Unknown")
                date = rec["meta"].get("objectDate", "Unknown")
                medium = rec["meta"].get("medium", "")
                if thumb:
                    st.image(thumb, caption=f"{title} ({mid})", use_column_width=True)
                st.write(f"**{title}**")
                st.write(f"{artist} • {date} • {medium}")
                st.write(f"[Open on MET]({rec['meta'].get('objectURL')})")
                if st.button(f"Select {mid}", key=f"select_{mid}"):
                    st.session_state["myth_selected_meta"] = rec["meta"]
                    st.success(f"Selected artwork {mid} for commentary.")
    else:
        st.info("No search results. Click 'Search MET for this character (medium-filtered)' to find artworks.")

    if "myth_selected_meta" in st.session_state:
        meta = st.session_state.get("myth_selected_meta")
        st.markdown("---")
        st.markdown(f"### Selected artwork — {meta.get('title') or 'Untitled'}")
        img_url = meta.get("primaryImage") or meta.get("primaryImageSmall") or ""
        if img_url:
            st.image(img_url, width=360)
        st.write(f"**Title:** {meta.get('title') or 'Untitled'}")
        st.write(f"**Artist:** {meta.get('artistDisplayName') or 'Unknown'}")
        st.write(f"**Date:** {meta.get('objectDate') or 'Unknown'}")
        st.write(f"**Medium:** {meta.get('medium') or 'Unknown'}")
        st.write(f"**Dimensions:** {meta.get('dimensions') or 'Unknown'}")
        st.write(f"[Open on MET]({meta.get('objectURL')})")

    st.markdown("---")
    st.subheader("Generate (AI) — Character Overview / Myth Narrative / Artwork Commentary")
    st.write("If no local seed exists, you may allow the app to auto-generate a brief Character Overview (seed) using OpenAI.")

    auto_seed = st.checkbox("Auto-generate Character Overview if missing", value=True)
    if st.button("Generate 3-part museum text (AI)"):
        # Prepare seed
        seed = MYTH_DB.get(character, "")
        if not seed and auto_seed:
            if "OPENAI_API_KEY" in st.session_state and st.session_state["OPENAI_API_KEY"]:
                try:
                    from openai import OpenAI
                    oa = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
                    p_seed = f"Write a 1-2 sentence museum-style character overview for '{character}', concise and suitable for exhibition labels."
                    resp_seed = oa.responses.create(model="gpt-4.1-mini", input=p_seed)
                    seed = (resp_seed.output_text or "").strip()
                except Exception as e:
                    st.warning(f"Auto-seed generation failed: {e}")
                    seed = ""
            else:
                st.info("No OpenAI key saved — cannot auto-generate seed. Proceeding with empty seed.")
                seed = ""

        if not seed and not meta:
            st.warning("No character seed and no artwork selected. Please choose artwork or allow seed auto-generation.")
        else:
            safe_seed = (seed or "").replace("{", "{{").replace("}", "}}")
            title = meta.get("title", "Untitled") if meta else None
            artist = meta.get("artistDisplayName", "Unknown") if meta else None
            date = meta.get("objectDate", "Unknown") if meta else None
            medium = meta.get("medium", "Unknown") if meta else None

            if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
                st.warning("Please save your OpenAI API key in the sidebar to enable generation.")
            else:
                try:
                    from openai import OpenAI
                except Exception:
                    st.error("OpenAI SDK not installed. Add 'openai>=1.0.0' to requirements.txt and redeploy.")
                    st.stop()

                client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])

                # Build prompt: request three labelled sections
                if meta:
                    prompt = f"""
You are an art historian and museum curator. Produce three clearly labelled sections for exhibition use:

1) Character Overview (1-2 sentences): a concise museum label about {character}, based on this seed: {safe_seed}

2) Myth Narrative (short audio-guide tone, 3-6 sentences): an emotive, concise retelling of the key myth(s) associated with {character}.

3) Artwork Commentary (3-6 sentences): analyze the selected artwork titled "{title}", by {artist}, dated {date}. Discuss composition, lighting, pose, symbolism, and how the image relates to the myth. Keep language accessible to students and exhibition visitors.

Return the three sections separated by a line with '---' and label each section.
"""
                else:
                    prompt = f"""
You are an art historian and museum curator. Produce two labelled sections for exhibition use:

1) Character Overview (1-2 sentences): a concise museum label about {character}, based on this seed: {safe_seed}

2) Myth Narrative (short audio-guide tone, 3-6 sentences): an emotive, concise retelling of the key myth(s) associated with {character}.

Return the sections separated by '---' and label each section.
"""

                with st.spinner("Generating..."):
                    try:
                        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
                        out_text = resp.output_text or "[No output]"
                    except Exception as e:
                        out_text = f"[Generation failed: {e}]"

                # Parse and display
                if '---' in out_text:
                    parts = [p.strip() for p in out_text.split('---') if p.strip()]
                    for p in parts:
                        if p.lower().startswith("1") or p.lower().startswith("character"):
                            st.markdown("### 🧾 Character Overview")
                            st.write(p)
                        elif p.lower().startswith("2") or p.lower().startswith("myth"):
                            st.markdown("### 📖 Myth Narrative")
                            st.write(p)
                        elif p.lower().startswith("3") or p.lower().startswith("artwork"):
                            st.markdown("### 🖼 Artwork Commentary")
                            st.write(p)
                        else:
                            st.write(p)
                else:
                    st.markdown("### Generated Text")
                    st.write(out_text)

                st.download_button("Download generated text (txt)", data=out_text, file_name=f"{character}_museum_text.txt", mime="text/plain")

# ---------- Style Transfer ----------
elif page == "Style Transfer":
    st.header("🎨 Style Transfer — Blend Content + Style Image")
    st.write("Upload content and style images; provide OpenAI API key in sidebar to generate stylized image.")
    if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
        st.warning("Please save your OpenAI API key in the sidebar to use this feature.")
    else:
        try:
            from openai import OpenAI
        except Exception:
            st.error("OpenAI SDK missing. Add 'openai>=1.0.0' to requirements.txt.")
            st.stop()
        import base64
        client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
        content_img = st.file_uploader("Content image", type=["png","jpg","jpeg"], key="style_content")
        style_img = st.file_uploader("Style image", type=["png","jpg","jpeg"], key="style_style")
        if content_img:
            st.image(content_img, caption="Content", width=300)
        if style_img:
            st.image(style_img, caption="Style", width=300)
        if content_img and style_img and st.button("Generate Stylized Image"):
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
                        image=[{"data": content_b64}, {"data": style_b64}]
                    )
                    img_b64 = result.data[0].b64_json
                    final = base64.b64decode(img_b64)
                    st.image(final, caption="Stylized result", use_column_width=True)
                    st.download_button("Download stylized image", data=final, file_name="style_transfer.png", mime="image/png")
                except Exception as e:
                    st.error(f"Image generation failed: {e}")

# ---------- AI Interpretation ----------
elif page == "AI Interpretation":
    st.header("AI Interpretation — Ask about dataset")
    question = st.text_input("Ask AI about the dataset or network:")
    if question:
        if "OPENAI_API_KEY" not in st.session_state or not st.session_state["OPENAI_API_KEY"]:
            st.warning("Please save your OpenAI API key in the sidebar.")
        else:
            try:
                from openai import OpenAI
            except Exception:
                st.error("OpenAI SDK missing. Add 'openai>=1.0.0' to requirements.txt.")
                st.stop()
            client = OpenAI(api_key=st.session_state["OPENAI_API_KEY"])
            dataset = st.session_state.get("analysis_dataset") or []
            sample = json.dumps([{"objectID": m.get("objectID"), "title": m.get("title"), "date": m.get("objectDate")} for m in dataset[:10]], ensure_ascii=False)
            prompt = f"You are an art historian and data analyst. Dataset sample:\n{sample}\nQuestion: {question}"
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
    st.write("Created by Pengwei He — Mythic Art Explorer (Final Project).")
    st.write("This version uses medium-level MET filtering and a 3-part Myth Stories generator (Character Overview / Myth Narrative / Artwork Commentary).")

# ---------- End ----------
