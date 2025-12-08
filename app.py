# final_app.py
"""
Mythic Art Explorer — All-in-One (integrated)
Features added on top of existing museum explorer:
 - Character Profiles (detailed, museum-style, EN/中文)
 - Character Relationships (museum-style explanations + optional network)
 - Personality Test (mythic match)
 - Myth Stories (3-part AI or local fallback: Overview / Narrative / Artwork Commentary)
 - AI Interpretation (image basic analysis + data QA fallback)
 - Safe thumbnail handling & multi-museum search (MET, CMA, AIC)
Notes:
 - Optional AI: Add OpenAI API key in sidebar to enable AI features.
 - Optional interactive network: install pyvis & networkx.
 - Requirements (suggested): streamlit, requests, pillow, plotly, openai (optional), pyvis (optional), networkx (optional)
"""

import streamlit as st
import requests
import json
import time
import collections
from typing import List, Dict, Any, Optional

# Optional imports handled safely
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# Try optional AI library (OpenAI). We will not import at top-level to avoid crash.
OPENAI_AVAILABLE = False
try:
    import openai  # just to detect; we will use dynamic client if available
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# Try pyvis/networkx for interactive network
PYVIS_AVAILABLE = False
try:
    import networkx as nx
    from pyvis.network import Network
    PYVIS_AVAILABLE = True
except Exception:
    PYVIS_AVAILABLE = False

# Streamlit page config
st.set_page_config(page_title="Mythic Art Explorer — Final", layout="wide")

