"""
reading_texts.py
نص القراءة لكل درس بتنسيقه الأصلي (أسطر وفقرات الكتاب)، بلا أسطر التمارين والعناوين.
- الاستخراج: الذكاء الاصطناعي يرى أسطر صفحات الدرس مرقّمة ويُعيد أرقام الأسطر التي تكوّن النص وتقسيمها إلى فقرات؛ ويُركّب
  النظام النص من الأسطر الأصلية حرفيًا (فلا تُعاد صياغة شيء). باقي الأسطر تُحفظ كتمارين تُستعمل للاستئناس عند توليد الأسئلة.
- الحفظ: مرة واحدة لكل درس (جدول reading_texts). يعدّله المدير/المشرف يدويًا من تبويب «نصوص القراءة».
- الاستعمال: زر «عرض النص» في قيّمني، وطباعة النص كاملًا قبل أسئلته في ورقة الاختبار.
"""
import html
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

LOCAL_FILE = BASE / "data" / "reading_texts.json"
TIMEOUT = 20
EXERCISES_MAX = 4000


# ---------------------------------------------------------------- التخزين
def _sb_on():
    return catalog.backend_name() == "supabase"


def _local():
    return json.loads(LOCAL_FILE.read_text(encoding="utf-8")) if LOCAL_FILE.exists() else {}


@st.cache_data(ttl=300, show_spinner=False)
def _row(book_slug, lesson_title):
    if _sb_on():
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/reading_texts", headers=h, timeout=TIMEOUT,
                         params={"select": "title,text,exercises,source", "book_slug": f"eq.{book_slug}",
                                 "lesson_title": f"eq.{lesson_title}"})
        catalog._check(r)
        rows = r.json()
        return rows[0] if rows else None
    return _local().get(f"{book_slug}|{lesson_title}")


@st.cache_data(ttl=120, show_spinner=False)
def list_rows(book_slug):
    """كل نصوص كتاب في طلب واحد: {عنوان الدرس: {title, source, words}} (لعرض الحالة دون استعلام لكل درس)."""
    if _sb_on():
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/reading_texts", headers=h, timeout=TIMEOUT,
                         params={"select": "lesson_title,title,text,source", "book_slug": f"eq.{book_slug}"})
        catalog._check(r)
        rows = {x["lesson_title"]: x for x in r.json()}
    else:
        rows = {k.split("|", 1)[1]: v for k, v in _local().items() if k.startswith(f"{book_slug}|")}
    return {t: {"title": v.get("title"), "source": v.get("source"), "words": len(str(v.get("text") or "").split())}
            for t, v in rows.items()}


def delete_row(book_slug, lesson_title):
    if _sb_on():
        url, h = catalog._sb()
        r = requests.delete(f"{url}/rest/v1/reading_texts", headers=h, timeout=TIMEOUT,
                            params={"book_slug": f"eq.{book_slug}", "lesson_title": f"eq.{lesson_title}"})
        catalog._check(r)
    else:
        db = _local()
        db.pop(f"{book_slug}|{lesson_title}", None)
        LOCAL_FILE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    _row.clear()
    list_rows.clear()


def save_row(book_slug, lesson_title, title, text, exercises, source, user_id=None):
    row = {"book_slug": book_slug, "lesson_title": lesson_title, "title": title or None, "text": text,
           "exercises": (exercises or "")[:EXERCISES_MAX] or None, "source": source, "updated_by": user_id,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    if _sb_on():
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/reading_texts",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"}, timeout=TIMEOUT,
                          params={"on_conflict": "book_slug,lesson_title"}, data=json.dumps([row]))
        catalog._check(r)
    else:
        db = _local()
        db[f"{book_slug}|{lesson_title}"] = {k: row[k] for k in ("title", "text", "exercises", "source")}
        LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_FILE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    _row.clear()
    list_rows.clear()


