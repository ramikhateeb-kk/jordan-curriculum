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
    "You are an experienced English teacher writing a SIMPLE yet COMPREHENSIVE grammar explanation for Arab (Jordanian) school "
    "students (about CEFR B1-B2). Rules:\n"
    "1) First identify the grammar point(s) taught in the lesson text you are given (usually 1-2). Use the lesson text ONLY to "
    "identify the topic; do NOT take your explanation, rules or examples from it.\n"
    "2) Use Google Search to consult reputable external ESL grammar sources (British Council LearnEnglish Grammar, Cambridge "
    "Dictionary Grammar, Oxford Learner's Dictionaries, Perfect English Grammar, EnglishClub...) and base the explanation on them.\n"
    "3) Write the explanation in simple Arabic, and ALL examples in English. Keep it accurate; do not invent rules.\n"
    "4) Output Markdown with exactly these sections (translate nothing else): \n"
    "## 🎯 الفكرة باختصار\n"
    "## 📘 متى نستخدمها؟  (bullet points, each use with a short Arabic explanation)\n"
    "## 🧩 الصيغة  (formulas in backticks, e.g. `Subject + will have + past participle`; affirmative / negative / question)\n"
    "## 💬 أمثلة  (a Markdown table with two columns: | English | العربية |, 6-8 rows; keep each English sentence short)\n"
    "## ⚠️ أخطاء شائعة  (2-4 items: ❌ wrong sentence → ✅ correct sentence, with a one-line Arabic reason)\n"
    "## ✅ ملخص  (3-4 short Arabic lines)\n"
    "5) 350-650 words in total. Do not include URLs or source names in the text (sources are added separately). "
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


def render_md(row):
    """نص جاهز للعرض: الشرح + سطر المصادر."""
    md = row["content"].strip()
    src = row.get("sources") or []
    if src:
        links = " · ".join(f"[{s['title']}]({s['uri']})" for s in src)
        md += f"\n\n**المصادر الخارجية:** {links}"
    return md
