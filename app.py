# final_app.py
"""
Mythic Art Explorer — Version A (Large API usage, recommended)
- AI-enhanced: museum labels on click, Mythic Lineages AI explanations, Myth Stories AI generation.
- Fallback templates used if OpenAI key absent or API fails.
"""

import streamlit as st
import requests
import time
import json
import collections
from typing import List, Dict, Optional
import plotly.express as px

# Page config
st.set_page_config(page_title="Mythic Art Explorer (AI)", layout="wide")

# ---------- Local Myth Seeds ----------
MYTH_DB = {
    "Zeus": "Zeus, king of the Olympian gods, wielder of thunder, arbiter of vows and order among gods and humans.",
    "Hera": "Hera, queen of the gods, goddess of marriage, often depicted with peacock symbolism.",
    "Athena": "Athena, goddess of wisdom, craft, and strategic warfare; patroness of cities and heroes.",
    "Apollo": "Apollo, god of music, prophecy, and the sun; associated with lyres and oracles.",
    "Artemis": "Artemis, goddess of the hunt and the moon; protector of young women and animals.",
    "Aphrodite": "Aphrodite, goddess of love and beauty; associated with sea-born imagery.",
    "Hermes": "Hermes, messenger of the gods, trickster and guide of travelers.",
    "Dionysus": "Dionysus, god of wine, ritual ecstasy and theatre.",
    "Ares": "Ares, god of war and battle.",
    "Hephaestus": "Hephaestus, god of craft and metallurgy.",
    "Poseidon": "Poseidon, god of the sea, horses, and earthquakes.",
    "Hades": "Hades, ruler of the underworld.",
    "Demeter": "Demeter, goddess of grain and harvest.",
    "Persephone": "Persephone, queen of the underworld and goddess of spring.",
    "Heracles": "Heracles, hero of Twelve Labors.",
    "Perseus": "Perseus, slayer of Medusa and rescuer of Andromeda.",
    "Orpheus": "Orpheus, musician who attempted to rescue Eurydice from the underworld.",
    "Narcissus": "Narcissus, youth who loved his own reflection.",
    "Medusa": "Medusa, Gorgon whose gaze turns mortals to stone.",
    "Theseus": "Theseus, hero who slew the Minotaur."
}
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

# ---------- Heuristic medium-level filter (recommended) ----------
def is_greek_roman_meta_medium(meta: Dict) -> bool:
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

# ---------- OpenAI wrapper (safe) ----------
def has_openai_key() -> bool:
    return "OPENAI_API_KEY" in st.session_state and st.session_state["OPENAI_API_KEY"]

def openai_client():
    try:
        from openai import OpenAI
        return OpenAI(api_key=st.session_state.get("OPENAI_API_KEY", ""))
    except Exception:
        return None

def ai_generate_text(prompt: str, model: str = "gpt-4.1-mini", max_tokens: int = 400) -> str:
    """
    Unified AI generation function. Returns text or raises Exception.
    """
    client = openai_client()
    if not client:
        raise RuntimeError("OpenAI client not available")
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text or ""

# ---------- Sidebar ----------
st.sidebar.title("Mythic Art Explorer — AI")
st.sidebar.markdown("Fill your OpenAI API key to enable AI features.")
api_key = st.sidebar.text_input("OpenAI API Key (session only)", type="password", key="openai_key")
if st.sidebar.button("Save API key"):
    if api_key:
        st.session_state["OPENAI_API_KEY"] = api_key
        st.sidebar.success("API key saved to session.")
    else:
        st.sidebar.warning("Provide a valid OpenAI API key.")

st.sidebar.markdown("---")
st.sidebar.markdown("Pages:")
page = st.sidebar.selectbox("Select page", ["Home","Mythic Art Explorer","Art Data","Mythic Lineages","Myth Stories","Style Transfer","About"], index=1)

# ---------- Home ----------
if page == "Home":
    st.title("🏛 Mythic Art Explorer — AI-enhanced")
    if has_openai_key():
        try:
            prompt = "Write a concise friendly welcome paragraph for 'Mythic Art Explorer', an educational web app showcasing Greek & Roman myth artworks with AI-generated museum labels."
            welcome = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=120)
        except Exception:
            welcome = "Explore Greek & Roman myths and artworks. Use the sidebar to choose pages. Fill OpenAI API Key to enable AI features."
    else:
        welcome = "Explore Greek & Roman myths and artworks. Fill OpenAI API Key in the sidebar to enable AI features."
    st.write(welcome)
    st.write("Quick tips: Use 'Mythic Art Explorer' to find images; click a thumbnail and then 'Generate AI label' to let AI describe the work.")

