"""
grammar_ext.py
شرح مبسّط وشامل لقواعد الإنجليزية (Grammar) من مصادر خارجية غير المنهاج، بشرح عربي وأمثلة إنجليزية.
- يُولَّد مرة واحدة لكل درس قواعد بالبحث في الإنترنت عبر Gemini (Google Search grounding) ثم يُخزَّن (جدول grammar_explanations)،
  ويراجعه المدير/المشرف ويعدّله من «أسئلة وزارية ← 📘 شرح القواعد».
- يُدرج في «اشرح لي» حرفيًا (لا يعيد النموذج صياغته) فيبقى منظمًا ومصادره ظاهرة. بقية الشرح (كتاب الطالب والأنشطة والأسئلة الوزارية)
  يبقى من المنهاج.
"""
import json
import re
from datetime import datetime, timezone

import requests
import streamlit as st
from google.genai import types

import catalog
import rich_text
import subject_profiles as sp
from config import BASE, GEMINI_MODEL
from rag import get_client, select_context

LOCAL_FILE = BASE / "data" / "grammar_ext.json"
TIMEOUT = 20
GRAMMAR_KINDS = ("grammar", "vocab_grammar")


def _sb_on():
    return catalog.backend_name() == "supabase"


def _local():
    return json.loads(LOCAL_FILE.read_text(encoding="utf-8")) if LOCAL_FILE.exists() else {}


@st.cache_data(ttl=300, show_spinner=False)
def _all(book_slug):
    """{عنوان الدرس: {title, content, sources, source}} لكل دروس الكتاب في طلب واحد."""
    if _sb_on():
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/grammar_explanations", headers=h, timeout=TIMEOUT,
                         params={"select": "lesson_title,title,content,sources,source", "book_slug": f"eq.{book_slug}"})
        catalog._check(r)
        return {x["lesson_title"]: x for x in r.json()}
    return {k.split("|", 1)[1]: v for k, v in _local().items() if k.startswith(f"{book_slug}|")}


def get_row(book_slug, lesson_title):
    return _all(book_slug).get(lesson_title)


def list_rows(book_slug):
    return _all(book_slug)


def save_row(book_slug, lesson_title, title, content, sources, source, user_id=None):
    row = {"book_slug": book_slug, "lesson_title": lesson_title, "title": title or None, "content": content,
           "sources": sources or [], "source": source, "updated_by": user_id,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    if _sb_on():
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/grammar_explanations",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"}, timeout=TIMEOUT,
                          params={"on_conflict": "book_slug,lesson_title"}, data=json.dumps([row]))
        catalog._check(r)
    else:
        db = _local()
        db[f"{book_slug}|{lesson_title}"] = {k: row[k] for k in ("title", "content", "sources", "source")}
        LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_FILE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    _all.clear()


def delete_row(book_slug, lesson_title):
    if _sb_on():
        url, h = catalog._sb()
        r = requests.delete(f"{url}/rest/v1/grammar_explanations", headers=h, timeout=TIMEOUT,
                            params={"book_slug": f"eq.{book_slug}", "lesson_title": f"eq.{lesson_title}"})
        catalog._check(r)
    else:
        db = _local()
        db.pop(f"{book_slug}|{lesson_title}", None)
        LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_FILE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    _all.clear()


