# final_app.py
"""
Mythic Art Explorer — Final integrated app (A + D)
Features:
 - Mythic Art Explorer (A): multi-alias MET search + medium-level heuristic filtering
 - Myth Stories (D): MET tag-precise search + 3-part museum-text generation (Character Overview / Myth Narrative / Artwork Commentary)
 - Art Data (analytics), Style Transfer (optional via OpenAI images), About
 - Safe OpenAI wrapper with graceful fallbacks when key/sdk missing
"""

import streamlit as st
import requests
import time
import json
import collections
from typing import List, Dict, Optional
import plotly.express as px

# --------------- Page config ---------------
st.set_page_config(page_title="Mythic Art Explorer — Final", layout="wide")

# --------------- Local myth seeds & lists ---------------
MYTH_DB = {
    "Zeus": "Zeus, king of the Olympian gods, wielder of thunder, arbiter of vows and order among gods and humans.",
    "Hera": "Hera, queen of the gods and guardian of marriage.",
    "Athena": "Athena, goddess of wisdom and strategic warfare, patron of cities and crafts.",
    "Apollo": "Apollo, god of music, prophecy, and the sun.",
    "Artemis": "Artemis, goddess of the hunt and the moon.",
    "Aphrodite": "Aphrodite, goddess of love and beauty.",
    "Hermes": "Hermes, messenger of the gods and guide of travelers.",
    "Perseus": "Perseus, hero who beheaded Medusa and rescued Andromeda.",
    "Medusa": "Medusa, one of the Gorgons whose gaze turns mortals to stone.",
    "Theseus": "Theseus, hero who slew the Minotaur."
}
MYTH_LIST = sorted(list(MYTH_DB.keys()))

# --------------- MET API endpoints & helpers ---------------
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

# --------------- Tag-precise filter using MET 'tags' ---------------
GREEK_MYTH_TAGS_SHORT = [
    "Greek Mythology","Zeus","Hera","Athena","Apollo","Artemis","Aphrodite","Hermes",
    "Perseus","Medusa","Theseus","Heracles","Dionysus","Poseidon","Hades","Demeter",
    "Persephone","Narcissus","Orpheus","Minotaur","Gorgon","Centaur","Satyr"
]

def is_greek_myth_by_tags(meta: Dict) -> bool:
    """Return True if MET object's tags include clear Greek/roman myth tags."""
    if not meta:
        return False
    tags = meta.get("tags") or []
    # tags are list of dicts like {"term": "..."}
    terms = []
    for t in tags:
        if isinstance(t, dict):
            term = t.get("term")
            if term:
                terms.append(term)
    for keyword in GREEK_MYTH_TAGS_SHORT:
        if keyword in terms:
            return True
    # fallback: check title/culture as weak signal
    title = (meta.get("title") or "").lower()
    culture = (meta.get("culture") or "").lower()
    if any(k.lower() in title for k in ["myth","goddess","god","medusa","minotaur","athena","zeus","perseus"]):
        return True
    if any(k in culture for k in ["greek","roman","hellenistic"]):
        return True
    return False

# --------------- Heuristic medium-level filter (for Explorer A) ---------------
def is_greek_roman_meta_medium(meta: Dict) -> bool:
    """Medium-level heuristic used by the Explorer to keep broader results but remove clear non-myth items."""
    if not meta:
        return False
    def c(text, keys):
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
    positive = ["greek", "hellenistic", "roman", "classical", "greco-roman"]
    myth_keywords = ["zeus","athena","apollo","artemis","perseus","medusa","minotaur","orpheus","narcissus","theseus","achilles","heracles","hera","aphrodite","poseidon","hades","demeter","persephone"]
    allowed_class = ["sculpture","vessel","ceramics","painting","drawing","print","relief","statuette","oil on canvas","marble","bronze"]
    if c(culture, positive) or c(period, positive):
        return True
    if c(title, myth_keywords) or c(objname, myth_keywords):
        return True
    if c(classification, allowed_class) and c(title, ["god","hero","myth","goddess","scene"]):
        return True
    rejects = ["costume","arms and armor","photographs","modern and contemporary","musical instruments","textiles"]
    if c(department, rejects) or c(classification, rejects):
        return False
    return False