# ---------------------------
# Basic configuration & DBs
# ---------------------------
# Detailed character profiles (museum-label style). EN and CN included.
CHARACTERS = {
    "Zeus": {
        "en": (
            "Zeus — King of the Olympian gods. "
            "He rules the sky and wields thunderbolts as instruments of divine power. "
            "In visual culture he is often depicted as a mature powerful figure, "
            "symbols include the thunderbolt, the eagle, and the scepter. "
            "As a central authority figure, depictions of Zeus in art signal sovereignty, law, and the mediation "
            "between mortals and gods."
        ),
        "cn": (
            "宙斯（Zeus）——奥林匹斯诸神之王。"
            "他掌管天空并以雷霆为权力象征。在视觉艺术中，宙斯常被描绘为成熟有力的男性形象，"
            "常见象征包括雷霆、鹰与权杖。宙斯的形象在艺术中常用于表达统治、法律以及神与人之间的中介。"
        )
    },
    "Hera": {
        "en": (
            "Hera — Queen of the gods, goddess of marriage, family and birth. "
            "She is often represented with regal iconography such as peacocks and throne-like postures. "
            "Hera's portrayal in art negotiates themes of feminine authority, fidelity, and ritual power."
        ),
        "cn": (
            "赫拉（Hera）——众神之后，婚姻、家族与生育的女神。"
            "在艺术中常以孔雀或王座式姿态出现，象征尊贵与权威。赫拉的形象涉及女性权威、婚姻忠诚与礼俗权力等议题。"
        )
    },
    "Athena": {
        "en": (
            "Athena — Goddess of wisdom, craftsmanship, and strategic warfare. "
            "Iconography includes the owl, helmet, aegis (shield/armor), and often a composed, armored stance. "
            "Visually Athena mediates intellect and martial skill; in museums she is a signifier of civic virtue and craft."
        ),
        "cn": (
            "雅典娜（Athena）——智慧、工艺与战略战争的女神。"
            "常见图像元素为猫头鹰、头盔、宙斯的神盾（或称Aegis）以及盔甲姿态。"
            "雅典娜在视觉上连接理性与军事技能，是市民美德与手工技艺的象征。"
        )
    },
    "Perseus": {
        "en": (
            "Perseus — Hero and slayer of Medusa. "
            "Depictions often show him holding Medusa's severed head, or in the act of rescue. "
            "Perseus embodies heroic cunning, divine assistance (gifts such as winged sandals), and the ambivalence of victory."
        ),
        "cn": (
            "珀尔修斯（Perseus）——英雄，斩杀美杜莎者。"
            "图像常见他持有美杜莎的首级，或进行救援的场景。"
            "珀尔修斯代表英雄机智、神祇赐予的帮助（例如带翅膀的凉鞋），以及胜利的复杂性。"
        )
    },
    "Medusa": {
        "en": (
            "Medusa — One of the Gorgons, whose gaze petrifies onlookers. "
            "In art she is rendered in many registers: monstrous, tragic, or even eroticized. "
            "Medusa's iconography invites readings about feminine menace, corporeal transformation, and protective apotropaic function."
        ),
        "cn": (
            "美杜莎（Medusa）——蛇发女妖之一，其凝视可使人石化。"
            "艺术中她有多种呈现：怪物式、悲剧式，甚至被性化。"
            "美杜莎的形象涉及女性威胁性、身体变形和辟邪功能等解读。"
        )
    },
    # add more default profiles — heroes, gods, monsters
    "Apollo": {"en": "Apollo — God of music, prophecy and sunlight.", "cn": "阿波罗（Apollo）——音乐、预言与太阳之神。"},
    "Artemis": {"en": "Artemis — Goddess of the hunt and the moon.", "cn": "阿耳忒弥斯（Artemis）——狩猎与月亮女神。"},
    "Ares": {"en": "Ares — God of war.", "cn": "战神阿瑞斯（Ares）。"},
    "Hermes": {"en": "Hermes — Messenger god and guide of travelers.", "cn": "赫尔墨斯（Hermes）——神的使者、旅行者的引导者。"},
    "Theseus": {"en": "Theseus — Hero who defeated the Minotaur.", "cn": "忒修斯（Theseus）——击败弥诺陶洛斯的英雄。"},
    "Heracles": {"en": "Heracles — Hero known for Twelve Labors.", "cn": "赫拉克勒斯（Heracles）——以十二项任务著称的英雄。"},
    "Orpheus": {"en": "Orpheus — Legendary musician who visited the underworld.", "cn": "俄耳甫斯（Orpheus）——传说中的音乐家，曾下冥界救妻。"},
    "Narcissus": {"en": "Narcissus — Youth who fell in love with his reflection.", "cn": "纳西瑟斯（Narcissus）——爱上自我倒影的青年。"},
    "Minotaur": {"en": "Minotaur — Half-man, half-bull, inhabitant of the Labyrinth.", "cn": "弥诺陶洛斯（Minotaur）——半人半牛，居住在迷宫中。"},
    "Cyclops": {"en": "Cyclops — One-eyed giant, often associated with smithing or pastoral scenes.", "cn": "独眼巨人（Cyclops）——常与冶炼或牧场场景相关联。"}
}

CHARACTER_LIST = list(CHARACTERS.keys())

# ---------------------------
# Museums API helpers
# ---------------------------
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
        return (r.json().get("objectIDs") or [])[:max_results]
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
def cma_search(q: str) -> List[Dict]:
    out = []
    try:
        r = requests.get(CMA_SEARCH.format(q), timeout=10)
        r.raise_for_status()
        js = r.json()
        return js.get("data", [])[:200]
    except Exception:
        return []

@st.cache_data(ttl=60*60*24)
def aic_search(q: str) -> List[Dict]:
    out = []
    try:
        r = requests.get(AIC_SEARCH.format(q), timeout=10)
        r.raise_for_status()
        js = r.json()
        data = js.get("data", [])[:120]
        # fetch details for each
        for d in data[:60]:
            try:
                rid = d.get("id")
                rd = requests.get(AIC_OBJ.format(rid), timeout=8).json()
                out.append(rd.get("data", d))
            except Exception:
                out.append(d)
        return out
    except Exception:
        return []

# -------------- thumbnail safety --------------
def is_valid_image_url(url: Optional[str]) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    lowered = url.lower()
    # disallow gifs/pdf/svg (streamlit may choke)
    if any(lowered.endswith(ext) for ext in [".gif", ".svg", ".pdf"]):
        return False
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return False
    return True