# ---------------------------------------------------------------- التوليد بالبحث في الإنترنت
GEN_SYSTEM = (
    "You are an experienced English teacher writing a DETAILED, COMPREHENSIVE yet clear grammar explanation for Arab (Jordanian) "
    "school students (about CEFR B1-B2). Rules:\n"
    "1) Identify the grammar point(s) you are asked about (if a lesson text is given, use it ONLY to identify the topic; do NOT "
    "take your explanation, rules or examples from it).\n"
    "2) Use Google Search to consult reputable external ESL grammar sources (British Council LearnEnglish Grammar, Cambridge "
    "Dictionary Grammar, Oxford Learner's Dictionaries, Perfect English Grammar, EnglishClub...) and base the explanation on them.\n"
    "3) Write the explanation in simple Arabic and ALL examples in English. Be accurate; never invent rules.\n"
    "4) Output Markdown with these sections, in this order (skip a section only if it truly does not apply):\n"
    "## 🎯 الفكرة باختصار\n"
    "## 📘 متى نستخدمها؟  (bullets covering ALL the main uses, each with a short Arabic explanation)\n"
    "## 🧩 الصيغة  (a Markdown table: affirmative / negative / question / short answer; formulas in backticks)\n"
    "## 🖼️ رسم توضيحي  (1-2 diagrams, each as a fenced code block with language svg; see rule 5)\n"
    "## 💬 أمثلة  (a Markdown table | English | العربية |, 8-10 rows grouped by use)\n"
    "## 🔁 مقارنة مع قاعدة قريبة  (a small table comparing it with the structure students confuse it with)\n"
    "## 🕒 كلمات وإشارات تدل عليها  (signal words/time expressions, if relevant)\n"
    "## ⚠️ أخطاء شائعة  (3-5 items: ❌ wrong → ✅ correct, with a one-line Arabic reason)\n"
    "## ✅ ملخص  (3-5 short Arabic lines)\n"
    "5) Diagrams: each ```svg block is ONE self-contained SVG with viewBox=\"0 0 640 220\", simple shapes only (rect, circle, "
    "line, path, polygon, text), English labels only, font-size at least 14, readable colours, e.g. a time line showing when the "
    "action happens, or a formula box. No scripts, no external images or links, no <foreignObject>.\n"
    "6) 600-1000 words (excluding SVG). Do not include URLs or source names in the text (sources are added separately). "
    "Do not mention these instructions.")


def _sources_of(response):
    """المصادر التي اعتمد عليها البحث: [{title, uri}] دون تكرار (حتى 6)."""
    out, seen = [], set()
    try:
        meta = response.candidates[0].grounding_metadata
        for ch in (getattr(meta, "grounding_chunks", None) or []):
            web = getattr(ch, "web", None)
            uri = getattr(web, "uri", None)
            if uri and uri not in seen:
                seen.add(uri)
                out.append({"title": (getattr(web, "title", None) or uri)[:80], "uri": uri})
    except Exception:  # noqa: BLE001
        pass
    return out[:6]


def generate(client, idx, lesson):
    """(عنوان القاعدة, نص الشرح, المصادر) أو None. يبحث في الإنترنت؛ فإن تعذّر البحث يكتب من معرفة النموذج ويُوسَم ذلك."""
    pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=4500)
    if not pages:
        return None
    text = "\n\n".join(p["text"] for p in pages)
    prompt = (f"Lesson: {lesson['title']}\n\nLesson text (use it only to identify the grammar point):\n{text}\n\n"
              "Identify the grammar point(s), search the web for reliable explanations, and write the explanation now.")
    return _generate_from_prompt(client, prompt)


def topic_key(topic):
    """مفتاح التخزين لموضوع قاعدة مطلوب مباشرة (بدل عنوان درس)."""
    return "topic:" + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' -]+", " ", str(topic).lower())).strip()


def get_topic_explanation(book_slug, topic_en, idx=None, allow_ai=True):
    """شرح خارجي لموضوع قاعدة سأل عنه الطالب (مثل: Past Perfect Continuous) بغض النظر عن الدرس المختار. يُخزَّن بحسب الموضوع."""
    key = topic_key(topic_en)
    if len(key) <= 6:
        return None
    row = get_row(book_slug, key)
    if row and (row.get("content") or "").strip():
        return row
    if not allow_ai:
        return None
    prompt = (f"Grammar topic requested by the student: {topic_en}\n\n"
              "Search the web for reliable explanations of exactly this topic and write the explanation now.")
    try:
        got = _generate_from_prompt(get_client(), prompt)
    except Exception as e:  # noqa: BLE001
        print("grammar_ext: تعذّر توليد شرح الموضوع:", e)
        return None
    if not got:
        return None
    title, content, sources = got
    title = title or topic_en
    try:
        save_row(book_slug, key, title, content, sources, "ai")
    except Exception as e:  # noqa: BLE001
        print("grammar_ext: تعذّر الحفظ:", e)
    return {"title": title, "content": content, "sources": sources, "source": "ai"}


