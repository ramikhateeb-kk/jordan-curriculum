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
import uuid
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


def _check(r):
    """يحوّل خطأ مخطط قاعدة البيانات القديم إلى رسالة واضحة تدلّ على الحل."""
    try:
        catalog._check(r)
    except RuntimeError as e:
        m = str(e)
        if any(x in m for x in ("text_key", "position", "42703", "42P10", "23502", "no unique or exclusion")):
            raise RuntimeError("جدول reading_texts في Supabase غير محدَّث لهذا الإصدار: شغّل ملف supabase_materials_4.sql "
                               "مرة واحدة ثم أعد المحاولة. (" + m[:140] + ")") from e
        raise


# ---------------------------------------------------------------- التخزين (أكثر من نص لكل درس)
EX_KEY = "_ex"        # صف خاص بتمارين الدرس


def _sb_on():
    return catalog.backend_name() == "supabase"


def _local():
    """{book|lesson: [صفوف]} — ويحوّل الصيغة القديمة (صف واحد لكل درس) تلقائيًا."""
    db = json.loads(LOCAL_FILE.read_text(encoding="utf-8")) if LOCAL_FILE.exists() else {}
    for k, v in list(db.items()):
        if isinstance(v, dict):
            db[k] = [{"key": "t1", "position": 0, "title": v.get("title"), "text": v.get("text") or "",
                      "exercises": v.get("exercises"), "source": v.get("source") or "manual"}]
    return db


def _local_save(db):
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")


@st.cache_data(ttl=120, show_spinner=False)
def _all(book_slug):
    """كل صفوف كتاب في طلب واحد: {عنوان الدرس: [صفوف مرتبة]}."""
    if _sb_on():
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/reading_texts", headers=h, timeout=TIMEOUT,
                         params={"select": "lesson_title,text_key,position,title,text,exercises,source",
                                 "book_slug": f"eq.{book_slug}", "order": "position.asc,id.asc"})
        _check(r)
        out = {}
        for x in r.json():
            out.setdefault(x["lesson_title"], []).append(
                {"key": x["text_key"], "position": x["position"], "title": x["title"], "text": x["text"] or "",
                 "exercises": x.get("exercises"), "source": x["source"]})
        return out
    return {k.split("|", 1)[1]: sorted(v, key=lambda r: (r.get("position", 0), r["key"]))
            for k, v in _local().items() if k.startswith(f"{book_slug}|")}


def _clear():
    _all.clear()
    list_rows.clear()


def texts_of(book_slug, lesson_title):
    """نصوص الدرس بترتيبها: [{key, title, text, source, position}] (تمارين الدرس لا تُحسب نصًا)."""
    return [r for r in _all(book_slug).get(lesson_title, []) if r["key"] != EX_KEY and (r.get("text") or "").strip()]


def exercises_of(book_slug, lesson_title):
    rows = _all(book_slug).get(lesson_title, [])
    for r in rows:
        if r["key"] == EX_KEY:
            return r.get("text") or ""
    return next((r["exercises"] for r in rows if r.get("exercises")), "") or ""


def _upsert(book_slug, lesson_title, key, position, title, text, source, user_id, exercises=None):
    row = {"book_slug": book_slug, "lesson_title": lesson_title, "text_key": key, "position": position,
           "title": title or None, "text": text, "exercises": exercises, "source": source, "updated_by": user_id,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    if _sb_on():
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/reading_texts",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"}, timeout=TIMEOUT,
                          params={"on_conflict": "book_slug,lesson_title,text_key"}, data=json.dumps([row]))
        _check(r)
    else:
        db = _local()
        rows = [x for x in db.get(f"{book_slug}|{lesson_title}", []) if x["key"] != key]
        rows.append({"key": key, "position": position, "title": row["title"], "text": text, "exercises": exercises,
                     "source": source})
        db[f"{book_slug}|{lesson_title}"] = rows
        _local_save(db)


def save_text(book_slug, lesson_title, key, title, text, source, user_id=None):
    """يحفظ نصًا في الدرس. key=None ← نص جديد يُضاف في آخر النصوص. يعيد مفتاح النص."""
    existing = [r for r in _all(book_slug).get(lesson_title, []) if r["key"] != EX_KEY]
    old = next((r for r in existing if r["key"] == key), None) if key else None
    key = key or "t" + uuid.uuid4().hex[:6]
    position = old["position"] if old else (max([r["position"] for r in existing], default=-1) + 1)
    _upsert(book_slug, lesson_title, key, position, title, text, source, user_id)
    _clear()
    return key


def save_exercises(book_slug, lesson_title, exercises, user_id=None):
    exercises = (exercises or "").strip()[:EXERCISES_MAX]
    if exercises:
        _upsert(book_slug, lesson_title, EX_KEY, 9999, None, exercises, "manual", user_id)
    else:
        delete_text(book_slug, lesson_title, EX_KEY)
    _clear()


def delete_text(book_slug, lesson_title, key):
    if _sb_on():
        url, h = catalog._sb()
        r = requests.delete(f"{url}/rest/v1/reading_texts", headers=h, timeout=TIMEOUT,
                            params={"book_slug": f"eq.{book_slug}", "lesson_title": f"eq.{lesson_title}",
                                    "text_key": f"eq.{key}"})
        _check(r)
    else:
        db = _local()
        k = f"{book_slug}|{lesson_title}"
        db[k] = [x for x in db.get(k, []) if x["key"] != key]
        if not db[k]:
            db.pop(k)
        _local_save(db)
    _clear()