def fallback_logo(source: str) -> str:
    logos = {
        "MET": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Metropolitan_Museum_of_Art_logo.svg",
        "CMA": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Cleveland_Museum_of_Art_logo.svg/512px-Cleveland_Museum_of_Art_logo.svg.png",
        "AIC": "https://upload.wikimedia.org/wikipedia/commons/9/94/Art_Institute_of_Chicago_logo.svg",
        "DEFAULT": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Metropolitan_Museum_of_Art_logo.svg"
    }
    return logos.get(source, logos["DEFAULT"])

def safe_thumb_from_meta(meta: Dict, source: str) -> Optional[str]:
    # Try known fields
    if not isinstance(meta, dict):
        return None
    # MET: primaryImageSmall or primaryImage
    if meta.get("primaryImageSmall") and is_valid_image_url(meta.get("primaryImageSmall")):
        return meta.get("primaryImageSmall")
    if meta.get("primaryImage") and is_valid_image_url(meta.get("primaryImage")):
        return meta.get("primaryImage")
    # AIC: use image_id to construct IIIF URL
    if meta.get("image_id"):
        url = f"https://www.artic.edu/iiif/2/{meta['image_id']}/full/400,/0/default.jpg"
        if is_valid_image_url(url):
            return url
    # CMA: images.web
    if meta.get("images") and isinstance(meta.get("images"), dict):
        img = meta["images"].get("web")
        if is_valid_image_url(img):
            return img
    # fallback
    return fallback_logo(source)

# ---------------------------
# AI helpers (safe)
# ---------------------------
def openai_client_from_key(key: str):
    """
    Return an OpenAI client wrapper (OpenAI class) if openai package available.
    Uses the modern OpenAI Python client if installed.
    """
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        # try old openai package usage
        try:
            import openai as o
            o.api_key = key
            return o
        except Exception:
            return None

def ai_generate_3part(character: str, seed: str, artwork_meta: Optional[Dict], key: Optional[str]) -> str:
    """
    Try to call OpenAI if key and client available. Otherwise return a local fallback composed text.
    """
    if key:
        client = openai_client_from_key(key)
        if client:
            title = artwork_meta.get("title") if artwork_meta else "Untitled"
            date = artwork_meta.get("objectDate") if artwork_meta else ""
            prompt = (
                f"You are an art historian and museum narrator. Produce three labeled sections for exhibition use:\n\n"
                f"1) Character Overview (2 sentences): about {character}. Seed: {seed}\n\n"
                f"2) Myth Narrative (3-6 sentences): an evocative museum audio-guide tone retelling key myth(s) of {character}.\n\n"
                f"3) Artwork Commentary (3-6 sentences): analyze the selected artwork titled '{title}', dated {date}. "
                f"Discuss composition, lighting, pose, symbolism, and how the image relates to the myth. Keep language accessible.\n\n"
                "Return sections separated by '---'."
            )
            try:
                # modern OpenAI client
                if hasattr(client, "responses"):
                    r = client.responses.create(model="gpt-4.1-mini", input=prompt)
                    return r.output_text or "[No text returned from AI]"
                else:
                    # fallback to older openai.ChatCompletion
                    import openai as o
                    resp = o.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}])
                    return resp.choices[0].message["content"]
            except Exception as e:
                return f"[AI generation failed: {e}]"
    # Local fallback generation (deterministic template)
    # Build three parts using character seed and artwork_meta fields
    overview = seed or CHARACTERS.get(character, {}).get("en", f"{character} — mythic figure.")
    narrative = (
        f"{character} is a central figure of myth. "
        "Legendary episodes and motifs around this figure have been retold across centuries, "
        "inviting reflection on power, desire, and fate."
    )
    if artwork_meta:
        title = artwork_meta.get("title", "Untitled")
        artist = artwork_meta.get("artistDisplayName") or artwork_meta.get("artist") or ""
        art_line = f"Selected work: {title}{(' — ' + artist) if artist else ''}."
        commentary = (
            f"{art_line} A museum reading notes composition and iconography that connect the image to {character}'s myth: "
            "look for emblematic objects, posture, and light treatment that link narrative and image."
        )
    else:
        commentary = "No artwork selected. Choose a work to generate a specific commentary."
    return f"Character Overview:\n{overview}\n\n---\n\nMyth Narrative:\n{narrative}\n\n---\n\nArtwork Commentary:\n{commentary}"