# ---------- Mythic Art Explorer ----------
elif page == "Mythic Art Explorer":
    st.header("Mythic Art Explorer — Filtered MET Gallery")
    selected = st.selectbox("Choose a mythic figure", MYTH_LIST, index=0)
    st.write(MYTH_DB.get(selected, ""))
    st.markdown("**Search aliases:**")
    def generate_aliases(name: str) -> List[str]:
        mapping = {"Athena":["Pallas Athena","Minerva"], "Zeus":["Jupiter"], "Aphrodite":["Venus"], "Hermes":["Mercury"], "Heracles":["Hercules"]}
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
        all_ids=[]
        p=st.progress(0)
        for i,a in enumerate(aliases):
            ids = met_search_ids(a, max_results=max_results)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate IDs. Fetching metadata and applying medium-level filter...")
        thumbs=[]
        p2=st.progress(0)
        total=max(1,len(all_ids))
        for i,oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m and is_greek_roman_meta_medium(m):
                thumb = m.get("primaryImageSmall") or m.get("primaryImage") or (m.get("additionalImages") or [None])[0]
                thumbs.append({"id":oid,"meta":m,"thumb":thumb})
            if i%20==0:
                p2.progress(min(100,int((i+1)/total*100)))
            time.sleep(0.005)
        p2.empty()
        st.session_state["gallery_thumbs"] = thumbs
        st.success(f"{len(thumbs)} filtered works ready.")

    thumbs = st.session_state.get("gallery_thumbs", [])
    if not thumbs:
        st.info("No works yet. Click 'Fetch related works (medium-filtered)'.")
    else:
        st.write(f"Showing {len(thumbs)} artworks (click a Select button to choose for AI label).")
        cols = st.columns(3)
        for idx, rec in enumerate(thumbs):
            with cols[idx%3]:
                title = rec["meta"].get("title","Untitled")
                artist = rec["meta"].get("artistDisplayName","Unknown")
                date = rec["meta"].get("objectDate","")
                medium = rec["meta"].get("medium","")
                if rec["thumb"]:
                    st.image(rec["thumb"], use_column_width=True)
                st.markdown(f"**{title}**")
                st.markdown(f"{artist} • {date} • {medium}")
                st.markdown(f"[Open on MET]({rec['meta'].get('objectURL')})")
                if st.button(f"Select {rec['id']}", key=f"sel_{rec['id']}"):
                    st.session_state["selected_artwork"] = rec
                    st.success(f"Selected artwork {rec['id']}")

    # If an artwork selected, show details and AI label button
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
                st.warning("No OpenAI key saved. Please add it in the sidebar.")
            else:
                prompt = f"""You are an art historian writing a museum label (50-120 words) for exhibition visitors.
Write in the language: English.
Artwork metadata:
Title: {meta.get('title')}
Artist: {meta.get('artistDisplayName')}
Date: {meta.get('objectDate')}
Medium: {meta.get('medium')}
Dimensions: {meta.get('dimensions')}
Context: Greek/Roman myth related art; write a concise but evocative description linking image and myth, mention key symbols and suggested viewing cues.
"""
                try:
                    text = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=250)
                except Exception as e:
                    st.error(f"AI generation failed: {e}")
                    text = ("🔹 " + meta.get("title","Untitled") + "\n\n" +
                            "Local fallback: This artwork depicts a mythic scene. " +
                            "No AI label available.")
                st.markdown("### AI Museum Label")
                st.write(text)
                st.download_button("Download label (txt)", data=text, file_name="label.txt", mime="text/plain")

# ---------- Art Data ----------
elif page == "Art Data":
    st.header("Art Data — dataset summary (AI-enabled)")
    figure = st.selectbox("Choose figure", MYTH_LIST)
    if st.button("Fetch & Analyze (AI)"):
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
            if i%20==0:
                st.progress(min(100,int((i+1)/max(1,len(all_ids))*100)))
            time.sleep(0.003)
        st.session_state["analysis_dataset"] = metas
        st.success(f"Dataset prepared: {len(metas)} records.")
    dataset = st.session_state.get("analysis_dataset", [])
    if not dataset:
        st.info("No dataset loaded. Click 'Fetch & Analyze (AI)'.")
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

