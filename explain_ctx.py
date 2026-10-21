"""
explain_ctx.py
مواد «اشرح لي» الإضافية لدرس/وحدة محددة: تمارين الكتاب المرافق (الأنشطة)، والأسئلة الوزارية المعتمدة على الدرس، وشرح القواعد الخارجي.
"""
import json
import re

import streamlit as st
from google.genai import types

import companion
import grammar_ext
import ministry
import subject_profiles as sp
from config import GEMINI_MODEL
from rag import get_client

WORKBOOK_MAX = 9000
MAX_LESSONS = 6
MAX_GRAMMAR = 2


def build(slug, idx, flat_lessons, scope_titles, user, lang, topic_en=None):
    """مواد «اشرح لي» من المنهاج: تمارين كتاب الأنشطة والأسئلة الوزارية المعتمدة على الدروس. (شرح القواعد الخارجي لا يُدرَج هنا؛
    يُعرض بعد الشرح من المنهاج عند طلب الطالب أو عند غياب الشرح في المنهاج.) topic_en = موضوع القاعدة المطلوبة إن وُجد."""
    lessons = [l for l in flat_lessons if l["title"] in set(scope_titles)][:MAX_LESSONS]
    extras = {"workbook": "", "ministry": "", "grammar_topic": topic_en or ""}
    if not lessons:
        return extras
    parts = []
    for l in lessons:
        t = companion.exercises_text(l, max_chars=3000)
        if t:
            parts.append(f"[{l['title']}]\n{t}")
    extras["workbook"] = "\n\n".join(parts)[:WORKBOOK_MAX]
    try:
        if ministry.is_visible(slug) or user["role"] in ("admin", "supervisor"):
            extras["ministry"] = ministry.examples_for_lessons(slug, [l["title"] for l in lessons], 6, lang)
    except Exception:  # noqa: BLE001
        pass
    return extras


def external(slug, idx, flat_lessons, followup):
    """الشرح المفصّل من مصادر خارجية لموضوع القاعدة: followup = {"kind":"topic","topic":...} أو {"kind":"lesson","lesson": عنوان}.
    يعيد {content, sources} أو None. يُخزَّن ويُعاد استعماله."""
    if followup.get("kind") == "topic":
        return grammar_ext.get_topic_explanation(slug, followup["topic"], idx)
    lesson = next((l for l in flat_lessons if l["title"] == followup.get("lesson")), None)
    return grammar_ext.get_explanation(slug, lesson, idx) if lesson else None


ROUTE_SYSTEM = (
    "You route a student's question about an English textbook (the student may write in Arabic). Return JSON only: "
    '{"keywords_en": "3-8 English keywords to find the relevant textbook pages (translate any Arabic term, e.g. '
    'الماضي التام المستمر -> past perfect continuous)", "is_grammar": true/false (the student asks about an English grammar '
    'rule, tense or structure), "topic_en": "the grammar topic name in English, e.g. Past Perfect Continuous, or null"}.')


@st.cache_data(ttl=7 * 24 * 3600, max_entries=2000, show_spinner=False)
def route(question):
    """يحلّل سؤال الطالب (عربي أو إنجليزي): كلمات بحث إنجليزية للعثور على صفحات الكتاب، وهل هو سؤال قواعد وما اسم القاعدة.
    يعيد {} عند الفشل (فيستمر النظام كما كان)."""
    try:
        r = get_client().models.generate_content(
            model=GEMINI_MODEL, contents=f"Student question:\n{question[:600]}",
            config=types.GenerateContentConfig(system_instruction=ROUTE_SYSTEM, temperature=0,
                                                response_mime_type="application/json"))
        d = json.loads(re.sub(r"^```(?:json)?|```$", "", (r.text or "").strip()).strip())
    except Exception as e:  # noqa: BLE001
        print("explain_ctx.route:", e)
        return {}
    if not isinstance(d, dict):
        return {}
    topic = d.get("topic_en")
    topic = str(topic).strip()[:80] if isinstance(topic, str) and topic.strip() and bool(d.get("is_grammar")) else None
    return {"keywords_en": str(d.get("keywords_en") or "")[:120].strip(), "is_grammar": bool(d.get("is_grammar")) and bool(topic),
            "topic_en": topic}