def delete_lesson(book_slug, lesson_title):
    """يحذف كل نصوص الدرس وتمارينه."""
    for r in list(_all(book_slug).get(lesson_title, [])):
        delete_text(book_slug, lesson_title, r["key"])


def replace_lesson(book_slug, lesson_title, texts, exercises, source, user_id=None):
    """ترحيل نتيجة الاستخراج الآلي: يستبدل كل نصوص الدرس بالمستخرَجة [{title, text}]."""
    delete_lesson(book_slug, lesson_title)
    for t in texts:
        save_text(book_slug, lesson_title, None, t.get("title"), t["text"], source, user_id)
    if exercises:
        save_exercises(book_slug, lesson_title, exercises, user_id)


@st.cache_data(ttl=120, show_spinner=False)
def list_rows(book_slug):
    """حالة كل دروس الكتاب: {عنوان الدرس: {count, words, source}} (لعرضها دون استعلام لكل درس)."""
    out = {}
    for lt, rows in _all(book_slug).items():
        ts = [r for r in rows if r["key"] != EX_KEY and (r.get("text") or "").strip()]
        if ts:
            out[lt] = {"count": len(ts), "words": sum(len(r["text"].split()) for r in ts),
                       "source": "manual" if any(r["source"] == "manual" for r in ts) else "ai"}
    return out


def display_title(lesson, row, rows):
    """اسم النص كما يظهر للطالب: عنوانه إن كُتب، وإلا اسم الدرس (مع رقم إن كان في الدرس أكثر من نص)."""
    if row.get("title"):
        return row["title"]
    base = sp.text_title(lesson["title"])
    if len(rows) > 1:
        n = next((i for i, r in enumerate(rows, start=1) if r["key"] == row["key"]), 1)
        return f"{base} ({n})"
    return base


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
    """(نصوص, تمارين) أو None. نصوص = [{title, text}] واحد لكل نص مستقل في الدرس، مركَّبة من الأسطر الأصلية حرفيًا."""
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
    found = data.get("texts") if isinstance(data, dict) else None
    if not found:
        return None
    by_n = {n: t for n, _pg, t in lines}
    used, texts = set(), []
    for t in found:                                    # كل عنصر = نص مستقل (موضوع مختلف)
        if not isinstance(t, dict):
            continue
        blocks = []
        for para in t.get("paragraphs") or []:
            nums = [n for n in para if isinstance(n, int) and n in by_n and n not in used]
            if nums:
                used.update(nums)
                blocks.append("\n".join(by_n[n] for n in sorted(nums)))
        if blocks:
            texts.append({"title": str(t.get("title") or "").strip() or None, "text": "\n\n".join(blocks)})
    if not texts:
        return None
    rest = "\n".join(t for n, _pg, t in lines if n not in used)
    return texts, rest[:EXERCISES_MAX]


def get_texts(book_slug, lesson, idx, allow_ai=True):
    """نصوص الدرس: [{key,title,text,source}]. محفوظة ← استخراج بالذكاء الاصطناعي (يُحفظ) ← استخراج تقريبي بلا ذكاء."""
    rows = texts_of(book_slug, lesson["title"])
    if rows:
        return rows
    if allow_ai:
        try:
            got = extract_with_ai(get_client(), idx, lesson)
        except Exception as e:  # noqa: BLE001
            print("reading_texts: تعذّر الاستخراج:", e)
            got = None
        if got:
            try:
                replace_lesson(book_slug, lesson["title"], got[0], got[1], "ai")
                rows = texts_of(book_slug, lesson["title"])
            except Exception as e:  # noqa: BLE001
                print("reading_texts: تعذّر الحفظ:", e)
            if rows:
                return rows
            return [{"key": f"a{i}", "title": t["title"], "text": t["text"], "source": "ai", "position": i}
                    for i, t in enumerate(got[0])]
    text = sp.full_reading_text(idx, lesson)
    return [{"key": "h1", "title": None, "text": text, "source": "heuristic", "position": 0}] if text else []


def get_text(book_slug, lesson, idx, allow_ai=True):
    """توافقًا مع الاستدعاءات القديمة: أول نص في الدرس مع تمارينه."""
    rows = get_texts(book_slug, lesson, idx, allow_ai)
    if not rows:
        return None
    return {**rows[0], "exercises": exercises_of(book_slug, lesson["title"])}


# ---------------------------------------------------------------- العرض
def show(row, lang=None):
    """يعرض النص بأسطره وفقراته كما في الكتاب. اتجاه كل فقرة تلقائي: الإنجليزية من اليسار لليمين والعربية من اليمين لليسار."""
    body = "".join(f"<p dir='auto' style='margin:0 0 .9em 0;text-align:start'>{html.escape(b).replace(chr(10), '<br>')}</p>"
                   for b in str(row["text"]).split("\n\n"))
    head = (f"<p dir='auto' style='font-weight:700;margin:0 0 .6em 0;text-align:start'>{html.escape(row['title'])}</p>"
            if row.get("title") else "")
    st.markdown(f"<div>{head}{body}</div>", unsafe_allow_html=True)


def input_direction_css(lang):
    """حقول إدخال النصوص (التي تبدأ تسميتها بـ 📄): اتجاه الكتاب الافتراضي، وكل فقرة تتبع لغتها تلقائيًا."""
    d, a = ("ltr", "left") if lang == "en" else ("rtl", "right")
    st.markdown(
        "<style>textarea[aria-label^='📄'], input[aria-label^='📄']"
        f"{{direction:{d};text-align:{a};unicode-bidi:plaintext;}}</style>", unsafe_allow_html=True)
