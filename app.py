# final_app.py
"""
Mythic Art Explorer — All-in-One (integrated)
Features:
 - Multi-museum search (MET, CMA, AIC)
 - Saved selection pool
 - Stories: 3-part museum texts (Overview / Narrative / Artwork Commentary) (AI if key provided)
 - Character Profiles & Relationships
 - Personality Test
 - AI Creation (Myth Scene Generator + Artwork Transformer) — uses OpenAI Images API when key present
Notes:
 - Optional AI: paste OpenAI API key in sidebar to enable AI features
 - Keep dependencies minimal; see suggested requirements.txt
"""

import streamlit as st
import requests
import time
import json
import collections
from typing import List, Dict, Optional, Any

# optional image handling
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# optional network graph
try:
    import networkx as nx
    from pyvis.network import Network
    PYVIS_AVAILABLE = True
except Exception:
    PYVIS_AVAILABLE = False

# Page config
st.set_page_config(page_title="Mythic Art Explorer — Final", layout="wide")

# -----------------------------
# Basic data: characters & relations
# -----------------------------
CHARACTERS = {
    "Zeus": {
        "en": "Zeus — King of the Olympian gods. Symbolic attributes: thunderbolt, eagle, scepter."
    },
    "Hera": {"en": "Hera — Queen of the gods; marriage, family, regal iconography (peacock)."},
    "Athena": {"en": "Athena — Goddess of wisdom, craft, and strategic warfare; owl, helmet, aegis."},
    "Apollo": {"en": "Apollo — God of music, prophecy, and the sun; lyre, laurel, youthful figure."},
    "Artemis": {"en": "Artemis — Goddess of the hunt and moon; bow, stag, virgin protector."},
    "Aphrodite": {"en": "Aphrodite — Goddess of love and beauty; sensual and marine imagery."},
    "Hermes": {"en": "Hermes — Messenger god; winged sandals, caduceus."},
    "Dionysus": {"en": "Dionysus — God of wine, ritual, and theatricality; vine imagery."},
    "Perseus": {"en": "Perseus — Hero who slew Medusa; winged sandals, severed head motif."},
    "Medusa": {"en": "Medusa — Gorgon whose gaze petrifies; complex readings across time."},
    "Theseus": {"en": "Theseus — Hero who defeated the Minotaur; labyrinth motif."},
    "Heracles": {"en": "Heracles — Hero of the Twelve Labors; lion-skin, club."},
    "Orpheus": {"en": "Orpheus — Legendary musician; journey to the underworld for Eurydice."},
}

RELATIONS = [
    ("Chaos", "Gaia", "parent"),
    ("Gaia", "Uranus", "parent"),
    ("Uranus", "Cronus", "parent"),
    ("Cronus", "Zeus", "parent"),
    ("Cronus", "Hera", "parent"),
    ("Cronus", "Poseidon", "parent"),
    ("Cronus", "Hades", "parent"),
    ("Zeus", "Athena", "parent"),
    ("Zeus", "Apollo", "parent"),
    ("Zeus", "Artemis", "parent"),
    ("Zeus", "Ares", "parent"),
    ("Zeus", "Hermes", "parent"),
    ("Zeus", "Dionysus", "parent"),
    ("Perseus", "Theseus", "influence"),
    ("Medusa", "Perseus", "conflict"),
    ("Minotaur", "Theseus", "conflict"),
    ("Cyclops", "Poseidon", "associate"),
]

# -----------------------------
# Museum APIs (MET, CMA, AIC)
# -----------------------------
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJ = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

CMA_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks/?q={}"
AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search?q={}&limit=80"
AIC_OBJ = "https://api.artic.edu/api/v1/artworks/{}"

@st.cache_data(ttl=60*60*24)
def met_search_ids(q: str, max_results: int = 200) -> List[int]:
    try:
        r = requests.get(MET_SEARCH, params={"q": q, "hasImages": True}, timeout=10)
        r.raise_for_status()
        ids = r.json().get("objectIDs") or []
        return ids[:max_results]
    except Exception:
        return []

