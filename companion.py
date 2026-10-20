"""
companion.py
الكتاب المرافق (مثل كتاب الأنشطة Workbook) لكتاب رئيسي: كل درس في الكتاب الرئيسي يُربط بنظيره في المرافق
تلقائيًا بـ (رقم الوحدة، رقم الدرس) المأخوذين من العناوين: «Unit 02» و«Lesson 3A» ↔ «Unit 02» و«Lesson 3B».
الأحرف (A/B) تُهمَل؛ يُقارن الرقم فقط. الدرس الذي لا نظير له (مثل Reading أو Writing) يبقى بلا ربط.
الكتب التي لا تحمل عناوينها رقم وحدة/درس بهذه الصيغة لا تُربط تلقائيًا.
"""
import re

import catalog
import ingest
from rag import load_index, select_context

_UNIT_RE = re.compile(r"unit\s*0*(\d+)", re.I)
_LESSON_RE = re.compile(r"lesson\s*0*(\d+)\s*[a-z]?\b", re.I)


def _num(rx, text):
    m = rx.search(text or "")
    return int(m.group(1)) if m else None


def attach(books, book, flat_lessons, lang):
    """يضيف إلى كل درس: lang، وإن وُجد كتاب مرافق: companion_key=(grade, sem, slug) وcompanion_pages=(start, end).
    يعيد الكتاب المرافق أو None. لا يرفع استثناءً: أي فشل في تجهيز المرافق يعني ببساطة عدم وجوده."""
    for l in flat_lessons:
        l["lang"] = lang
        l["page_offset"] = book.get("page_offset", 0) or 0     # لتحويل صفحة ملف PDF إلى الصفحة المطبوعة في الكتاب
    comps = [b for b in books if b.get("parent_slug") == book["slug"]]
    if not comps:
        return None
    comp = comps[0]
    try:
        ingest.ensure_index(comp)
        idx = load_index(comp["grade"], comp["semester"], comp["slug"])
        if idx is None:
            return None
        units = catalog.compute_units(comp["units"], comp["page_offset"], idx[2].get("pages", 0))
    except Exception:  # noqa: BLE001
        return None
    table = {}
    for u in units:
        un = _num(_UNIT_RE, u["title"])
        for l in u["lessons"]:
            ln = _num(_LESSON_RE, l["title"])
            if un is not None and ln is not None:
                table[(un, ln)] = (l["start"], l["end"])
    key = (comp["grade"], comp["semester"], comp["slug"])
    for l in flat_lessons:
        k = (_num(_UNIT_RE, l.get("unit_title", "")), _num(_LESSON_RE, l["title"]))
        if None not in k and k in table:
            l["companion_key"], l["companion_pages"] = key, table[k]
    return comp


def exercises_text(lesson, max_chars=12000):
    """نص تمارين الكتاب المرافق لهذا الدرس (أو '' إن لم يوجد نظير). يُرسَل كمادة مساندة فقط."""
    key, pages = lesson.get("companion_key"), lesson.get("companion_pages")
    if not key or not pages:
        return ""
    idx = load_index(*key)
    if idx is None:
        return ""
    ctx = select_context(idx, lesson["title"], pages, max_chars=max_chars)
    from rich_text import clean_text
    return "\n\n".join(f"=== Workbook page {p['page']} ===\n{clean_text(p['text'])}" for p in ctx)