def lessons_for_topic(idx, flat_lessons, query, limit=2):
    """أنسب دروس الكتاب لموضوع (بالإنجليزية): عدد مرات ورود كلمات الموضوع في صفحات كل درس، مع ترجيح العنوان."""
    words = {w for w in re.findall(r"[a-z]{4,}", query.lower())}
    if not words:
        return []
    scored = []
    for l in flat_lessons:
        text = " ".join(p["text"].lower() for p in idx[0] if l["start"] <= p["page"] <= l["end"])
        score = sum(text.count(w) for w in words) + 8 * sum(w in l["title"].lower() for w in words)
        if score > 0:
            scored.append((score, l["title"]))
    return [t for _s, t in sorted(scored, key=lambda x: -x[0])[:limit]]



def find_title_pages(question, idx):
    """يعثر على الصفحات التي يظهر فيها عنوان/عبارة إنجليزية ذكرها الطالب صراحةً."""
    q = str(question or "")
    # التقط العبارة الإنجليزية بعد «نص»/«عنوان» أو داخل علامات اقتباس.
    candidates = re.findall(r"[\"'“”‘’]([^\"'“”‘’]{3,100})[\"'“”‘’]", q)
    if not candidates:
        m = re.search(r"(?:نص|عنوان|text|title)\s+(.+?)(?=\s+(?:في|صفحة|بالصفحة|page)\b|$)", q, re.I)
        if m:
            candidates = [m.group(1)]
    stop = {"they", "need", "saving", "too", "the", "text", "words", "word", "highlighted", "meaning", "معنى", "الكلمات", "المظللة"}
    # نحتفظ بعبارات إنجليزية كاملة، مع تجربة العبارة الأصلية أولاً.
    phrases = []
    for c in candidates:
        words = re.findall(r"[a-z]+", c.lower())
        if len(words) >= 2:
            phrases.append(" ".join(words))
    if not phrases:
        # عنوان معروف مذكور بلا علامات اقتباس في سؤال شائع.
        words = re.findall(r"[a-z]+", q.lower())
        for n in range(min(8, len(words)), 1, -1):
            phrase = " ".join(words[-n:])
            if phrase not in {"the student", "student book"}:
                phrases.append(phrase)
    pages = []
    for page in idx[0]:
        text = re.sub(r"[^a-z0-9]+", " ", str(page.get("text", "")).lower()).strip()
        for phrase in phrases:
            if phrase and re.sub(r"[^a-z0-9]+", " ", phrase).strip() in text:
                pages.append(int(page["page"]))
                break
    return sorted(set(pages))


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PAGE_RX = re.compile(r"(?<!\w)(?:صفحة|صفحه|الصفحة|ص|page|p)\.?\s*[:\-]?\s*(\d{1,3})(?!\d)", re.I)


def parse_page(question):
    """رقم الصفحة المطبوعة الذي ذكره الطالب («حل سؤال 5 في صفحة 30») أو None."""
    m = _PAGE_RX.search(str(question).translate(_AR_DIGITS))
    return int(m.group(1)) if m else None


def _which_books(question):
    q = str(question).lower()
    workbook = bool(re.search(r"الأنشطة|الانشطة|النشاط|workbook|activity", q))
    student = bool(re.search(r"كتاب الطالب|student", q))
    return (not workbook or student), (workbook or not student)


def asked_pages(question, idx, offset, comp_idx=None, comp_offset=0, source_mode="جميع المصادر"):
    """استرجاع الصفحة المطلوبة من مصدر الإجابة المحدد فقط، أو من المصدرين عند اختيار الجميع."""
    page = parse_page(question)
    if not page:
        return []
    from rich_text import clean_text
    use_main, use_comp = _which_books(question)
    # اختيار الواجهة هو المرجع الحاسم؛ لا يكفي ذكر كلمة "student" داخل نص السؤال لتجاوز الاختيار.
    if source_mode == "كتاب الطالب":
        use_main, use_comp = True, False
    elif source_mode == "كتاب الأنشطة":
        use_main, use_comp = False, True
    # في وضع "جميع المصادر" نراعي أيضًا إن كان الطالب قد سمّى كتابًا بعينه.
    out = []
    if use_main:
        for p in idx[0]:
            if p["page"] == page + offset:
                out.append({"source": "كتاب الطالب", "page": page, "text": clean_text(p["text"])[:4000]})
    if use_comp and comp_idx:
        for p in comp_idx[0]:
            if p["page"] == page + comp_offset:
                out.append({"source": "كتاب الأنشطة", "page": page, "text": clean_text(p["text"])[:4000]})
    return out