# ---------- Myth Stories (High-Accuracy Tag Filter) ----------
elif page == "Myth Stories":
    st.header("Myth Stories — Tag-Filtered Mythic Art Interpretation (AI)")

    MYTH_TAGS = {
        "Zeus": ["Zeus", "Jupiter", "Greek Mythology"],
        "Hera": ["Hera", "Juno", "Greek Mythology"],
        "Athena": ["Athena", "Pallas Athena", "Minerva", "Greek Mythology"],
        "Apollo": ["Apollo"],
        "Artemis": ["Artemis", "Diana"],
        "Aphrodite": ["Aphrodite", "Venus"],
        "Hermes": ["Hermes", "Mercury"],
        "Ares": ["Ares", "Mars"],
        "Poseidon": ["Poseidon", "Neptune"],
        "Hades": ["Hades", "Pluto"],
        "Dionysus": ["Dionysus", "Bacchus"],
        "Heracles": ["Heracles", "Hercules"],
        "Medusa": ["Medusa", "Gorgon"],
        "Perseus": ["Perseus"],
        "Theseus": ["Theseus"],
        "Orpheus": ["Orpheus"],
        "Narcissus": ["Narcissus"]
    }

    character = st.selectbox("Choose character", MYTH_LIST)
    tags = MYTH_TAGS.get(character, [])
    st.write("Matched tags:", ", ".join(tags))

    if st.button("Find artworks for this mythic figure"):
        st.info("Searching MET…")

        ids = []
        for t in tags:
            res = met_search_ids(t, max_results=150)
            for oid in res:
                if oid not in ids:
                    ids.append(oid)

        results = []
        p = st.progress(0)

        for i, oid in enumerate(ids):
            meta = met_get_object_cached(oid)
            tag_terms = [t["term"] for t in meta.get("tags", [])]

            if any(t in tag_terms for t in tags):
                thumb = meta.get("primaryImageSmall") or meta.get("primaryImage")
                if thumb:
                    results.append({"id": oid, "meta": meta, "thumb": thumb})

            p.progress(int((i + 1) / max(1, len(ids)) * 100))

        st.session_state["story_results"] = results
        st.success(f"Found {len(results)} valid mythic artworks.")

    # Display results
    results = st.session_state.get("story_results", [])

    if results:
        cols = st.columns(3)
        for idx, rec in enumerate(results):
            with cols[idx % 3]:
                meta = rec["meta"]
                st.image(rec["thumb"], use_column_width=True)
                st.write(f"**{meta.get('title')}**")
                if st.button(f"Select artwork {rec['id']}", key=f"s_{rec['id']}"):
                    st.session_state["selected_story_art"] = rec
                    st.success("Artwork selected")

    meta_rec = st.session_state.get("selected_story_art")

    if meta_rec:
        m = meta_rec["meta"]
        st.subheader("Selected Artwork")
        st.image(m.get("primaryImage"), width=360)
        st.write(f"**{m.get('title')}**")
        st.write(m.get("artistDisplayName"))
        st.write(m.get("objectDate"))

        if st.button("Generate AI 3-Part Museum Text"):
            if not has_openai_key():
                st.warning("Enter API key first.")
            else:
                seed = MYTH_DB.get(character, "")

                prompt = f"""
Write 3 museum texts for exhibition:

1) Character Overview — 2 sentences introducing {character}. Seed: {seed}

2) Myth Narrative — 5 sentences retelling a key myth of {character} in an evocative style.

3) Artwork Commentary — 5 sentences analyzing:
Title: {m.get('title')}
Artist: {m.get('artistDisplayName')}
Date: {m.get('objectDate')}
Explain composition, lighting, symbolism, and relation to the myth.

Separate sections with '---'.
"""

                text = ai_generate_text(prompt, max_tokens=600)
                st.write(text)