# ---------------------------
# Character relationship data
# ---------------------------
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
    ("Theseus", "Achilles", "influence"),
    ("Medusa", "Perseus", "conflict"),
    ("Minotaur", "Theseus", "conflict"),
    ("Cyclops", "Poseidon", "associate"),
]

def relation_text(a: str, b: str, rel: str) -> str:
    if rel == "parent":
        return f"🔹 {a} → {b}\n\n{a} is a progenitor figure whose attributes and myths help shape the domains associated with {b}."
    if rel == "conflict":
        return f"🔹 {a} → {b}\n\nThe relationship is conflictual: stories stage trials, violence or redemption between {a} and {b}."
    if rel == "influence":
        return f"🔹 {a} → {b}\n\n{a} exerts narrative or symbolic influence on {b}, visible in iconography and recurring motifs."
    if rel == "associate":
        return f"🔹 {a} → {b}\n\nAn associative relation: these figures appear together or share thematic attributes in mythic cycles."
    return f"🔹 {a} → {b}\n\nRelation: {rel}."

# ---------------------------
# UI: Sidebar / Page selection
# ---------------------------
st.sidebar.title("Mythic Art Explorer — Final")
st.sidebar.markdown("Add optional OpenAI key to enable AI features (session only).")
openai_key = st.sidebar.text_input("OpenAI API key (optional)", type="password")
if openai_key:
    st.session_state["OPENAI_KEY"] = openai_key

page = st.sidebar.selectbox("Select page", [
    "Home",
    "Explorer",
    "Saved Items",
    "Stories",
    "Visualization",
    "Character Profiles",
    "Character Relationships",
    "Personality Test",
    "AI Interpretation",
    "About"
])

# ---------------------------
# Keep a simple saved items mechanism
# ---------------------------
if "saved_items" not in st.session_state:
    st.session_state["saved_items"] = []

# ---------------------------
# HOME
# ---------------------------
if page == "Home":
    st.title("🏛 Mythic Art Explorer — Final")
    st.markdown(
        "Explore Greek & Roman myth artworks across multiple museum APIs (MET, Cleveland, Art Institute of Chicago).  \n"
        "Use the Explorer to search; save items to your personal pool; generate museum-style narratives and AI-assisted commentary."
    )
    st.markdown("**APIs used:** MET (The Metropolitan Museum of Art), Cleveland Museum of Art (Open Access), Art Institute of Chicago (AIC).")
    st.markdown("---")
    st.write("Quick tips:")
    st.write("- Use **Explorer** to find artworks (multi-source).")
    st.write("- Click **Save** on items you want to include in Stories or Analysis.")
    st.write("- Visit **Character Profiles** for detailed museum-style biographies (EN/CN).")
    st.write("- To enable AI generation, paste your OpenAI API key in the sidebar (optional).")