@st.cache_data(ttl=60*60*24)
def met_get_object(object_id: int) -> Dict:
    try:
        r = requests.get(MET_OBJ.format(object_id), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

@st.cache_data(ttl=60*60*24)
def cma_search(q: str, limit: int = 200) -> List[Dict]:
    try:
        r = requests.get(CMA_SEARCH.format(q), timeout=10)
        r.raise_for_status()
        js = r.json()
        return js.get("data", [])[:limit]
    except Exception:
        return []

@st.cache_data(ttl=60*60*24)
def aic_search(q: str, limit: int = 60) -> List[Dict]:
    out = []
    try:
        r = requests.get(AIC_SEARCH.format(q), timeout=10)
        r.raise_for_status()
        js = r.json()
        data = js.get("data", [])[:limit]
        # fetch details for a subset to get image_id
        for d in data[:min(len(data), 40)]:
            rid = d.get("id")
            try:
                rd = requests.get(AIC_OBJ.format(rid), timeout=8).json()
                out.append(rd.get("data", d))
            except Exception:
                out.append(d)
        return out
    except Exception:
        return []

# -----------------------------
# Thumbnail & safety helpers
# -----------------------------
def is_valid_image_url(url: Optional[str]) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u: return False
    # avoid formats that Streamlit may choke on
    if any(u.endswith(ext) for ext in [".gif", ".svg", ".pdf"]):
        return False
    if u.startswith("http://") or u.startswith("https://"):
        return True
    return False

def fallback_logo(source: str) -> str:
    logos = {
        "MET": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Metropolitan_Museum_of_Art_logo.svg",
        "CMA": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Cleveland_Museum_of_Art_logo.svg/512px-Cleveland_Museum_of_Art_logo.svg.png",
        "AIC": "https://upload.wikimedia.org/wikipedia/commons/9/94/Art_Institute_of_Chicago_logo.svg",
        "DEFAULT": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Metropolitan_Museum_of_Art_logo.svg"
    }
    return logos.get(source, logos["DEFAULT"])

def safe_thumb_from_meta(meta: Dict, source: str) -> Optional[str]:
    if not isinstance(meta, dict):
        return None
    # MET fields
    if meta.get("primaryImageSmall") and is_valid_image_url(meta.get("primaryImageSmall")):
        return meta.get("primaryImageSmall")
    if meta.get("primaryImage") and is_valid_image_url(meta.get("primaryImage")):
        return meta.get("primaryImage")
    # AIC: construct IIIF url if image_id exists
    if meta.get("image_id"):
        url = f"https://www.artic.edu/iiif/2/{meta['image_id']}/full/400,/0/default.jpg"
        if is_valid_image_url(url):
            return url
    # CMA: images.web
    if meta.get("images") and isinstance(meta.get("images"), dict):
        img = meta["images"].get("web")
        if is_valid_image_url(img):
            return img
    return fallback_logo(source)

# -----------------------------
# AI helpers (OpenAI dynamic client)
# -----------------------------
def openai_client_from_key(key: str):
    """
    Return a client object (modern OpenAI client or fallback to old openai library).
    If not available, return None.
    """
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        try:
            import openai as o
            o.api_key = key
            return o
        except Exception:
            return None

def ai_generate_3part(character: str, seed: str, artwork_meta: Optional[Dict], key: Optional[str]) -> str:
    if key:
        client = openai_client_from_key(key)
        if client:
            title = artwork_meta.get("title") if artwork_meta else "Untitled"
            date = artwork_meta.get("objectDate") or artwork_meta.get("date") or ""
            prompt = (
                f"You are an art historian. Produce three labeled sections for exhibition use:\n\n"
                f"1) Character Overview (2 sentences): about {character}. Seed: {seed}\n\n"
                f"2) Myth Narrative (3-6 sentences): evocative museum audio-guide tone.\n\n"
                f"3) Artwork Commentary (3-6 sentences): analyze the artwork titled '{title}', dated {date}. "
                "Discuss composition, lighting, pose, symbolism, and relation to the myth. Keep language accessible.\n\n"
                "Return sections separated by '---'."
            )
            try:
                if hasattr(client, "responses"):
                    r = client.responses.create(model="gpt-4.1-mini", input=prompt)
                    return r.output_text or "[AI returned no text]"
                else:
                    resp = client.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}])
                    return resp.choices[0].message["content"]
            except Exception as e:
                return f"[AI generation failed: {e}]"
    # local fallback
    overview = seed or CHARACTERS.get(character, {}).get("en", character)
    narrative = f"{character} is a central figure of myth whose stories have been retold across centuries, offering lenses on power and fate."
    if artwork_meta:
        title = artwork_meta.get("title", "Untitled")
        commentary = f"Selected work: {title}. Look for emblematic objects and posture that link image to {character}."
    else:
        commentary = "No artwork selected. Choose a saved item to produce specific commentary."
    return f"Character Overview:\n{overview}\n\n---\n\nMyth Narrative:\n{narrative}\n\n---\n\nArtwork Commentary:\n{commentary}"