# ---------- Myth Stories ----------
elif page == "Myth Stories":
    st.header("Myth Stories — Character Overview / Myth Narrative / Artwork Commentary (AI)")
    character = st.selectbox("Choose character", MYTH_LIST, index=0)
    st.write("Local seed (if present):")
    st.info(MYTH_DB.get(character, "No local seed available; app can auto-generate one using AI."))

    if st.button("Search MET for character (medium-filtered)"):
        aliases = [character, f"{character} myth", f"{character} greek"]
        all_ids=[]
        p=st.progress(0)
        for i,a in enumerate(aliases):
            ids = met_search_ids(a, max_results=120)
            for oid in ids:
                if oid not in all_ids:
                    all_ids.append(oid)
            p.progress(int((i+1)/len(aliases)*100))
        p.empty()
        st.info(f"Found {len(all_ids)} candidate IDs. Fetching metadata...")
        results=[]
        p2=st.progress(0)
        total=max(1,len(all_ids))
        for i,oid in enumerate(all_ids):
            m = met_get_object_cached(oid)
            if m and is_greek_roman_meta_medium(m):
                thumb = m.get("primaryImageSmall") or m.get("primaryImage") or (m.get("additionalImages") or [None])[0]
                results.append({"id":oid,"meta":m,"thumb":thumb})
            if i%20==0:
                p2.progress(min(100,int((i+1)/total*100)))
            time.sleep(0.004)
        p2.empty()
        st.session_state["myth_results"] = results
        st.success(f"{len(results)} likely works found.")

    results = st.session_state.get("myth_results", [])
    if results:
        st.markdown("### Results (select one for commentary)")
        cols = st.columns(3)
        for idx, rec in enumerate(results):
            with cols[idx%3]:
                title = rec["meta"].get("title","Untitled")
                artist = rec["meta"].get("artistDisplayName","Unknown")
                date = rec["meta"].get("objectDate","Unknown")
                medium = rec["meta"].get("medium","")
                if rec["thumb"]:
                    st.image(rec["thumb"], use_column_width=True)
                st.write(f"**{title}**")
                st.write(f"{artist} • {date} • {medium}")
                if st.button(f"Select {rec['id']}", key=f"ms_{rec['id']}"):
                    st.session_state["myth_selected"] = rec
                    st.success(f"Selected {rec['id']}")
    else:
        st.info("No results. Click 'Search MET for character (medium-filtered)'.")

    meta = st.session_state.get("myth_selected")
    if meta:
        m = meta["meta"]
        st.markdown("---")
        st.subheader(f"Selected: {m.get('title','Untitled')}")
        if m.get("primaryImage"):
            st.image(m.get("primaryImage"), width=360)
        st.write(f"{m.get('artistDisplayName','Unknown')} • {m.get('objectDate','')} • {m.get('medium','')}")
        st.write(f"[Open on MET]({m.get('objectURL')})")

    st.markdown("---")
    st.write("Generate 3-part museum text")
    auto_seed = st.checkbox("Auto-generate Character Overview (if seed missing)", value=True)
    if st.button("Generate 3-part text (AI)"):
        seed = MYTH_DB.get(character,"")
        if not seed and auto_seed:
            if has_openai_key():
                try:
                    prompt_seed = f"Write a 1-2 sentence Character Overview for '{character}' suitable for a museum label."
                    seed = ai_generate_text(prompt_seed, model="gpt-4.1-mini", max_tokens=120).strip()
                except Exception:
                    seed = ""
            else:
                seed = ""
        if not seed and not meta:
            st.warning("No seed and no artwork selected. Please select an artwork or allow auto-seed.")
        else:
            title = meta["meta"].get("title") if meta else None
            artist = meta["meta"].get("artistDisplayName") if meta else None
            date = meta["meta"].get("objectDate") if meta else None
            prompt = f"""You are an art historian and museum curator. Produce three labeled sections for exhibition use:

1) Character Overview (1-2 sentences): about {character}. Seed: {seed}

2) Myth Narrative (3-6 sentences): an emotive museum audio-guide tone retelling key myth(s).

3) Artwork Commentary (3-6 sentences): analyze the selected artwork titled "{title}" by {artist}, dated {date}. Discuss composition, lighting, pose, symbolism, and link to the myth. Keep language accessible to students and visitors.

Return sections separated by '---' and label each section.
"""
            if not has_openai_key():
                st.warning("No OpenAI key. Cannot generate AI content.")
            else:
                try:
                    out = ai_generate_text(prompt, model="gpt-4.1-mini", max_tokens=700)
                except Exception as e:
                    out = f"[AI generation failed: {e}]"
                if "---" in out:
                    parts = [p.strip() for p in out.split("---") if p.strip()]
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
                st.download_button("Download text (txt)", data=out, file_name=f"{character}_museum_text.txt", mime="text/plain")

# ---------- Style Transfer ----------
elif page == "Style Transfer":
    st.header("Style Transfer — AI image generation (requires OpenAI key)")
    st.write("Upload a content image and a style image. The app will call the OpenAI images API to generate a blended stylized image.")
    if not has_openai_key():
        st.warning("Please save your OpenAI key in the sidebar to use this feature.")
    else:
        try:
            from openai import OpenAI
        except Exception:
            st.error("OpenAI SDK missing in environment. Add 'openai>=1.0.0' to requirements.")
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

# ---------- About ----------
elif page == "About":
    st.header("About")
    st.write("Mythic Art Explorer — Version A (AI-enhanced).")
    st.write("Use the sidebar to provide OpenAI API key to enable AI features.")

# End