# ---------------------------
# EXPLORER
# ---------------------------
elif page == "Explorer":
    st.header("Explorer — Multi-museum search")
    query = st.text_input("Search keyword (e.g., Athena, Zeus, Medusa):", "Zeus")
    max_per_source = st.slider("Max per source", 10, 200, 80, step=10)
    if st.button("Search across MET / CMA / AIC"):
        st.info("Searching museums... This may take a few seconds.")
        results = []
        # MET
        ids = met_search_ids(query, max_results=max_per_source)
        for oid in ids[:max_per_source]:
            meta = met_get_object(oid)
            thumb = safe_thumb_from_meta(meta, "MET")
            results.append({"source": "MET", "id": oid, "title": meta.get("title"), "meta": meta, "thumb": thumb})
        # CMA
        cma_hits = cma_search(query)
        for m in cma_hits[:max_per_source]:
            thumb = safe_thumb_from_meta(m, "CMA")
            results.append({"source": "CMA", "id": m.get("id"), "title": m.get("title"), "meta": m, "thumb": thumb})
        # AIC
        aic_hits = aic_search(query)
        for m in aic_hits[:max_per_source]:
            thumb = safe_thumb_from_meta(m, "AIC")
            results.append({"source": "AIC", "id": m.get("id"), "title": m.get("title"), "meta": m, "thumb": thumb})
        st.session_state["explorer_results"] = results
        st.success(f"Search complete. {len(results)} total items (mixed sources).")

    res = st.session_state.get("explorer_results", [])
    if not res:
        st.info("No results yet. Run a search.")
    else:
        st.write(f"Showing {len(res)} results")
        cols = st.columns(3)
        for i, rec in enumerate(res):
            with cols[i % 3]:
                thumb = rec.get("thumb") or fallback_logo(rec.get("source"))
                # show safe thumb (if it's a remote svg logo the browser may still render; acceptable)
                st.image(thumb, use_column_width=True)
                st.write(f"**{rec.get('title', 'Untitled')}**")
                st.caption(f"{rec.get('source')} — id: {rec.get('id')}")
                if st.button(f"Save {rec.get('source')}:{rec.get('id')}", key=f"save_{rec.get('source')}_{rec.get('id')}"):
                    st.session_state["saved_items"].append(rec)
                    st.success("Saved to your selection pool.")
                if st.button(f"View {i}", key=f"view_{rec.get('source')}_{i}"):
                    st.session_state["detail_item"] = rec

    # Detail view (single)
    if "detail_item" in st.session_state:
        st.markdown("---")
        item = st.session_state["detail_item"]
        st.subheader(item.get("title", "Untitled"))
        st.caption(f"Source: {item.get('source')} / ID: {item.get('id')}")
        st.image(item.get("thumb") or fallback_logo(item.get("source")), width=420)
        meta = item.get("meta", {})
        # display available metadata fields in a compact way
        st.write("**Metadata**")
        # try common fields
        if meta:
            st.write(f"- Date: {meta.get('objectDate') or meta.get('date')}")
            st.write(f"- Medium: {meta.get('medium') or meta.get('technique')}")
            st.write(f"- Culture: {meta.get('culture') or meta.get('cultureName')}")
            if meta.get("objectURL"):
                st.write(f"[Open on museum page]({meta.get('objectURL')})")
        st.markdown("---")

# ---------------------------
# SAVED ITEMS
# ---------------------------
elif page == "Saved Items":
    st.header("Saved Items — Your Selection Pool")
    saved = st.session_state.get("saved_items", [])
    st.write(f"You have {len(saved)} saved items.")
    if saved:
        cols = st.columns(3)
        for i, rec in enumerate(saved):
            with cols[i % 3]:
                st.image(rec.get("thumb") or fallback_logo(rec.get("source")), use_column_width=True)
                st.write(f"**{rec.get('title','Untitled')}**")
                st.caption(f"{rec.get('source')} / ID: {rec.get('id')}")
                if st.button(f"Remove {i}", key=f"rm_{i}"):
                    st.session_state["saved_items"].pop(i)
                    st.experimental_rerun()

        st.markdown("---")
        st.write("You can use saved items as input for Myth Stories, AI Interpretation, or Data Analysis.")
    else:
        st.info("Your selection pool is empty. Use Explorer to add items.")