# --------------- OpenAI wrapper (safe) ---------------
def has_openai_key() -> bool:
    return "OPENAI_API_KEY" in st.session_state and st.session_state["OPENAI_API_KEY"]

def openai_client():
    try:
        from openai import OpenAI
        return OpenAI(api_key=st.session_state.get("OPENAI_API_KEY",""))
    except Exception:
        return None

def ai_generate_text(prompt: str, model: str = "gpt-4.1-mini", max_tokens: int = 400) -> str:
    client = openai_client()
    if not client:
        raise RuntimeError("OpenAI client not available")
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text or ""

# --------------- Sidebar & navigation ---------------
st.sidebar.title("Mythic Art Explorer")
st.sidebar.markdown("Use MET API to explore Greek & Roman myth artworks. Add OpenAI API key to enable AI features.")
api_key = st.sidebar.text_input("OpenAI API Key (session only)", type="password", key="openai_key")
if st.sidebar.button("Save API key"):
    if api_key:
        st.session_state["OPENAI_API_KEY"] = api_key
        st.sidebar.success("Saved to session.")
    else:
        st.sidebar.warning("Enter a key before saving.")

st.sidebar.markdown("---")
page = st.sidebar.selectbox("Select a page:", [
    "Home",
    "Mythic Art Explorer (A)",
    "Myth Stories (D)",
    "Art Data",
    "Style Transfer",
    "About"
], index=1)

# ---------------- Home ----------------
if page == "Home":
    st.title("🏛 Mythic Art Explorer — Final (A + D)")
    st.write("""
    This project combines broad MET-based exploration (Explorer A) and high-precision tag-filtered storytelling (Stories D).
    Use the sidebar to navigate. Fill OpenAI API key to enable AI label / narrative generation.
    """)
    st.markdown("---")
    st.write("Quick tips:")
    st.write("- Use **Mythic Art Explorer (A)** to browse many candidate artworks (wide coverage).")
    st.write("- Use **Myth Stories (D)** to find only curator-tagged artworks for a character and generate 3-part museum text.")