def ai_generate_image(prompt: str, key: Optional[str], size: str = "1024x1024") -> Dict:
    """
    Call OpenAI images API via modern or legacy client.
    Returns dict: {'b64_json':..., 'error': None} or {'b64_json': None, 'error': str}
    """
    if not key:
        return {"b64_json": None, "error": "No API key provided"}
    client = openai_client_from_key(key)
    if not client:
        return {"b64_json": None, "error": "OpenAI client not available in environment"}
    try:
        # modern client usage
        if hasattr(client, "images") and hasattr(client, "responses"):
            # some modern clients expose .images or .responses differently; try images.generate if available
            try:
                res = client.images.generate(model="gpt-image-1", prompt=prompt, size=size, n=1)
                b64 = res.data[0].b64_json
                return {"b64_json": b64, "error": None}
            except Exception:
                # fallback to responses->image? try client.responses.create with an image generation instruction (not standard)
                pass
        # fallback to older openai images.create
        try:
            import openai as o
            img = o.Image.create(model="gpt-image-1", prompt=prompt, size=size, n=1)
            b64 = img['data'][0]['b64_json']
            return {"b64_json": b64, "error": None}
        except Exception as e:
            return {"b64_json": None, "error": str(e)}
    except Exception as e:
        return {"b64_json": None, "error": str(e)}

# -----------------------------
# UI: Sidebar + state
# -----------------------------
st.sidebar.title("Mythic Art Explorer")
st.sidebar.markdown("Optional: paste your OpenAI API key to enable AI features (session only).")
openai_key = st.sidebar.text_input("OpenAI API key (optional)", type="password")
if openai_key:
    st.session_state["OPENAI_KEY"] = openai_key

page = st.sidebar.selectbox("Page", [
    "Home",
    "Explorer",
    "Saved Items",
    "Stories",
    "Visualization",
    "Character Profiles",
    "Character Relationships",
    "Personality Test",
    "AI Creation",
    "About"
])

if "saved_items" not in st.session_state:
    st.session_state["saved_items"] = []

# -----------------------------
# HOME
# -----------------------------
if page == "Home":
    st.title("🏛 Mythic Art Explorer — Final")
    st.markdown("Multi-museum search & AI-assisted museum texts.")
    st.markdown("**APIs used:** MET (Metropolitan Museum of Art), Cleveland Museum of Art (Open Access), Art Institute of Chicago (AIC).")
    st.markdown("---")
    st.write("Quick tips:")
    st.write("- Explorer: search across MET / CMA / AIC.")
    st.write("- Save items to your Selection Pool (Saved Items).")
    st.write("- Stories: pick saved item + character → generate 3-part museum text (AI if key provided).")
    st.write("- AI Creation: Myth Scene Generator & Artwork Transformer (requires OpenAI key).")