# ---------------------------
# STORIES (existing feature + enhanced AI generation)
# ---------------------------
elif page == "Stories":
    st.header("Myth Stories — Generate museum-style narratives and commentary")
    st.write("Pick a saved item, choose a character, and generate a 3-part museum text (Overview / Narrative / Artwork Commentary).")
    saved = st.session_state.get("saved_items", [])
    character = st.selectbox("Choose character", CHARACTER_LIST)
    chosen_idx = st.selectbox("Choose saved item (index)", list(range(len(saved))) if saved else ["None"])
    seed_en = CHARACTERS.get(character, {}).get("en", "")
    seed_cn = CHARACTERS.get(character, {}).get("cn", "")

    if chosen_idx != "None" and saved:
        selected = saved[int(chosen_idx)]
        st.subheader("Selected artwork")
        st.image(selected.get("thumb") or fallback_logo(selected.get("source")), width=360)
        st.write(f"**{selected.get('title')}** — {selected.get('source')}")
        if st.button("Generate 3-part text (AI if available)"):
            key = st.session_state.get("OPENAI_KEY") or None
            # craft the artwork meta for ai function
            meta = selected.get("meta") or {}
            out = ai_generate_3part(character, seed_en, meta, key)
            # Show both EN and CN: if AI provided single-language, also show CN by using local CN template
            st.markdown("### English")
            st.text_area("AI / Text (EN)", out, height=300)
            # produce Chinese translation using AI if key present, otherwise fallback to local CN seeds + templates
            if key:
                try:
                    client = openai_client_from_key(key)
                    if client and hasattr(client, "responses"):
                        # ask AI to translate to Chinese
                        trans_prompt = f"Translate the following exhibition text into concise Traditional Chinese / Simplified Chinese for museum labels. Keep labels and sections:\n\n{out}"
                        r = client.responses.create(model="gpt-4.1-mini", input=trans_prompt)
                        cn_text = r.output_text or ""
                    else:
                        cn_text = seed_cn + "\n\n[Translation not available]"
                except Exception as e:
                    cn_text = f"[Translation failed: {e}]"
            else:
                # local fallback: assemble CN using seed_cn and short templates
                cn_text = seed_cn + "\n\n(Chinese commentary not generated — add OpenAI key to enable translation.)"
            st.markdown("### 中文")
            st.text_area("AI / Text (CN)", cn_text, height=300)
            st.download_button("Download story (txt)", data=out + "\n\n\nChinese:\n" + cn_text, file_name=f"{character}_story.txt")

    else:
        st.info("No saved item selected. Save an artwork in Saved Items first.")

# ---------------------------
# VISUALIZATION (existing)
# ---------------------------
elif page == "Visualization":
    st.header("Data Visualization — MET-focused analytics")
    st.write("This page performs lightweight analysis on MET metadata for a chosen figure.")
    fig_char = st.selectbox("Choose figure for dataset", CHARACTER_LIST, index=0)
    if st.button("Fetch MET dataset (sample)"):
        ids = met_search_ids(fig_char, max_results=300)
        metas = []
        p = st.progress(0)
        for i, oid in enumerate(ids[:200]):
            meta = met_get_object(oid)
            if meta:
                metas.append(meta)
            if i % 20 == 0:
                p.progress(min(100, int((i+1)/max(1,len(ids))*100)))
            time.sleep(0.005)
        st.session_state["viz_dataset"] = metas
        st.success(f"Fetched {len(metas)} MET records (sample).")
    data = st.session_state.get("viz_dataset", [])
    if data:
        # simple counts: mediums and years
        years = [m.get("objectBeginDate") for m in data if isinstance(m.get("objectBeginDate"), int)]
        mediums = [ (m.get("medium") or "Unknown").lower() for m in data ]
        import plotly.express as px
        if years:
            st.plotly_chart(px.histogram(x=years, nbins=30, title="Year distribution"), use_container_width=True)
        if mediums:
            cnt = collections.Counter(mediums).most_common(15)
            fig2 = px.bar(x=[c for _,c in cnt], y=[k for k,_ in cnt], orientation="h", labels={"x":"Count","y":"Medium"}, title="Top mediums")
            st.plotly_chart(fig2, use_container_width=True)

# ---------------------------
# CHARACTER PROFILES (new)
# ---------------------------
elif page == "Character Profiles":
    st.header("Character Profiles — Detailed museum-style Bios (EN / 中文)")
    character = st.selectbox("Choose character", CHARACTER_LIST, index=0)
    st.markdown("**English (museum label)**")
    en = CHARACTERS.get(character, {}).get("en", f"{character} — mythic figure.")
    st.write(en)
    st.markdown("**中文（博物馆展签风格）**")
    cn = CHARACTERS.get(character, {}).get("cn", "")
    if cn:
        st.write(cn)
    else:
        # fallback: simple translation-style placeholder
        st.write("（暂无中文展签。可在侧栏输入 OpenAI key 并使用 AI 翻译或编辑。）")
    # More detailed "curator notes" (expanded version)
    if st.checkbox("Show curator notes (expanded explanation)", value=False):
        # assemble a longer explanation heuristically
        extra = f"{character} is a key figure across many artworks and media. "
        extra += "Curatorial commentary should point to recurring symbols, historical variations, and interpretive questions for viewers: "
        if character in ["Medusa","Perseus","Theseus","Heracles"]:
            extra += "Consider the interplay of heroism and monstrosity; how the object frames violence and transformation."
        else:
            extra += "Consider the ways the figure is used to convey civic values, ritual power, or personal devotion."
        st.write(extra)