# ---------------- Mythic Art Explorer (A) ----------------
elif page == "Mythic Art Explorer (A)":
    st.header("Mythic Art Explorer — Broad search + medium filter (A)")
    selected = st.selectbox("Choose a mythic figure", MYTH_LIST, index=0)
    st.info(MYTH_DB.get(selected, ""))

    st.markdown("**Aliases used for search (auto-generated):**")
    def generate_aliases(name: str) -> List[str]:
        mapping = {
            "Athena": ["Pallas Athena", "Minerva"],
            "Zeus": ["Jupiter"],
            "Aphrodite": ["Venus"],
            "Hermes": ["Mercury"],
            "Heracles": ["Hercules"]
        }
        aliases = [name] + mapping.get(name, []) + [f"{name} myth", f"{name} greek", f"{name} mythology"]
        out=[]; seen=set()
        for a in aliases:
            if a not in seen:
                seen.add(a); out.append(a)
        return out

    st.write(generate_aliases(selected))
    max_results = st.slider("Max MET records per alias", 20, 300, 120, step=10)

    if st.button("Fetch related works (medium-filtered)"):
        aliases = generate_aliases(selected)
        all_ids = []
        p = st.progress(0)
        for i,a in enumerate(aliases):
            ids = met_search_ids(a, max_results=max_results)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate IDs. Fetching metadata + applying medium-level filter...")

        thumbs=[]
        p2 = st.progress(0)
        total = max(1, len(all_ids))
        for i, oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m and is_greek_roman_meta_medium(m):
                thumb = m.get("primaryImageSmall") or m.get("primaryImage") or (m.get("additionalImages") or [None])[0]
                thumbs.append({"id": oid, "meta": m, "thumb": thumb})
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/total*100)))
            time.sleep(0.004)
        p2.empty()
        st.session_state["gallery_thumbs"] = thumbs
        st.success(f"{len(thumbs)} filtered works ready.")

    thumbs = st.session_state.get("gallery_thumbs", [])
    if not thumbs:
        st.info("No works yet. Click 'Fetch related works (medium-filtered)'.")
    else:
        st.write(f"Showing {len(thumbs)} artworks (click 'Select' to choose for AI label).")
        cols = st.columns(3)
        for idx, rec in enumerate(thumbs):
            with cols[idx % 3]:
                meta = rec["meta"]
                title = meta.get("title","Untitled")
                artist = meta.get("artistDisplayName","Unknown")
                date = meta.get("objectDate","")
                medium = meta.get("medium","")
                if rec["thumb"]:
                    st.image(rec["thumb"], use_column_width=True)
                st.markdown(f"**{title}**")
                st.markdown(f"{artist} • {date} • {medium}")
                st.markdown(f"[Open on MET]({meta.get('objectURL')})")
                if st.button(f"Select {rec['id']}", key=f"sel_{rec['id']}"):
                    st.session_state["selected_artwork"] = rec
                    st.success(f"Selected artwork {rec['id']}")

    if "selected_artwork" in st.session_state:
        rec = st.session_state["selected_artwork"]
        meta = rec["meta"]
        st.markdown("---")
        st.subheader("Selected artwork")
        st.image(meta.get("primaryImage") or meta.get("primaryImageSmall") or rec["thumb"], width=360)
        st.write(f"**{meta.get('title','Untitled')}**")
        st.write(f"{meta.get('artistDisplayName','Unknown')} • {meta.get('objectDate','')} • {meta.get('medium','')}")
        st.write(f"[Open on MET]({meta.get('objectURL')})")
        st.markdown("---")
        if st.button("Generate AI museum label for this artwork"):
            if not has_openai_key():
                st.warning("No OpenAI key saved. Please add in sidebar.")
            else:
                prompt = f"""You are an art historian writing a museum label (50-120 words) for exhibition visitors.
Title: {meta.get('title')}
Artist: {meta.get('artistDisplayName')}
Date: {meta.get('objectDate')}
Medium: {meta.get('medium')}
Context: Greek/Roman myth related art; link the image to myth, mention key symbols and viewing cues."""
                try:
                    text = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=250)
                except Exception as e:
                    st.error(f"AI generation failed: {e}")
                    text = "Local fallback: This artwork depicts a mythic scene. No AI label available."
                st.markdown("### AI Museum Label")
                st.write(text)
                st.download_button("Download label (txt)", data=text, file_name="label.txt", mime="text/plain")