# -----------------------------
# EXPLORER
# -----------------------------
elif page == "Explorer":
    st.header("Explorer — Multi-museum search")
    query = st.text_input("Search term (e.g., 'Athena', 'Medusa')", "Zeus")
    max_source = st.slider("Max items per source", 10, 200, 60, step=10)
    if st.button("Search MET / CMA / AIC"):
        st.info("Searching... please wait.")
        results = []
        # MET
        met_ids = met_search_ids(query, max_results=max_source)
        for oid in met_ids[:max_source]:
            m = met_get_object(oid)
            thumb = safe_thumb_from_meta(m, "MET")
            results.append({"source": "MET", "id": oid, "title": m.get("title", "Untitled"), "meta": m, "thumb": thumb})
        # CMA
        cma_hits = cma_search(query, limit=max_source)
        for c in cma_hits[:max_source]:
            thumb = safe_thumb_from_meta(c, "CMA")
            results.append({"source": "CMA", "id": c.get("id"), "title": c.get("title", "Untitled"), "meta": c, "thumb": thumb})
        # AIC
        aic_hits = aic_search(query, limit=max(20, max_source//2))
        for a in aic_hits[:max_source]:
            thumb = safe_thumb_from_meta(a, "AIC")
            results.append({"source": "AIC", "id": a.get("id"), "title": a.get("title", "Untitled"), "meta": a, "thumb": thumb})
        st.session_state["explorer_results"] = results
        st.success(f"Found {len(results)} items (mixed sources).")

    results = st.session_state.get("explorer_results", [])
    if not results:
        st.info("No results yet. Run a search.")
    else:
        st.write(f"Showing {len(results)} results.")
        cols = st.columns(3)
        for i, rec in enumerate(results):
            with cols[i % 3]:
                thumb = rec.get("thumb") or fallback_logo(rec.get("source"))
                try:
                    st.image(thumb, use_column_width=True)
                except Exception:
                    st.image(fallback_logo(rec.get("source")), use_column_width=True)
                st.write(f"**{rec.get('title')}**")
                st.caption(f"{rec.get('source')} — id: {rec.get('id')}")
                if st.button(f"Save {rec.get('source')}:{rec.get('id')}", key=f"save_{rec.get('source')}_{rec.get('id')}"):
                    st.session_state["saved_items"].append(rec)
                    st.success("Saved to selection pool.")
                if st.button(f"View {i}", key=f"view_{i}"):
                    st.session_state["detail_item"] = rec

    if "detail_item" in st.session_state:
        st.markdown("---")
        item = st.session_state["detail_item"]
        st.subheader(item.get("title", "Untitled"))
        st.caption(f"{item.get('source')} — id: {item.get('id')}")
        try:
            st.image(item.get("thumb") or fallback_logo(item.get("source")), width=420)
        except Exception:
            st.image(fallback_logo(item.get("source")), width=420)
        meta = item.get("meta", {})
        st.write("**Metadata (selected fields)**")
        if meta:
            st.write(f"- Date: {meta.get('objectDate') or meta.get('date') or meta.get('date_display')}")
            st.write(f"- Medium: {meta.get('medium') or meta.get('technique') or meta.get('material')}")
            st.write(f"- Culture: {meta.get('culture') or meta.get('cultureName')}")
            if meta.get("objectURL"):
                st.write(f"[Open on museum page]({meta.get('objectURL')})")
        st.markdown("---")

# -----------------------------
# SAVED ITEMS
# -----------------------------
elif page == "Saved Items":
    st.header("Saved Items — Your Selection Pool")
    saved = st.session_state.get("saved_items", [])
    st.write(f"{len(saved)} items in your pool.")
    if saved:
        cols = st.columns(3)
        for i, rec in enumerate(saved):
            with cols[i % 3]:
                try:
                    st.image(rec.get("thumb") or fallback_logo(rec.get("source")), use_column_width=True)
                except Exception:
                    st.image(fallback_logo(rec.get("source")), use_column_width=True)
                st.write(f"**{rec.get('title','Untitled')}**")
                st.caption(f"{rec.get('source')} / id: {rec.get('id')}")
                if st.button(f"Remove {i}", key=f"rm_{i}"):
                    st.session_state["saved_items"].pop(i)
                    st.experimental_rerun()
        st.markdown("---")
        st.write("Use saved items as input for Stories or AI Creation.")
    else:
        st.info("Selection pool empty. Add items from Explorer.")

# -----------------------------
# STORIES
# -----------------------------
elif page == "Stories":
    st.header("Stories — 3-part museum text (Overview / Narrative / Artwork Commentary)")
    saved = st.session_state.get("saved_items", [])
    character = st.selectbox("Choose character", list(CHARACTERS.keys()))
    choice_idx = st.selectbox("Pick a saved item index", list(range(len(saved))) if saved else ["None"])
    seed = CHARACTERS.get(character, {}).get("en", "")
    if choice_idx != "None" and saved:
        sel = saved[int(choice_idx)]
        st.subheader("Selected artwork")
        try:
            st.image(sel.get("thumb") or fallback_logo(sel.get("source")), width=360)
        except Exception:
            st.image(fallback_logo(sel.get("source")), width=360)
        st.write(f"**{sel.get('title')}** — {sel.get('source')}")
        if st.button("Generate 3-part text"):
            key = st.session_state.get("OPENAI_KEY") or None
            out = ai_generate_3part(character, seed, sel.get("meta"), key)
            st.markdown("### English (generated)")
            st.text_area("Output (EN)", out, height=320)
            # try to auto-translate if key provided (optional)
            if key:
                client = openai_client_from_key(key)
                if client:
                    try:
                        trans_prompt = f"Translate into concise Chinese suitable for a museum label. Keep sections and labels:\n\n{out}"
                        if hasattr(client, "responses"):
                            r = client.responses.create(model="gpt-4.1-mini", input=trans_prompt)
                            cn_text = r.output_text or ""
                        else:
                            resp = client.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":trans_prompt}])
                            cn_text = resp.choices[0].message["content"]
                    except Exception as e:
                        cn_text = f"[Translation failed: {e}]"
                else:
                    cn_text = "[Translation not available: OpenAI client not available]"
            else:
                cn_text = "[Translation not generated: no OpenAI key]"
            st.markdown("### Chinese (auto-translate / optional)")
            st.text_area("Chinese", cn_text, height=320)
            st.download_button("Download story (txt)", data="EN:\n" + out + "\n\nCN:\n" + cn_text, file_name=f"{character}_story.txt")
    else:
        st.info("No saved item selected. Save an artwork first.")

# -----------------------------
# VISUALIZATION
# -----------------------------
elif page == "Visualization":
    st.header("Visualization — MET dataset sample analytics")
    char = st.selectbox("Choose figure", list(CHARACTERS.keys()))
    if st.button("Fetch sample MET dataset"):
        ids = met_search_ids(char, max_results=300)
        metas = []
        p = st.progress(0)
        for i, oid in enumerate(ids[:200]):
            m = met_get_object(oid)
            if m:
                metas.append(m)
            if i % 20 == 0:
                p.progress(min(100, int((i+1)/max(1, len(ids))*100)))
            time.sleep(0.005)
        st.session_state["viz_dataset"] = metas
        st.success(f"Fetched {len(metas)} records.")
    data = st.session_state.get("viz_dataset", [])
    if data:
        import plotly.express as px
        years = [m.get("objectBeginDate") for m in data if isinstance(m.get("objectBeginDate"), int)]
        mediums = [(m.get("medium") or "Unknown") for m in data]
        if years:
            st.plotly_chart(px.histogram(x=years, nbins=30, title="Year distribution"), use_container_width=True)
        if mediums:
            cnt = collections.Counter(mediums).most_common(12)
            fig = px.bar(x=[c for _, c in cnt], y=[k for k, _ in cnt], orientation="h", labels={"x":"Count","y":"Medium"}, title="Top mediums")
            st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# CHARACTER PROFILES
# -----------------------------
elif page == "Character Profiles":
    st.header("Character Profiles — Museum-style bios")
    character = st.selectbox("Choose character", list(CHARACTERS.keys()))
    st.markdown("**English (museum label)**")
    st.write(CHARACTERS.get(character, {}).get("en"))
    if st.checkbox("Show expanded curator notes"):
        notes = f"{character} appears across many media. Curatorial notes should highlight recurring motifs and interpretive questions."
        st.write(notes)

# -----------------------------
# CHARACTER RELATIONSHIPS
# -----------------------------
elif page == "Character Relationships":
    st.header("Character Relationships — Explanations")
    st.write("Panel summary: This sequence maps mythic genealogies and selected thematic relations.")
    st.markdown("---")
    for a, b, rel in RELATIONS:
        if rel == "parent":
            st.markdown(f"🔹 **{a} → {b}** — {a} is a progenitor whose myths shape {b}.")
        elif rel == "conflict":
            st.markdown(f"🔹 **{a} → {b}** — Conflictual relation: stories stage trials and confrontations.")
        elif rel == "influence":
            st.markdown(f"🔹 **{a} → {b}** — {a} influences the legend and iconography of {b}.")
        else:
            st.markdown(f"🔹 **{a} → {b}** — {rel}")
    st.markdown("---")
    if PYVIS_AVAILABLE:
        try:
            G = nx.Graph()
            for a, b, rel in RELATIONS:
                G.add_node(a); G.add_node(b); G.add_edge(a, b, relation=rel)
            nt = Network(height="600px", width="100%", notebook=False)
            for n in G.nodes():
                nt.add_node(n, label=n, title=n)
            for u, v, data in G.edges(data=True):
                nt.add_edge(u, v, title=data.get("relation", ""))
            html = nt.generate_html()
            st.components.v1.html(html, height=620, scrolling=True)
        except Exception as e:
            st.error(f"Interactive network failed: {e}")
    else:
        st.info("Install pyvis & networkx to enable interactive network.")

# -----------------------------
# PERSONALITY TEST
# -----------------------------
elif page == "Personality Test":
    st.header("Personality Test — Which mythic figure are you?")
    q1 = st.radio("In a group you usually:", ["Lead", "Support", "Create", "Question"])
    q2 = st.radio("You prefer:", ["Order", "Wisdom", "Passion", "Adventure"])
    q3 = st.slider("Tradition vs Change", 0, 10, 5)
    q4 = st.selectbox("Pick a symbol", ["Thunderbolt", "Owl", "Lyre", "Bow", "Bull"])
    if st.button("Reveal match"):
        score = collections.defaultdict(int)
        if q1 == "Lead": score["Zeus"] += 2
        if q1 == "Support": score["Athena"] += 1
        if q1 == "Create": score["Apollo"] += 2
        if q1 == "Question": score["Athena"] += 2
        if q2 == "Order": score["Zeus"] += 1
        if q2 == "Wisdom": score["Athena"] += 2
        if q2 == "Passion": score["Dionysus"] += 2
        if q2 == "Adventure": score["Perseus"] += 2
        if q3 <= 3: score["Orpheus"] += 1
        if q3 >= 7: score["Zeus"] += 1
        if q4 == "Thunderbolt": score["Zeus"] += 2
        if q4 == "Owl": score["Athena"] += 2
        if q4 == "Lyre": score["Apollo"] += 2
        if q4 == "Bow": score["Artemis"] += 2
        if q4 == "Bull": score["Poseidon"] += 1
        match = max(score, key=score.get) if score else "Zeus"
        st.success(f"Your mythic match: {match}")
        st.write(CHARACTERS.get(match, {}).get("en", ""))

# -----------------------------
# AI CREATION (NEW): Myth Scene Generator + Artwork Transformer
# -----------------------------
elif page == "AI Creation":
    st.header("AI Creation — Myth Scene Generator & Artwork Transformer")
    st.markdown("**Note:** These features require an OpenAI API key entered in the sidebar to actually generate images. Without a key the app will show prompts / previews text only.")

    # 1) Myth Scene Generator
    st.subheader("1) Myth Scene Generator")
    ms_character = st.text_input("Character / Scene prompt (e.g., 'Zeus vs Typhon in stormy sky, Hellenistic marble style')", "Zeus vs Typhon, dramatic storm, Greek vase style")
    ms_style = st.selectbox("Art style", ["Greek vase style", "Hellenistic marble style", "Renaissance myth painting", "Oil painting", "Woodcut"])
    ms_size = st.selectbox("Image size", ["512x512", "1024x1024"], index=1)
    if st.button("Generate myth scene image"):
        key = st.session_state.get("OPENAI_KEY") or None
        prompt = f"{ms_character}. Style: {ms_style}. Make composition cinematic with clear focal center, strong lighting, and classical motifs."
        if not key:
            st.warning("No OpenAI key provided. Insert your key in the sidebar to generate images.")
            st.info("Prompt preview:")
            st.code(prompt)
        else:
            with st.spinner("Generating image..."):
                res = ai_generate_image(prompt, key, size=ms_size)
                if res.get("error"):
                    st.error(f"Image generation failed: {res.get('error')}")
                    st.info("Prompt used:")
                    st.code(prompt)
                else:
                    import base64, io
                    b64 = res.get("b64_json")
                    try:
                        img_bytes = base64.b64decode(b64)
                        st.image(img_bytes, use_column_width=True)
                        st.download_button("Download image", data=img_bytes, file_name="myth_scene.png", mime="image/png")
                    except Exception as e:
                        st.error(f"Failed to render image: {e}")

    st.markdown("---")

    # 2) Artwork Transformer (style transfer-like)
    st.subheader("2) Artwork Transformer — Upload + Transform")
    st.write("Upload a content image and choose a target classical style to transform it into (AI).")
    content = st.file_uploader("Content image (your photo or artwork)", type=["png", "jpg", "jpeg"], key="transform_content")
    transform_style = st.selectbox("Target style", ["Greek vase pattern", "Roman mosaic", "Hellenistic sculpture", "Renaissance oil painting", "AIC oil painting style"])
    t_size = st.selectbox("Output size", ["512x512", "1024x1024"], index=0)
    if content:
        try:
            if PIL_AVAILABLE:
                img = Image.open(content)
                st.image(img, caption="Content image", use_column_width=True)
            else:
                st.write("Pillow not installed — preview unavailable.")
        except Exception:
            st.write("Could not preview uploaded image.")
    if content and st.button("Generate transformed image"):
        key = st.session_state.get("OPENAI_KEY") or None
        if not key:
            st.warning("No OpenAI key provided.")
        else:
            # Read content bytes as base64 and instruct image model to transform style.
            import base64
            content_bytes = content.read()
            encoded = base64.b64encode(content_bytes).decode()
            # Some image APIs accept image inputs; here we craft a prompt describing desired transformation
            prompt = f"Transform the uploaded image into {transform_style}. Preserve main subject but apply {transform_style} textures, palette, and motifs."
            with st.spinner("Generating transformed image..."):
                res = ai_generate_image(prompt + " Use the uploaded image as content reference.", key, size=t_size)
                if res.get("error"):
                    st.error(f"Image generation failed: {res.get('error')}")
                    st.info("Prompt used:")
                    st.code(prompt)
                else:
                    import base64
                    try:
                        img_bytes = base64.b64decode(res.get("b64_json"))
                        st.image(img_bytes, use_column_width=True)
                        st.download_button("Download transformed image", data=img_bytes, file_name="transformed.png", mime="image/png")
                    except Exception as e:
                        st.error(f"Failed to render transformed image: {e}")

# -----------------------------
# ABOUT
# -----------------------------
elif page == "About":
    st.header("About & Notes")
    st.markdown("- APIs used: MET (Metropolitan Museum of Art), Cleveland Museum of Art (Open Access), Art Institute of Chicago (AIC).")
    st.markdown("- AI: optional OpenAI integration (paste key in sidebar). Image generation uses OpenAI Images API if key provided.")
    st.markdown("- Optional: install pyvis & networkx to enable interactive relationship network.")
    st.markdown("## Deployment / requirements")
    st.write("Suggested requirements (example):")
    st.code("""
streamlit
requests
pillow
plotly
openai  # optional, for AI features
pyvis   # optional
networkx  # optional
""")
    st.write("If you deploy to Streamlit Cloud, add your requirements.txt and (optionally) set OPENAI_API_KEY as a secret for automated runs.")

# end of file