# ---------------------------
# CHARACTER RELATIONSHIPS (new)
# ---------------------------
elif page == "Character Relationships":
    st.header("Character Relationships — Museum-style explanations")
    st.write("Explanations are presented first (easy reading). An interactive network is shown if pyvis is installed.")
    # Show panel summary
    st.markdown("### Panel summary")
    st.write("This panel summarizes mythic genealogies and thematic relations between key figures. Use the bullet list for readable exhibition labels.")
    st.markdown("---")
    for a,b,rel in RELATIONS:
        st.markdown(relation_text(a,b,rel))

    st.markdown("---")
    st.write("Interactive network (optional)")
    if PYVIS_AVAILABLE:
        try:
            G = nx.Graph()
            for a,b,rel in RELATIONS:
                G.add_node(a); G.add_node(b); G.add_edge(a,b, relation=rel)
            nt = Network(height="650px", width="100%", bgcolor="#ffffff", font_color="black", notebook=False)
            for n in G.nodes():
                nt.add_node(n, label=n, title=n)
            for u,v,data in G.edges(data=True):
                nt.add_edge(u, v, title=data.get("relation",""))
            html_str = nt.generate_html()
            st.components.v1.html(html_str, height=680, scrolling=True)
        except Exception as e:
            st.error(f"Interactive network failed: {e}")
    else:
        st.info("Interactive network unavailable. To enable, install pyvis and networkx in your environment.")

# ---------------------------
# PERSONALITY TEST (new)
# ---------------------------
elif page == "Personality Test":
    st.header("Personality Test — Which mythic figure are you?")
    st.write("Quick quiz — pick options and get a mythic match.")
    q1 = st.radio("In a group you usually:", ["Lead", "Support", "Create", "Question"], index=0)
    q2 = st.radio("You prefer:", ["Order", "Wisdom", "Passion", "Adventure"], index=1)
    q3 = st.slider("How much do you value tradition vs change?", 0, 10, 5)
    q4 = st.selectbox("Pick a symbol", ["Thunderbolt", "Owl", "Lyre", "Bow", "Bull"], index=1)

    if st.button("Reveal your mythic match"):
        score = {"Zeus":0,"Athena":0,"Apollo":0,"Artemis":0,"Perseus":0,"Heracles":0,"Medusa":0,"Orpheus":0}
        if q1 == "Lead": score["Zeus"] += 2; score["Heracles"] += 1
        if q1 == "Support": score["Athena"] += 1; score["Orpheus"] += 1
        if q1 == "Create": score["Apollo"] += 2; score["Orpheus"] += 1
        if q1 == "Question": score["Athena"] += 2; score["Perseus"] += 1
        if q2 == "Order": score["Zeus"] += 2; score["Athena"] += 1
        if q2 == "Wisdom": score["Athena"] += 2; score["Orpheus"] += 1
        if q2 == "Passion": score["Apollo"] += 2; score["Dionysus"] = score.get("Dionysus",0)+2
        if q2 == "Adventure": score["Perseus"] += 2; score["Heracles"] += 1
        if q3 <= 3: score["Orpheus"] += 1
        if q3 >= 7: score["Zeus"] += 1
        if q4 == "Thunderbolt": score["Zeus"] += 2
        if q4 == "Owl": score["Athena"] += 2
        if q4 == "Lyre": score["Apollo"] += 2; score["Orpheus"] += 1
        if q4 == "Bow": score["Artemis"] = score.get("Artemis",0)+2
        if q4 == "Bull": score["Poseidon"] = score.get("Poseidon",0)+1

        match = max(score, key=score.get)
        st.success(f"Your mythic match: {match}")
        st.write("Museum-style introduction:")
        st.markdown("**English**")
        st.write(CHARACTERS.get(match, {}).get("en", ""))
        st.markdown("**中文**")
        st.write(CHARACTERS.get(match, {}).get("cn", "（暂无中文展签）"))