# ---------------- Myth Stories (D) ----------------
elif page == "Myth Stories (D)":
    st.header("Myth Stories — Tag-precise search + 3-part museum text (D)")
    st.write("This page uses MET object's tags for high-precision matching to a mythic character, then generates a 3-part museum text (Character Overview / Myth Narrative / Artwork Commentary).")
    character = st.selectbox("Choose character", MYTH_LIST, index=0)
    st.info(MYTH_DB.get(character, "No local seed available."))

    # tags mapping for targeted search
    MYTH_TAGS = {
        "Zeus": ["Zeus","Jupiter","Greek Mythology"],
        "Hera": ["Hera","Juno","Greek Mythology"],
        "Athena": ["Athena","Pallas Athena","Minerva","Greek Mythology"],
        "Apollo": ["Apollo","Greek Mythology"],
        "Artemis": ["Artemis","Diana","Greek Mythology"],
        "Aphrodite": ["Aphrodite","Venus","Greek Mythology"],
        "Hermes": ["Hermes","Mercury","Greek Mythology"],
        "Perseus": ["Perseus","Greek Mythology"],
        "Medusa": ["Medusa","Gorgon","Greek Mythology"],
        "Theseus": ["Theseus","Greek Mythology"]
    }
    tags = MYTH_TAGS.get(character, [character, "Greek Mythology"])
    st.write("Matched tags for search:", ", ".join(tags))

    if st.button("Find MET artworks (tag-precise)"):
        st.info("Searching MET (tag-precise)...")
        ids = []
        p = st.progress(0)
        for i, t in enumerate(tags):
            res = met_search_ids(t, max_results=150)
            if res:
                for oid in res:
                    if oid not in ids:
                        ids.append(oid)
            p.progress(int((i+1)/len(tags)*100))
        p.empty()
        st.write(f"Raw candidate IDs: {len(ids)} — now fetch metadata & validate tags...")
        results = []
        p2 = st.progress(0)
        for i, oid in enumerate(ids):
            m = met_get_object_cached(oid)
            if not m:
                continue
            # Validate tags field
            m_tags = [t.get("term") for t in (m.get("tags") or []) if isinstance(t, dict)]
            if any(t in (m_tags or []) for t in tags):
                thumb = m.get("primaryImageSmall") or m.get("primaryImage") or (m.get("additionalImages") or [None])[0]
                results.append({"id": oid, "meta": m, "thumb": thumb})
            if i % 20 == 0:
                p2.progress(min(100, int((i+1)/max(1,len(ids))*100)))
            time.sleep(0.003)
        p2.empty()
        st.session_state["story_tag_results"] = results
        st.success(f"{len(results)} validated artworks found (tag-precise).")

    results = st.session_state.get("story_tag_results", [])
    if not results:
        st.info("No tag-precise artworks yet. Click the button above.")
    else:
        st.markdown("### Results (select one for detailed commentary)")
        cols = st.columns(3)
        for idx, rec in enumerate(results):
            with cols[idx % 3]:
                meta = rec["meta"]
                if rec["thumb"]:
                    st.image(rec["thumb"], use_column_width=True)
                st.write(f"**{meta.get('title','Untitled')}**")
                st.write(meta.get("artistDisplayName","Unknown"))
                if st.button(f"Select {rec['id']}", key=f"story_sel_{rec['id']}"):
                    st.session_state["story_selected"] = rec
                    st.success("Selected.")

    selected = st.session_state.get("story_selected")
    if selected:
        m = selected["meta"]
        st.markdown("---")
        st.subheader(f"Selected: {m.get('title','Untitled')}")
        if m.get("primaryImage"):
            st.image(m.get("primaryImage"), width=360)
        st.write(f"{m.get('artistDisplayName','Unknown')} • {m.get('objectDate','')}")
        st.write(f"[Open on MET]({m.get('objectURL')})")

        if st.button("Generate AI 3-Part Museum Text"):
            if not has_openai_key():
                st.warning("No OpenAI key saved. Add it in the sidebar to enable AI generation.")
            else:
                seed = MYTH_DB.get(character, "")
                prompt = f"""
You are an art historian and museum curator. Produce three labeled sections for exhibition use:

1) Character Overview (1-2 sentences) about {character}. Seed: {seed}

2) Myth Narrative (3-6 sentences) — an emotive museum audio-guide style retelling of the main myth(s).

3) Artwork Commentary (3-6 sentences) — analyze the selected artwork:
Title: {m.get('title')}
Artist: {m.get('artistDisplayName')}
Date: {m.get('objectDate')}
Discuss composition, lighting, pose, symbolism, and how the image relates to the myth.

Return the three sections separated by '---' and label each section.
"""
                try:
                    out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=700)
                except Exception as e:
                    out = f"[AI generation failed: {e}]"
                if isinstance(out, str) and '---' in out:
                    parts = [p.strip() for p in out.split('---') if p.strip()]
                    for p in parts:
                        if p.lower().startswith("1") or "overview" in p.lower():
                            st.markdown("### 🧾 Character Overview")
                            st.write(p)
                        elif p.lower().startswith("2") or "narrative" in p.lower():
                            st.markdown("### 📖 Myth Narrative")
                            st.write(p)
                        elif p.lower().startswith("3") or "artwork" in p.lower():
                            st.markdown("### 🖼 Artwork Commentary")
                            st.write(p)
                        else:
                            st.write(p)
                else:
                    st.markdown("### Generated Text")
                    st.write(out)
                st.download_button("Download museum text (txt)", data=out, file_name=f"{character}_museum_text.txt", mime="text/plain")

