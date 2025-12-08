import streamlit as st
import requests
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(
    page_title="Mythic Art Explorer",
    page_icon="🧿",
    layout="wide"
)

client = OpenAI()

# -----------------------------
# MET API
# -----------------------------
BASE = "https://collectionapi.metmuseum.org/public/collection/v1"


def met_search(term: str):
    url = f"{BASE}/search?q={term}"
    try:
        r = requests.get(url, timeout=20)
        return r.json().get("objectIDs") or []
    except:
        return []


def get_met_object(object_id: int):
    url = f"{BASE}/objects/{object_id}"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


# -----------------------------
# GREEK MYTH TAG + MEDIUM FILTER
# -----------------------------
STRICT_MYTH_TAGS = {
    "Greek Mythology",
    "Zeus", "Hera", "Athena", "Apollo", "Artemis",
    "Aphrodite", "Hermes", "Poseidon", "Hades", "Demeter",
    "Dionysus", "Perseus", "Medusa", "Gorgon",
    "Theseus", "Heracles", "Hercules", "Achilles",
    "Narcissus", "Orpheus", "Pan"
}

CHAR_KEYWORDS = [
    "zeus", "hera", "athena", "apollo", "artemis",
    "aphrodite", "hermes", "poseidon", "medusa",
    "perseus", "heracles", "hercules", "gorgon"
]

MEDIUM_KEYWORDS = [
    "greek", "attic", "hellenistic", "roman", "classical",
    "terracotta", "vase", "krater", "amphora"
]


def passes_strict_tag_filter(meta: dict) -> bool:
    tags = meta.get("tags") or []
    for tag in tags:
        if isinstance(tag, dict) and tag.get("term") in STRICT_MYTH_TAGS:
            return True
    return False


def passes_medium_filter(meta: dict) -> bool:
    title = (meta.get("title") or "").lower()
    culture = (meta.get("culture") or "").lower()
    medium = (meta.get("medium") or "").lower()

    if any(k in title for k in CHAR_KEYWORDS):
        return True
    if "greek" in culture or "hellenistic" in culture:
        return True
    if any(k in medium for k in MEDIUM_KEYWORDS):
        return True
    return False


def is_greek_myth_artwork(meta: dict) -> bool:
    return passes_strict_tag_filter(meta) or passes_medium_filter(meta)


def search_myth_objects(object_ids):
    results = []
    for oid in object_ids:
        meta = get_met_object(oid)
        if meta and is_greek_myth_artwork(meta):
            results.append(meta)
    return results


# -----------------------------
# AI Functions
# -----------------------------
def ai_story_and_analysis(hero: str, artwork: dict):
    prompt = f"""
You are an art historian and mythologist.
Write THREE SEPARATE SECTIONS:

1. **Myth Story (120–150 words)**  
Retell a myth involving {hero}, vivid and narratively clear.

2. **Artwork Interpretation (120–160 words)**  
Analyze this MET artwork:
Title: {artwork.get('title')}
Date: {artwork.get('objectDate')}
Culture: {artwork.get('culture')}
Medium: {artwork.get('medium')}
Explain composition, symbolism, and how it relates to the myth.

3. **Museum Label (Concise, 60–80 words)**  
Write an academic-style caption suitable for museum display.

Output in English only.
"""
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"[AI Error: {e}]"


# -----------------------------
# STREAMLIT UI
# -----------------------------
st.title("🧿 Mythic Art Explorer")
st.write("Explore Greek mythology through MET Museum artworks + AI storytelling.")

st.markdown("### 1. Choose a mythic figure")
HEROES = ["Athena", "Zeus", "Apollo", "Artemis", "Aphrodite", "Hermes", "Poseidon", "Medusa", "Perseus", "Heracles"]
hero = st.selectbox("Select a figure", HEROES)

st.markdown("### 2. Fetching MET Artworks…")

query_terms = list({hero, hero.lower(), hero.upper(), f"{hero} greek", f"{hero} vase"})
object_ids_all = []

for t in query_terms:
    ids = met_search(t)
    if ids:
        object_ids_all.extend(ids)

object_ids_all = list(set(object_ids_all))

st.write(f"Found **{len(object_ids_all)}** raw results from MET API")
st.write("Filtering for Greek myth artworks…")

filtered = search_myth_objects(object_ids_all)

st.success(f"After filtering: **{len(filtered)}** valid Greek myth artworks")


# -----------------------------
# DISPLAY RESULTS
# -----------------------------
st.markdown("## 3. Artworks")

if len(filtered) == 0:
    st.error("No artworks found for this figure. Try another character.")
else:
    for art in filtered:
        col1, col2 = st.columns([1, 2])
        with col1:
            if art.get("primaryImageSmall"):
                st.image(art["primaryImageSmall"])
            else:
                st.write("No image")

        with col2:
            st.markdown(f"### {art.get('title')}")
            st.write(f"**Date:** {art.get('objectDate')}")
            st.write(f"**Culture:** {art.get('culture')}")
            st.write(f"**Medium:** {art.get('medium')}")
            st.markdown(f"[Open on MET]({art.get('objectURL')})")

        with st.expander("AI Story + Analysis"):
            analysis = ai_story_and_analysis(hero, art)
            st.write(analysis)

        st.markdown("---")