# ---------------------------
# AI INTERPRETATION (new)
# ---------------------------
elif page == "AI Interpretation":
    st.header("AI Interpretation — Image & Data Inquiry")
    st.write("Upload an artwork image to get a basic automated analysis (color, composition hints). For richer textual interpretation, provide an OpenAI API key in the sidebar.")
    uploaded = st.file_uploader("Upload an image (optional)", type=["png","jpg","jpeg"])
    text_query = st.text_area("Or paste JSON metadata or ask a question about your saved items (optional)", height=100)
    if uploaded and PIL_AVAILABLE:
        try:
            img = Image.open(uploaded)
            st.image(img, caption="Uploaded image", use_column_width=True)
            # Basic color summary: compute top 3 colors (naive)
            small = img.resize((100,100)).convert("RGB")
            colors = small.getcolors(10000)
            colors_sorted = sorted(colors, key=lambda x: x[0], reverse=True)[:6]
            top_colors = [c[1] for c in colors_sorted]
            st.write("Top colors (RGB):")
            st.write(top_colors)
            # simple aspect ratio and orientation
            w, h = img.size
            st.write(f"Dimensions: {w} x {h} (orientation: {'Landscape' if w>h else 'Portrait' if h>w else 'Square'})")
            # simple composition hint: center of mass of brightness
            import numpy as np
            arr = np.array(small.convert("L"))
            ys, xs = np.meshgrid(range(arr.shape[1]), range(arr.shape[0]))
            mass_y = (arr * ys).sum() / arr.sum() if arr.sum() else arr.shape[1]//2
            mass_x = (arr * xs).sum() / arr.sum() if arr.sum() else arr.shape[0]//2
            st.write(f"Estimated brightness centre (x,y): {(mass_x, mass_y)} — may indicate focal region.")
        except Exception as e:
            st.error(f"Image analysis failed: {e}")
    else:
        if uploaded and not PIL_AVAILABLE:
            st.warning("Pillow not available: image analysis disabled. Install pillow to enable.")

    if text_query and st.button("Run AI text interpretation (optional)"):
        key = st.session_state.get("OPENAI_KEY") or None
        if not key:
            st.warning("No OpenAI key provided. AI text features require a valid key in the sidebar.")
        else:
            try:
                client = openai_client_from_key(key)
                if not client:
                    st.error("OpenAI client not available in environment.")
                else:
                    prompt = f"You are an art historian assistant. Analyze this input and provide a concise interpretation and suggested exhibition label:\n\n{text_query}\n\nKeep output under 200 words."
                    if hasattr(client, "responses"):
                        r = client.responses.create(model="gpt-4.1-mini", input=prompt)
                        out = r.output_text or ""
                    else:
                        import openai as o
                        out = o.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}]).choices[0].message["content"]
                    st.write(out)
            except Exception as e:
                st.error(f"AI request failed: {e}")

# ---------------------------
# ABOUT
# ---------------------------
elif page == "About":
    st.header("About & Notes")
    st.markdown(
        "- **APIs used**: Metropolitan Museum of Art (MET), Cleveland Museum of Art (CMA), Art Institute of Chicago (AIC).\n"
        "- **AI**: optional OpenAI integration (paste key in the sidebar). If no key provided, local fallback templates are used.\n"
        "- **Interactive network**: optional (install pyvis & networkx)."
    )
    st.markdown("## Deployment notes")
    st.write("To run the app with AI features, add your OpenAI API key in the sidebar (session only).")
    st.write("If you plan to deploy on Streamlit Cloud, include required packages in requirements.txt (streamlit, requests, pillow, plotly).")

# ---------------------------
# End of file
# ---------------------------