# ---------------- Art Data ----------------
elif page == "Art Data":
    st.header("Art Data — dataset summary & AI-assisted analysis")
    figure = st.selectbox("Choose figure", MYTH_LIST)
    if st.button("Fetch & Analyze (medium-filtered)"):
        aliases = [figure] + [f"{figure} myth", f"{figure} greek"]
        all_ids=[]
        p=st.progress(0)
        for i,a in enumerate(aliases):
            ids = met_search_ids(a, max_results=150)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate IDs; fetching metadata...")
        metas=[]
        for i,oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m and is_greek_roman_meta_medium(m):
                metas.append(m)
            if i % 20 == 0:
                st.progress(min(100, int((i+1)/max(1,len(all_ids))*100)))
            time.sleep(0.003)
        st.session_state["analysis_dataset"] = metas
        st.success(f"Dataset prepared: {len(metas)} records.")
    dataset = st.session_state.get("analysis_dataset", [])
    if not dataset:
        st.info("No dataset loaded. Click 'Fetch & Analyze (medium-filtered)'.")
    else:
        st.write(f"Analyzing {len(dataset)} records")
        years=[]; mediums=[]
        for m in dataset:
            y = m.get("objectBeginDate")
            if isinstance(y,int): years.append(y)
            med = (m.get("medium") or "").lower()
            if med: mediums.append(med)
        if years:
            fig = px.histogram(x=years, nbins=30, title="Year distribution")
            st.plotly_chart(fig, use_container_width=True)
        if mediums:
            cnt = collections.Counter(mediums).most_common(10)
            fig2 = px.bar(x=[c for _,c in cnt], y=[k for k,_ in cnt], orientation="h", labels={"x":"Count","y":"Medium"})
            st.plotly_chart(fig2, use_container_width=True)
        if st.button("AI: generate short analysis of dataset"):
            if not has_openai_key():
                st.warning("No OpenAI key.")
            else:
                sample = json.dumps([{"objectID":m.get("objectID"), "title":m.get("title"), "date":m.get("objectDate")} for m in dataset[:20]], ensure_ascii=False)
                prompt = f"You are an art historian. Given this dataset sample: {sample}\nWrite a concise analysis (4-6 sentences) describing trends, notable media, and what this suggests about depiction of {figure} in museum collections."
                try:
                    text = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=300)
                except Exception as e:
                    text = f"[AI failed: {e}]"
                st.markdown("### AI Analysis")
                st.write(text)

# ---------------- Style Transfer ----------------
elif page == "Style Transfer":
    st.header("Style Transfer — AI image generation (OpenAI required)")
    st.write("Upload a content image and a style image. The app will call the OpenAI images API to generate a blended stylized image.")
    if not has_openai_key():
        st.warning("Please save your OpenAI key in the sidebar to use this feature.")
    else:
        try:
            from openai import OpenAI
        except Exception:
            st.error("OpenAI SDK missing. Add 'openai>=1.0.0' to requirements.")
            st.stop()
        import base64
        client = openai_client()
        content = st.file_uploader("Content image", type=["png","jpg","jpeg"], key="st_content")
        style = st.file_uploader("Style image", type=["png","jpg","jpeg"], key="st_style")
        if content:
            st.image(content, caption="Content", width=240)
        if style:
            st.image(style, caption="Style", width=240)
        if content and style and st.button("Generate stylized image"):
            with st.spinner("Generating..."):
                try:
                    content_bytes = content.read()
                    style_bytes = style.read()
                    content_b64 = base64.b64encode(content_bytes).decode()
                    style_b64 = base64.b64encode(style_bytes).decode()
                    result = client.images.generate(model="gpt-image-1",
                                                    prompt="Blend the content image with the style image into a single stylized artwork.",
                                                    size="1024x1024",
                                                    image=[{"data": content_b64},{"data": style_b64}])
                    img_b64 = result.data[0].b64_json
                    final = base64.b64decode(img_b64)
                    st.image(final, caption="Stylized result", use_column_width=True)
                    st.download_button("Download image", data=final, file_name="style_transfer.png", mime="image/png")
                except Exception as e:
                    st.error(f"Image generation failed: {e}")

# ---------------- About ----------------
elif page == "About":
    st.header("About")
    st.write("Mythic Art Explorer — Final integrated version (A + D).")
    st.write("This app demonstrates API-driven art exploration and AI-assisted museum text generation.")
    st.write("If you plan to use AI features, add 'openai' to requirements and paste your API key in the sidebar.")

# --------------- End of file ---------------