# ---------------------------------------------------------------- الاستخراج بالذكاء الاصطناعي
EXTRACT_SYSTEM = (
    "You separate the READING TEXT of a textbook lesson from its exercises. You are given the lines of the lesson pages in order, "
    "each as: n<TAB>printed page<TAB>line text. Identify the reading text(s) the student reads: the article, extract, story, "
    "dialogue, letter or poem. Rules:\n"
    "1) Return ONLY line numbers (n). Never rewrite or invent text.\n"
    "2) Include ONLY lines that belong to the reading text itself. Exclude: lesson/section headings (LESSON ..., SPEAKING, "
    "CRITICAL THINKING, ACTIVE READING, VALUES), exercise numbers and instructions, questions, answer options, glossary entries, "
    "notes boxes, captions, page headers, and any other exercise material.\n"
    "3) paragraphs = list of paragraphs; each paragraph is a list of consecutive line numbers in the original order. Start a "
    "new paragraph where the text starts one (indented first line, previous line ended a sentence and was short, "
    "a new speaker, or a stanza break in a poem). In poems keep one line per line number.\n"
    "4) title = the heading of the text if the text has its own printed title, else null.\n"
    "5) If the lesson has no reading text, return {\"texts\": []}.\n"
    'Return JSON only: {"texts":[{"title":null,"paragraphs":[[3,4,5],[6,7]]}]}')


def _ask_json(client, system, prompt):
    for _ in range(2):
        try:
            r = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0,
                                                    response_mime_type="application/json"))
            return json.loads(re.sub(r"^```(?:json)?|```$", "", r.text.strip()).strip())
        except Exception as e:  # noqa: BLE001
            print("reading_texts: خطأ JSON:", e)
    return None


def extract_with_ai(client, idx, lesson):
    """(title, text, exercises) أو None. النص مركَّب من الأسطر الأصلية كما هي (أسطر وفقرات الكتاب)."""
    off = int(lesson.get("page_offset") or 0)
    pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=200000)
    lines = []
    for p in pages:
        for raw in p["text"].splitlines():
            s = raw.strip()
            if not s or re.fullmatch(r"\d{1,3}", s) or "قيد الإعداد" in s:        # أرقام الأسطر الهامشية وعلامة المسودة
                continue
            lines.append((len(lines) + 1, p["page"] - off, sp.fix_ligatures(s)))
    if len(lines) < 5:
        return None
    listing = "\n".join(f"{n}\t{pg}\t{t}" for n, pg, t in lines)
    data = _ask_json(client, EXTRACT_SYSTEM, f"Lesson: {lesson['title']}\n\nLines:\n{listing}")
    texts = data.get("texts") if isinstance(data, dict) else None
    if not texts:
        return None
    by_n = {n: t for n, _pg, t in lines}
    used, blocks, title = set(), [], None
    for t in texts:
        if not isinstance(t, dict):
            continue
        title = title or (str(t.get("title") or "").strip() or None)
        for para in t.get("paragraphs") or []:
            nums = [n for n in para if isinstance(n, int) and n in by_n and n not in used]
            if nums:
                used.update(nums)
                blocks.append("\n".join(by_n[n] for n in sorted(nums)))
    if not blocks:
        return None
    rest = "\n".join(t for n, _pg, t in lines if n not in used)
    return title, "\n\n".join(blocks), rest[:EXERCISES_MAX]


def get_text(book_slug, lesson, idx, allow_ai=True):
    """{"title","text","exercises","source"} أو None. محفوظ ← استخراج بالذكاء الاصطناعي (يُحفظ) ← استخراج تقريبي بلا ذكاء."""
    row = _row(book_slug, lesson["title"])
    if row and row.get("text"):
        return row
    if allow_ai:
        try:
            got = extract_with_ai(get_client(), idx, lesson)
        except Exception as e:  # noqa: BLE001
            print("reading_texts: تعذّر الاستخراج:", e)
            got = None
        if got:
            title, text, exercises = got
            try:
                save_row(book_slug, lesson["title"], title, text, exercises, "ai")
            except Exception as e:  # noqa: BLE001
                print("reading_texts: تعذّر الحفظ:", e)
            return {"title": title, "text": text, "exercises": exercises, "source": "ai"}
    text = sp.full_reading_text(idx, lesson)
    return {"title": None, "text": text, "exercises": None, "source": "heuristic"} if text else None


# ---------------------------------------------------------------- العرض
def show(row, lang="en"):
    """يعرض النص بأسطره وفقراته كما في الكتاب."""
    d, a = ("ltr", "left") if lang == "en" else ("rtl", "right")
    body = "".join(f"<p style='margin:0 0 .9em 0'>{html.escape(b).replace(chr(10), '<br>')}</p>"
                   for b in str(row["text"]).split("\n\n"))
    head = f"<p style='font-weight:700;margin:0 0 .6em 0'>{html.escape(row['title'])}</p>" if row.get("title") else ""
    st.markdown(f"<div dir='{d}' style='text-align:{a}'>{head}{body}</div>", unsafe_allow_html=True)