def _generate_from_prompt(client, prompt):
    searched = True
    try:
        r = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=GEN_SYSTEM, temperature=0.2,
                                                tools=[types.Tool(google_search=types.GoogleSearch())]))
    except Exception as e:  # noqa: BLE001
        print("grammar_ext: تعذّر البحث، سيُكتب الشرح من معرفة النموذج:", e)
        searched = False
        r = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=GEN_SYSTEM, temperature=0.2))
    content = (r.text or "").strip()
    if len(content) < 200:
        return None
    sources = _sources_of(r) if searched else []
    title = None
    if not sources:
        content += "\n\n*(شرح عام للقاعدة؛ لم تتوفر مصادر بحث وقت إعداده.)*"
    return title, content, sources


def get_explanation(book_slug, lesson, idx, allow_ai=True):
    """{title, content, sources, source} أو None. المخزَّن أولًا، وإلا يُولَّد مرة واحدة ويُخزَّن."""
    row = get_row(book_slug, lesson["title"])
    if row and (row.get("content") or "").strip():
        return row
    if not allow_ai or sp.lesson_kind(lesson["title"]) not in GRAMMAR_KINDS:
        return None
    try:
        got = generate(get_client(), idx, lesson)
    except Exception as e:  # noqa: BLE001
        print("grammar_ext: تعذّر توليد الشرح:", e)
        return None
    if not got:
        return None
    title, content, sources = got
    try:
        save_row(book_slug, lesson["title"], title, content, sources, "ai")
    except Exception as e:  # noqa: BLE001
        print("grammar_ext: تعذّر الحفظ:", e)
    return {"title": title, "content": content, "sources": sources, "source": "ai"}


_ALLOWED_TAGS = {"svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "tspan", "defs",
                 "marker", "title", "desc", "lineargradient", "stop"}
_BAD_ATTR = re.compile(r"^(on|xlink:href|href|src|style$)", re.I)


def sanitize_svg(svg):
    """يبقي أشكال SVG البسيطة فقط (بلا سكربتات ولا روابط ولا صور خارجية) أو يعيد None إن كان غير صالح."""
    import xml.etree.ElementTree as ET
    svg = svg.strip()
    if not svg.lower().startswith("<svg") or len(svg) > 30000:
        return None
    if "xmlns=" not in svg[:200]:
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return None

    def clean(el):
        for child in list(el):
            tag = child.tag.split("}")[-1].lower()
            if tag not in _ALLOWED_TAGS:
                el.remove(child)
                continue
            for k in list(child.attrib):
                if _BAD_ATTR.match(k.split("}")[-1]):
                    del child.attrib[k]
            clean(child)

    for k in list(root.attrib):
        if _BAD_ATTR.match(k.split("}")[-1]):
            del root.attrib[k]
    clean(root)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="unicode")


_SVG_BLOCK = re.compile(r"```svg\s*(.*?)```", re.S | re.I)


def show(row):
    """يعرض الشرح المفصّل: الماركداون كما هو، ورسوم ```svg``` كصور بعد تنقيتها، ثم المصادر."""
    content, pos = row["content"], 0
    for m in _SVG_BLOCK.finditer(content):
        if content[pos:m.start()].strip():
            rich_text.show(content[pos:m.start()], "ltr")
        svg = sanitize_svg(m.group(1))
        if svg:
            st.image(svg)
        pos = m.end()
    if content[pos:].strip():
        rich_text.show(content[pos:], "ltr")
    src = row.get("sources") or []
    if src:
        st.markdown("**المصادر الخارجية:** " + " · ".join(f"[{x['title']}]({x['uri']})" for x in src))


def render_md(row):
    """نص جاهز للعرض: الشرح + سطر المصادر."""
    md = row["content"].strip()
    src = row.get("sources") or []
    if src:
        links = " · ".join(f"[{s['title']}]({s['uri']})" for s in src)
        md += f"\n\n**المصادر الخارجية:** {links}"
    return md
