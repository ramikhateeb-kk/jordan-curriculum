"""
ministry.py
بنك «الأسئلة الوزارية السابقة» لكل كتاب:
  1) الرفع والاستخراج: يرفع المدير/المشرف ملفات امتحانات سابقة (TXT / Word / PDF / صور)؛ يقرأها الذكاء الاصطناعي ويحوّلها
     إلى أسئلة منظَّمة بنصها الأصلي دون تعديل، ويقترح الدرس المرتبط بكل سؤال. تُحفظ مسوّدات (draft).
  2) المراجعة: المدير والمشرف فقط يعدّلون كل سؤال ثم يعتمدونه (approved) أو يرفضونه. لا يظهر شيء قبل الاعتماد.
  3) العرض: الأسئلة المعتمدة تُعرض للمعلم والطالب كبنك قابل للتصفح، ويتحكم المدير بإتاحته أو إخفائه لكل كتاب.
  4) النمط: من الأسئلة المعتمدة يُستنتج ملخّص نمط الأسئلة الوزارية (أنواعها وصياغتها وعلاماتها)، وتُستخدم أمثلة منها
     عند توليد أسئلة جديدة (قيّمني/إنشاء اختبار) لتأتي بالنمط نفسه، مع منع نسخ الأسئلة الأصلية حرفيًا.
التخزين: Supabase إن وُجدت مفاتيحه (supabase_materials.sql)، وإلا ملف محلي مؤقت data/ministry.json.
"""
import difflib
import html
import io
import json
import random
import re
from datetime import datetime, timezone

import requests
import streamlit as st
from google.genai import types
from PIL import Image

import accounts as acc
import auth_ui
import catalog
import images
import qbank
from config import BASE, GEMINI_MODEL
from rag import _norm, get_client

LOCAL_FILE = BASE / "data" / "ministry.json"
TIMEOUT = 20
QTYPES = ("mcq", "tf", "fill", "short", "essay", "matching", "other")
QTYPE_AR = {"mcq": "اختيار من متعدد", "tf": "صح أو خطأ", "fill": "أكمل الفراغ", "short": "سؤال قصير",
            "essay": "مقالي/كتابة", "matching": "مطابقة", "other": "أخرى"}
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_PDF_IMAGE_PAGES = 15
TEXT_CHUNK = 9000
PAGE_SIZE = 15
REVIEW_BATCH = 8
SIMILAR_RATIO = 0.88
MIN_FOR_STYLE = 5


def _now():
    return datetime.now(timezone.utc).isoformat()


# ================================================================ التخزين
def _sb_on():
    return catalog.backend_name() == "supabase"


def _req(method, table, params=None, rows=None, rep=False):
    url, h = catalog._sb()
    headers = {**h, "Prefer": ("return=representation" if rep else "return=minimal")}
    if method == "UPSERT":
        method = "POST"
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    r = requests.request(method, f"{url}/rest/v1/{table}", headers=headers, params=params,
                         data=json.dumps(rows) if rows is not None else None, timeout=TIMEOUT)
    catalog._check(r)
    return r.json() if rep and r.text else None


def _get(table, params):
    url, h = catalog._sb()
    r = requests.get(f"{url}/rest/v1/{table}", headers=h, params=params, timeout=TIMEOUT)
    catalog._check(r)
    return r.json()


def _local():
    if LOCAL_FILE.exists():
        return json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
    return {"exams": [], "questions": [], "style": {}, "settings": {}, "seq": {"exams": 0, "questions": 0}}


def _local_save(db):
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")


def add_exam(book_slug, year, session, title, user_id):
    row = {"book_slug": book_slug, "year": year, "session": session or None, "title": title or None,
           "created_by": user_id}
    if _sb_on():
        return _req("POST", "ministry_exams", rows=[row], rep=True)[0]["id"]
    db = _local()
    db["seq"]["exams"] += 1
    db["exams"].append({**row, "id": db["seq"]["exams"]})
    _local_save(db)
    return db["seq"]["exams"]


def list_exams(book_slug):
    if _sb_on():
        return _get("ministry_exams", {"select": "*", "book_slug": f"eq.{book_slug}", "order": "year.desc.nullslast,id.desc"})
    return sorted([e for e in _local()["exams"] if e["book_slug"] == book_slug],
                  key=lambda e: (-(e.get("year") or 0), -e["id"]))


def delete_exam(exam_id):
    if _sb_on():
        _req("DELETE", "ministry_exams", params={"id": f"eq.{exam_id}"})   # الأسئلة تُحذف تلقائيًا (cascade)
    else:
        db = _local()
        db["exams"] = [e for e in db["exams"] if e["id"] != exam_id]
        db["questions"] = [q for q in db["questions"] if q["exam_id"] != exam_id]
        _local_save(db)


def add_questions(exam_id, book_slug, items):
    """items: [{number, qtype, data, lesson_title}] — تُحفظ كمسوّدات."""
    rows = [{"exam_id": exam_id, "book_slug": book_slug, "number": it.get("number"), "qtype": it["qtype"],
             "data": it["data"], "lesson_title": it.get("lesson_title"), "status": "draft"} for it in items]
    if not rows:
        return
    if _sb_on():
        _req("POST", "ministry_questions", rows=rows)
        return
    db = _local()
    for r in rows:
        db["seq"]["questions"] += 1
        db["questions"].append({**r, "id": db["seq"]["questions"]})
    _local_save(db)


def list_questions(book_slug, status=None, exam_id=None):
    if _sb_on():
        p = {"select": "id,exam_id,number,qtype,data,lesson_title,status,qbank_id,transferred_at", "book_slug": f"eq.{book_slug}",
             "order": "exam_id.desc,number.asc.nullslast,id.asc"}
        if status:
            p["status"] = f"eq.{status}"
        if exam_id:
            p["exam_id"] = f"eq.{exam_id}"
        return _get("ministry_questions", p)
    rows = [q for q in _local()["questions"] if q["book_slug"] == book_slug
            and (not status or q["status"] == status) and (not exam_id or q["exam_id"] == exam_id)]
    return sorted(rows, key=lambda q: (-q["exam_id"], q.get("number") or 10**6, q["id"]))


def update_question(qid, patch):
    if _sb_on():
        _req("PATCH", "ministry_questions", params={"id": f"eq.{qid}"}, rows=patch)
        return
    db = _local()
    for q in db["questions"]:
        if q["id"] == qid:
            q.update(patch)
    _local_save(db)


def is_visible(book_slug):
    if _sb_on():
        rows = _get("ministry_settings", {"select": "visible", "book_slug": f"eq.{book_slug}"})
        return bool(rows and rows[0]["visible"])
    return bool(_local()["settings"].get(book_slug))


def set_visible(book_slug, flag):
    if _sb_on():
        _req("UPSERT", "ministry_settings", params={"on_conflict": "book_slug"},
             rows=[{"book_slug": book_slug, "visible": bool(flag)}])
        return
    db = _local()
    db["settings"][book_slug] = bool(flag)
    _local_save(db)


def get_style(book_slug):
    """يعيد (ملف النمط, عدد الأسئلة التي بُني عليها) أو None."""
    if _sb_on():
        rows = _get("ministry_style", {"select": "data,based_on", "book_slug": f"eq.{book_slug}"})
        return (rows[0]["data"], rows[0]["based_on"]) if rows else None
    s = _local()["style"].get(book_slug)
    return (s["data"], s["based_on"]) if s else None


def save_style(book_slug, data, based_on):
    if _sb_on():
        _req("UPSERT", "ministry_style", params={"on_conflict": "book_slug"},
             rows=[{"book_slug": book_slug, "data": data, "based_on": based_on, "updated_at": _now()}])
        return
    db = _local()
    db["style"][book_slug] = {"data": data, "based_on": based_on}
    _local_save(db)


@st.cache_data(ttl=300, show_spinner=False)
def _approved_cached(book_slug):
    return list_questions(book_slug, status="approved")


@st.cache_data(ttl=300, show_spinner=False)
def _style_cached(book_slug):
    return get_style(book_slug)


def _clear_caches():
    _approved_cached.clear()
    _style_cached.clear()


# ================================================================ قراءة الملفات
def _chunk(text, n=TEXT_CHUNK):
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        if cur and len(cur) + len(line) > n:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out


def read_sources(f):
    """ملف مرفوع → قائمة وحدات [(نص, صورة PIL أو None)] كل وحدة تُرسَل في طلب واحد."""
    name = (f.name or "").lower()
    data = f.getvalue()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"«{f.name}»: الحجم يتجاوز {MAX_FILE_BYTES // (1024 * 1024)}MB.")
    if name.endswith(".txt"):
        for enc in ("utf-8-sig", "utf-8", "cp1256"):
            try:
                return [(c, None) for c in _chunk(data.decode(enc))]
            except UnicodeDecodeError:
                continue
        raise ValueError(f"«{f.name}»: تعذّر قراءة ترميز الملف النصي.")
    if name.endswith(".docx"):
        from docx import Document
        d = Document(io.BytesIO(data))
        if d.inline_shapes:
            st.warning(f"«{f.name}»: الصور داخل ملفات Word لا تُستخرج تلقائيًا. صدّر الصفحات كـ PDF أو صور لتُقتطع الأشكال، "
                       "أو أضف الصورة يدويًا أثناء المراجعة.")
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return [(c, None) for c in _chunk("\n".join(parts))]
    if name.endswith(".pdf"):
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        units, buf, n_img, skipped = [], [], 0, False

        def flush():
            if "".join(buf).strip():
                units.extend((c, None) for c in _chunk("\n\n".join(buf)))
            buf.clear()

        for pg in doc:
            text = pg.get_text()
            try:
                area = pg.rect.width * pg.rect.height
                big_img = any((b[2] - b[0]) * (b[3] - b[1]) > 0.04 * area for b in
                              (i["bbox"] for i in pg.get_image_info()))
                has_fig = big_img or len(pg.get_drawings()) > 25
            except Exception:  # noqa: BLE001
                has_fig = False
            if has_fig or len(text.strip()) < 150:     # صفحة فيها شكل أو ممسوحة ضوئيًا: تُقرأ كصورة لاقتطاع الأشكال
                flush()
                if n_img >= MAX_PDF_IMAGE_PAGES:
                    skipped = True
                    continue
                pix = pg.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
                units.append(("", Image.open(io.BytesIO(pix.tobytes("png")))))
                n_img += 1
            else:
                buf.append(text)
        flush()
        if skipped:
            st.warning(f"«{f.name}»: قُرئت أول {MAX_PDF_IMAGE_PAGES} صفحة تحوي أشكالًا أو ممسوحة ضوئيًا فقط. ارفع الباقي في ملف آخر.")
        return units
    return [("", Image.open(io.BytesIO(data)))]


# ================================================================ الاستخراج بالذكاء الاصطناعي
def _ask_json(client, system, contents, temperature=0):
    for _ in range(2):
        try:
            r = client.models.generate_content(
                model=GEMINI_MODEL, contents=contents,
                config=types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                                    response_mime_type="application/json"))
            return json.loads(re.sub(r"^```(?:json)?|```$", "", r.text.strip()).strip())
        except Exception as e:  # noqa: BLE001
            print("ministry: خطأ JSON:", e)
    return None


EXTRACT_SYSTEM = (
    "أنت مساعد يستخرج الأسئلة من امتحان وزاري سابق (نص أو صورة) إلى JSON منظَّم. التزم بصرامة:\n"
    "1) انسخ نص كل سؤال وخياراته بلغته الأصلية (عربي أو إنجليزي) كما هو حرفيًا، دون ترجمة أو تصحيح أو إعادة صياغة، "
    "ولا تضف سؤالًا أو خيارًا أو إجابة من عندك.\n"
    "2) type: mcq (له خيارات)، tf (صح/خطأ أو True/False)، fill (فراغ؛ اكتب الفراغ ______)، short (إجابة قصيرة)، "
    "essay (كتابة مطوّلة أو فقرة أو مقال)، matching (مطابقة بين عمودين)، other (أي شيء آخر؛ ضع نصه كاملًا في question).\n"
    "3) options بلا حروف الترقيم (أ، ب، A، B). ضع الإجابة الصحيحة فقط إذا كانت معلَّمة صراحةً في المدخل، وإلا null.\n"
    "4) section: عنوان السؤال الرئيسي/القسم كما ورد (مثل «السؤال الأول» أو Section A)، instruction: تعليمات القسم كما وردت، "
    "marks: علامة السؤال رقمًا إن ظهرت وإلا null، number: رقمه المطبوع إن ظهر وإلا null.\n"
    "5) تجاهل الترويسات والمعلومات الإدارية.\n"
    "6) إذا كان السؤال يعتمد على شكل أو رسم أو صورة أو جدول أو مخطط ظاهر في الصورة المرفقة، فأعد figure_box = "
    "[ymin, xmin, ymax, xmax] بإحداثيات من 0 إلى 1000 تحيط بالشكل وحده دون نص السؤال أو خياراته، وإلا null. "
    "الشكل المشترك بين عدة أسئلة يُعاد بالإحداثيات نفسها لكل منها. لا تخترع شكلًا غير موجود.\n"
    "أعد JSON فقط بلا أي نص آخر."
)
EXTRACT_SCHEMA = (
    '[{"type":"mcq","question":"...","options":["...","...","...","..."],"correct_index":null,"correct":null,'
    '"model_answer":null,"section":"...","instruction":"...","marks":null,"number":1,"figure_box":null}]'
)


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def clean_item(it):
    """يفحص بنية السؤال المستخرج محليًا ويعيد {number, qtype, data} أو None."""
    if not isinstance(it, dict):
        return None
    text = str(it.get("question") or "").strip()
    if not text:
        return None
    qt = it.get("type") if it.get("type") in QTYPES else "other"
    d = {"type": qt, "question": text, "section": str(it.get("section") or "").strip() or None,
         "instruction": str(it.get("instruction") or "").strip() or None, "marks": _num(it.get("marks"))}
    if qt == "mcq":
        opts = [str(o).strip() for o in (it.get("options") or []) if str(o).strip()]
        if len(opts) < 2:
            qt, d["type"] = "other", "other"
        else:
            d["options"] = opts
            ci = it.get("correct_index")
            d["correct_index"] = ci if isinstance(ci, int) and not isinstance(ci, bool) and 0 <= ci < len(opts) else None
    if qt == "tf":
        c = it.get("correct")
        d["correct"] = c if isinstance(c, bool) else None
    if qt == "fill":
        d["question"] = re.sub(r"_{2,}|\.{4,}|…+", "______", text)
    if qt in ("fill", "short", "essay", "other", "matching"):
        ma = str(it.get("model_answer") or "").strip()
        d["model_answer"] = ma or None
    n = _num(it.get("number"))
    return {"number": int(n) if n is not None else None, "qtype": qt, "data": d, "box": it.get("figure_box")}


def extract(client, text, image):
    prompt = (f"استخرج كل الأسئلة من المدخل التالي بهذا الشكل بالضبط:\n{EXTRACT_SCHEMA}\n\n"
              f"المدخل:\n{text or '(الأسئلة في الصورة المرفقة)'}")
    data = _ask_json(client, EXTRACT_SYSTEM, [image, prompt] if image is not None else prompt)
    got = [x for x in (clean_item(i) for i in (data if isinstance(data, list) else [])) if x]
    if image is not None:                      # اقتطاع الأشكال من الصورة الأصلية وحفظها
        cache = {}
        for it in got:
            box = it.pop("box", None)
            if not box:
                continue
            key = tuple(round(float(v) / 20) for v in box) if isinstance(box, (list, tuple)) and len(box) == 4 else None
            if key is None:
                continue
            if key not in cache:
                crop = images.crop_box(image, box)
                cache[key] = images.save(*images.prepare(crop)) if crop is not None else None
            if cache[key]:
                it["data"]["image_id"] = cache[key]
    else:
        for it in got:
            it.pop("box", None)
    return got


def tag_lessons(client, items, flat_lessons, user=None):
    """يقترح الدرس المرتبط بكل سؤال (طلب واحد لكل 40 سؤالًا). الفشل لا يوقف شيئًا: يبقى الدرس فارغًا."""
    if not flat_lessons or not items:
        return
    lessons = [{"n": i, "title": l["title"]} for i, l in enumerate(flat_lessons)]
    for s in range(0, len(items), 40):
        chunk = items[s:s + 40]
        if user is not None:
            auth_ui.require_quota_or_stop(user)
        qs = [{"i": i, "q": it["data"]["question"][:300]} for i, it in enumerate(chunk)]
        prompt = (f"الدروس:\n{json.dumps(lessons, ensure_ascii=False)}\n\nالأسئلة:\n{json.dumps(qs, ensure_ascii=False)}\n\n"
                  'لكل سؤال اختر رقم الدرس الأنسب (n) أو null إن لم يتضح. أعد JSON: [{"i":0,"n":3}]')
        data = _ask_json(client, "أنت تربط أسئلة امتحان بدروس كتاب مدرسي. أعد JSON فقط.", prompt)
        for v in (data if isinstance(data, list) else []):
            if isinstance(v, dict) and isinstance(v.get("i"), int) and 0 <= v["i"] < len(chunk):
                n = v.get("n")
                if isinstance(n, int) and not isinstance(n, bool) and 0 <= n < len(flat_lessons):
                    chunk[v["i"]]["lesson_title"] = flat_lessons[n]["title"]


# ================================================================ نمط الأسئلة
def build_style(client, approved, lang):
    """ملخّص نمط الأسئلة الوزارية من الأسئلة المعتمدة. يعيد dict أو None."""
    sample = approved if len(approved) <= 80 else random.sample(approved, 80)
    compact = []
    for r in sample:
        d = r["data"]
        compact.append({"type": d.get("type"), "section": d.get("section"), "instruction": d.get("instruction"),
                        "marks": d.get("marks"), "q": d.get("question", "")[:240],
                        "options": [o[:60] for o in (d.get("options") or [])][:5]})
    lang_note = "English" if lang == "en" else "العربية"
    system = ("أنت خبير تقويم تربوي. حلّل أسئلة امتحانات وزارية سابقة لمبحث واحد واستنتج نمطها بدقة، دون نسخ أي سؤال. "
              f"اكتب الملخص بلغة: {lang_note}. أعد JSON فقط.")
    prompt = (f"الأسئلة ({len(approved)} سؤالًا، هذه عيّنة منها):\n{json.dumps(compact, ensure_ascii=False)}\n\n"
              'أعد JSON بهذا الشكل: {"overview":"وصف عام لنمط الورقة","structure":[{"section":"...","type":"mcq",'
              '"typical_count":10,"marks_each":1,"instruction_example":"..."}],"wording_patterns":["صيغ تتكرر في '
              'السؤال"],"distractor_style":"طريقة صياغة الخيارات الخاطئة","difficulty":"مستوى الصعوبة وتدرجه",'
              '"language_notes":"ملاحظات لغوية/أسلوبية"}')
    data = _ask_json(client, system, prompt, temperature=0.2)
    return data if isinstance(data, dict) and data.get("overview") else None


def _fmt_example(d, lang):
    letters = "ABCDE" if lang == "en" else "أبجدهـ"
    out = d.get("question", "")
    for i, o in enumerate(d.get("options") or []):
        out += f"\n  {letters[i]}) {o}"
    ans = None
    if d.get("type") == "mcq" and d.get("correct_index") is not None:
        ans = (d.get("options") or [])[d["correct_index"]]
    elif d.get("type") == "tf" and d.get("correct") is not None:
        ans = ("True" if d["correct"] else "False") if lang == "en" else ("صح" if d["correct"] else "خطأ")
    elif d.get("model_answer"):
        ans = d["model_answer"]
    if ans:
        out += f"\n  → {ans}"
    return out


def style_snippet(book_slug, qtype, lang="ar", k=3):
    """نص يُضاف إلى تعليمات توليد السؤال: ملخّص نمط الأسئلة الوزارية + أمثلة معتمدة من النوع نفسه. '' إن لم يتوفر شيء."""
    try:
        style = _style_cached(book_slug)
        approved = _approved_cached(book_slug)
    except Exception:  # noqa: BLE001
        return ""
    parts = []
    if style:
        p = style[0]
        pats = "؛ ".join(p.get("wording_patterns") or [])
        parts.append(f"{p.get('overview', '')}\n- Wording: {pats}\n- Distractors: {p.get('distractor_style', '')}\n"
                     f"- Difficulty: {p.get('difficulty', '')}")
    same = [r["data"] for r in approved if r["qtype"] == qtype]
    if same:
        ex = "\n\n".join(_fmt_example(d, lang) for d in random.sample(same, min(k, len(same))))
        parts.append(("Real Ministry questions of this type:\n" if lang == "en" else "أسئلة وزارية حقيقية من النوع نفسه:\n") + ex)
    if not parts:
        return ""
    if lang == "en":
        head = ("Write the new question in the SAME style, format, level and wording conventions as the Jordanian Ministry "
                "exams described below. Do NOT copy any example or reuse its content; the new question must be about this "
                "lesson only.\n")
    else:
        head = ("اكتب السؤال الجديد بالنمط نفسه والصياغة والمستوى كما في الامتحانات الوزارية الموصوفة أدناه. لا تنسخ أي مثال "
                "ولا تعد استخدام محتواه؛ يجب أن يخص السؤال الجديد هذا الدرس وحده.\n")
    return head + "\n\n".join(parts)


def _n(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]|_", " ", _norm(str(t)))).strip()


def too_similar(book_slug, text):
    """هل السؤال المولَّد يكاد يطابق سؤالًا وزاريًا معتمدًا؟ (لمنع النسخ الحرفي)."""
    try:
        approved = _approved_cached(book_slug)
    except Exception:  # noqa: BLE001
        return False
    n = _n(text)
    return any(e == n or difflib.SequenceMatcher(None, e, n).ratio() >= SIMILAR_RATIO
               for e in (_n(r["data"].get("question", "")) for r in approved))


# ================================================================ الواجهة
def _can_manage(user, book):
    scope = acc.qbank_subject_scope(user)
    return user["role"] == "admin" or (user["role"] == "supervisor" and book["subject"] in scope)


def _box(text, lang, bold=False):
    d, a = ("ltr", "left") if lang == "en" else ("rtl", "right")
    body = html.escape(str(text)).replace("\n", "<br>")
    return f"<div dir='{d}' style='text-align:{a};{'font-weight:600;' if bold else ''}margin:2px 0'>{body}</div>"


def _render_q(r, exams, lang):
    d, ex = r["data"], exams.get(r["exam_id"], {})
    head = " · ".join(x for x in [str(ex.get("year") or ""), ex.get("session") or "", d.get("section") or "",
                                  (f"{d['marks']:g} علامة" if d.get("marks") else ""),
                                  QTYPE_AR.get(r["qtype"], "")] if x)
    st.markdown(f"<small style='color:gray'>{html.escape(head)}</small>", unsafe_allow_html=True)
    if d.get("instruction"):
        st.markdown(_box(d["instruction"], lang), unsafe_allow_html=True)
    st.markdown(_box(d["question"], lang, bold=True), unsafe_allow_html=True)
    if d.get("image_id"):
        img = images.load(d["image_id"])
        if img:
            st.image(img, width=380)
    letters = "ABCDE" if lang == "en" else "أبجدهـ"
    for i, o in enumerate(d.get("options") or []):
        st.markdown(_box(f"{letters[i]}) {o}", lang), unsafe_allow_html=True)
    with st.expander("الإجابة"):
        if r["qtype"] == "mcq" and d.get("correct_index") is not None:
            st.markdown(_box(f"{letters[d['correct_index']]}) {d['options'][d['correct_index']]}", lang), unsafe_allow_html=True)
        elif r["qtype"] == "tf" and d.get("correct") is not None:
            st.write("صح" if d["correct"] else "خطأ")
        elif d.get("model_answer"):
            st.markdown(_box(d["model_answer"], lang), unsafe_allow_html=True)
        else:
            st.caption("لا تتوفر إجابة نموذجية لهذا السؤال.")
    st.divider()


def _bank_tab(book, user, can_manage, lang):
    slug = book["slug"]
    visible = is_visible(slug)
    if user["role"] == "admin":
        new = st.toggle("إتاحة هذا البنك للمعلمين والطلاب", value=visible, key=f"mvis_{slug}")
        if new != visible:
            set_visible(slug, new)
            st.rerun()
    elif can_manage:
        st.caption("البنك " + ("**متاح** للمعلمين والطلاب." if visible else "**غير متاح** لهم حاليًا (يقرّر المدير ذلك)."))
    rows, exams = list_questions(slug, status="approved"), {e["id"]: e for e in list_exams(slug)}
    if not rows:
        st.info("لا توجد أسئلة معتمدة بعد.")
        return
    c1, c2, c3 = st.columns(3)
    years = sorted({exams[r["exam_id"]].get("year") for r in rows if r["exam_id"] in exams and exams[r["exam_id"]].get("year")},
                   reverse=True)
    f_year = c1.selectbox("السنة", ["الكل"] + years, key=f"mf_y_{slug}")
    f_type = c2.selectbox("النوع", ["الكل"] + [QTYPE_AR[t] for t in QTYPES if any(r["qtype"] == t for r in rows)],
                          key=f"mf_t_{slug}")
    lessons = sorted({r["lesson_title"] for r in rows if r.get("lesson_title")})
    f_les = c3.selectbox("الدرس", ["الكل"] + lessons, key=f"mf_l_{slug}")
    flt = [r for r in rows
           if (f_year == "الكل" or exams.get(r["exam_id"], {}).get("year") == f_year)
           and (f_type == "الكل" or QTYPE_AR[r["qtype"]] == f_type)
           and (f_les == "الكل" or r.get("lesson_title") == f_les)]
    st.caption(f"{len(flt)} سؤال")
    pages = max(1, -(-len(flt) // PAGE_SIZE))
    pg = st.number_input("الصفحة", 1, pages, 1, key=f"mpg_{slug}") if pages > 1 else 1
    for r in flt[(pg - 1) * PAGE_SIZE: pg * PAGE_SIZE]:
        _render_q(r, exams, lang)


def _upload_section(book, flat_lessons, user):
    slug = book["slug"]
    st.caption("ارفع ملفات امتحانات سابقة (TXT / Word / PDF / صور). تُحوَّل إلى مسوّدات تراجعها قبل الاعتماد. "
               "كل صورة أو جزء نصي يُحتسب طلبًا واحدًا من الحصة اليومية. الأشكال والرسومات داخل الأسئلة لا تُنقل (النص فقط).")
    c1, c2 = st.columns(2)
    year = c1.number_input("سنة الامتحان", 1990, 2100, datetime.now().year - 1, key=f"mu_y_{slug}")
    session = c2.text_input("الدورة", placeholder="مثال: الدورة الشتوية", key=f"mu_s_{slug}")
    files = st.file_uploader("ملفات الامتحان", type=["txt", "docx", "pdf", "png", "jpg", "jpeg"],
                             accept_multiple_files=True, key=f"mu_f_{slug}")
    if not st.button("🔍 استخراج الأسئلة", type="primary", disabled=not files, key=f"mu_b_{slug}"):
        return
    client, items, failed = get_client(), [], []
    with st.spinner("جارٍ قراءة الملفات واستخراج الأسئلة..."):
        for f in files:
            try:
                units = read_sources(f)
            except Exception as e:  # noqa: BLE001
                failed.append(str(e))
                continue
            for text, image in units:
                auth_ui.require_quota_or_stop(user)
                got = extract(client, text, image)
                if not got:
                    failed.append(f"«{f.name}»: لم يُستخرج أي سؤال من أحد أجزاء الملف.")
                items += got
        if items:
            tag_lessons(client, items, flat_lessons, user)
            exam_id = add_exam(slug, int(year), session.strip(), ", ".join(f.name for f in files)[:200], user["id"])
            add_questions(exam_id, slug, items)
    for m in failed:
        st.warning(m)
    if items:
        st.success(f"استُخرج {len(items)} سؤالًا كمسوّدات. راجعها أدناه ثم اعتمدها.")
    elif not failed:
        st.error("لم يُستخرج أي سؤال. تأكد من وضوح الملفات.")


def _review_section(book, flat_lessons, user, lang):
    slug = book["slug"]
    exams = list_exams(slug)
    if exams:
        with st.expander(f"🗂️ الامتحانات المرفوعة ({len(exams)})"):
            for e in exams:
                qs = list_questions(slug, exam_id=e["id"])
                cnt = {s: sum(1 for q in qs if q["status"] == s) for s in ("draft", "approved", "rejected")}
                c1, c2 = st.columns([5, 1])
                c1.write(f"**{e.get('year') or '—'}** {e.get('session') or ''} — مسوّدات {cnt['draft']} · معتمدة "
                         f"{cnt['approved']} · مرفوضة {cnt['rejected']}")
                if c2.button("🗑️", key=f"mdel_{e['id']}", help="حذف الامتحان وكل أسئلته"):
                    delete_exam(e["id"])
                    _clear_caches()
                    st.rerun()
    drafts = list_questions(slug, status="draft")
    if not drafts:
        st.info("لا توجد مسوّدات بانتظار المراجعة.")
        return
    st.markdown(f"**{len(drafts)} سؤال بانتظار المراجعة** (يُعرض {min(REVIEW_BATCH, len(drafts))} في كل مرة)")
    if st.checkbox("أؤكد أنني راجعت المسوّدات وأريد اعتماد كلها دفعة واحدة", key=f"mall_{slug}"):
        if st.button(f"✅ اعتماد كل المسوّدات ({len(drafts)})", key=f"mallb_{slug}"):
            for q in drafts:
                update_question(q["id"], {"status": "approved", "reviewed_by": user["id"], "reviewed_at": _now()})
            _clear_caches()
            st.rerun()
    lesson_titles = ["— بلا درس —"] + [l["title"] for l in flat_lessons]
    letters = "ABCDE" if lang == "en" else "أبجدهـ"
    for q in drafts[:REVIEW_BATCH]:
        d, k = dict(q["data"]), f"mr_{q['id']}"
        with st.container(border=True):
            st.caption(f"{QTYPE_AR.get(q['qtype'], '')} — {d.get('section') or ''}")
            d["question"] = st.text_area("نص السؤال", d["question"], key=f"{k}_q")
            if q["qtype"] == "mcq":
                opts = [o.strip() for o in st.text_area("الخيارات (خيار في كل سطر)", "\n".join(d.get("options") or []),
                                                        key=f"{k}_o").splitlines() if o.strip()]
                d["options"] = opts
                labels = ["غير محددة"] + [f"{letters[i]}) {o}" for i, o in enumerate(opts[:5])]
                cur = (d.get("correct_index") + 1) if d.get("correct_index") is not None and d["correct_index"] < len(opts) else 0
                pick = st.selectbox("الإجابة الصحيحة", range(len(labels)), index=cur,
                                    format_func=lambda i, L=labels: L[i], key=f"{k}_c")
                d["correct_index"] = (pick - 1) if pick > 0 else None
            elif q["qtype"] == "tf":
                cur = {None: 0, True: 1, False: 2}[d.get("correct")]
                pick = st.selectbox("الحكم الصحيح", ["غير محدد", "صح", "خطأ"], index=cur, key=f"{k}_c")
                d["correct"] = {"غير محدد": None, "صح": True, "خطأ": False}[pick]
            else:
                d["model_answer"] = st.text_area("الإجابة النموذجية (اختياري)", d.get("model_answer") or "",
                                                 key=f"{k}_a").strip() or None
            rm_img, up_img = False, None
            if d.get("image_id"):
                cur_img = images.load(d["image_id"])
                if cur_img:
                    st.image(cur_img, width=320)
                rm_img = st.checkbox("حذف صورة السؤال", key=f"{k}_rmimg")
            up_img = st.file_uploader("إضافة أو استبدال صورة السؤال (اختياري)", type=["png", "jpg", "jpeg"], key=f"{k}_img")
            c1, c2 = st.columns(2)
            d["marks"] = c1.number_input("العلامة", 0.0, 100.0, float(d.get("marks") or 0.0), 0.5, key=f"{k}_m") or None
            cur_l = lesson_titles.index(q["lesson_title"]) if q.get("lesson_title") in lesson_titles else 0
            les = c2.selectbox("الدرس", lesson_titles, index=cur_l, key=f"{k}_l")
            b1, b2 = st.columns(2)

            def _patch(d=d, les=les, up_img=up_img, rm_img=rm_img):
                if up_img is not None:
                    try:
                        d["image_id"] = images.save(*images.prepare(Image.open(io.BytesIO(up_img.getvalue()))))
                    except Exception:  # noqa: BLE001
                        st.error("تعذّرت قراءة الصورة المرفوعة.")
                elif rm_img:
                    d.pop("image_id", None)
                return {"data": d, "lesson_title": None if les == lesson_titles[0] else les,
                        "reviewed_by": user["id"], "reviewed_at": _now()}

            if b1.button("✅ اعتماد", key=f"{k}_ok", type="primary"):
                update_question(q["id"], {**_patch(), "status": "approved"})
                _clear_caches()
                st.rerun()
            if b2.button("🗑️ رفض", key=f"{k}_no"):
                update_question(q["id"], {**_patch(), "status": "rejected"})
                st.rerun()


def to_qbank_item(row, lesson_ranges):
    """سؤال وزاري معتمد → (qtype, page_start, page_end, بيانات السؤال بصيغة بنك قيّمني) أو (None, سبب الاستبعاد)."""
    d, qt = row["data"], row["qtype"]
    if qt not in ("mcq", "tf", "fill", "short"):
        return None, "نوع غير مدعوم في بنك قيّمني"
    rng = lesson_ranges.get(row.get("lesson_title") or "")
    if not rng:
        return None, "غير مرتبط بدرس"
    q = {"type": qt, "question": d["question"], "explanation": "", "page": None, "source": "ministry",
         "ministry_id": row["id"]}
    if d.get("image_id"):
        q["image_id"] = d["image_id"]
    if qt == "mcq":
        opts = d.get("options") or []
        if len(opts) != 4 or len(set(opts)) != 4:
            return None, "يلزم أربعة خيارات مختلفة"
        if d.get("correct_index") is None:
            return None, "بلا إجابة صحيحة محدّدة"
        q["options"], q["correct_index"] = opts, d["correct_index"]
    elif qt == "tf":
        if not isinstance(d.get("correct"), bool):
            return None, "بلا حكم صحيح محدّد"
        q["correct"] = d["correct"]
    else:
        if not (d.get("model_answer") or "").strip():
            return None, "بلا إجابة نموذجية"
        q["model_answer"] = d["model_answer"].strip()
    return (qt, rng[0], rng[1], q), None


def _transfer_section(book, flat_lessons, user):
    slug = book["slug"]
    st.caption("نقل الأسئلة الوزارية **المعتمدة** إلى بنك «قيّمني» والاختبارات ليسحب منها الطلاب والمعلمون في الاختبارات. "
               "يتم يدويًا بقرارك. يُنقل فقط: الاختيار من متعدد (4 خيارات وإجابة محددة)، وصح/خطأ، وأكمل الفراغ، "
               "والقصير؛ بشرط ربطه بدرس وتحديد إجابته أثناء المراجعة. تُنقل صورة السؤال أيضًا.")
    ranges = {l["title"]: (l["start"], l["end"]) for l in flat_lessons}
    approved = list_questions(slug, status="approved")
    pending = [r for r in approved if not r.get("transferred_at")]
    done = [r for r in approved if r.get("transferred_at")]
    ok, bad = [], {}
    for r in pending:
        item, why = to_qbank_item(r, ranges)
        if item:
            ok.append((r, item))
        else:
            bad.setdefault(why, 0)
            bad[why] += 1
    c1, c2, c3 = st.columns(3)
    c1.metric("جاهزة للنقل", len(ok))
    c2.metric("تم نقلها", len(done))
    c3.metric("غير مؤهَّلة", sum(bad.values()))
    for why, n in bad.items():
        st.caption(f"• {n} سؤال: {why}")
    if st.button(f"🏦 نقل الأسئلة الجاهزة ({len(ok)}) إلى بنك قيّمني والاختبارات", type="primary", disabled=not ok,
                 key=f"mtr_{slug}"):
        for r, (qt, ps, pe, q) in ok:
            qid = qbank.add_question(slug, ps, pe, qt, q)
            update_question(r["id"], {"qbank_id": qid, "transferred_at": _now()})
        st.success(f"نُقل {len(ok)} سؤالًا.")
        st.rerun()
    if done and catalog.backend_name() == "supabase":
        with st.expander("سحب الأسئلة المنقولة من بنك قيّمني"):
            st.caption("يحذف النسخ المنقولة من بنك «قيّمني» والاختبارات فقط، وتبقى الأسئلة الوزارية الأصلية في هذا البنك.")
            if st.button(f"↩️ سحب كل المنقول ({len(done)})", key=f"mwd_{slug}"):
                for r in done:
                    if r.get("qbank_id"):
                        qbank.delete_question(r["qbank_id"])
                    update_question(r["id"], {"qbank_id": None, "transferred_at": None})
                st.rerun()


def _style_section(book, user, lang):
    slug = book["slug"]
    approved = list_questions(slug, status="approved")
    st.caption(f"الأسئلة المعتمدة: **{len(approved)}**. تُستنتج منها بصمة النمط، وتُستخدم أمثلة منها عند توليد أسئلة جديدة "
               "في «قيّمني» و«إنشاء اختبار». كلما زادت الدورات المعتمدة كانت المحاكاة أدق.")
    cur = get_style(slug)
    if cur:
        p, n = cur
        st.markdown(f"**النمط الحالي** (مبني على {n} سؤالًا)")
        st.markdown(_box(p.get("overview", ""), lang), unsafe_allow_html=True)
        for s in p.get("structure") or []:
            st.markdown(f"- {s.get('section', '')} — {s.get('type', '')} × {s.get('typical_count', '')} "
                        f"({s.get('marks_each', '')} علامة)")
        for lab, key in (("الصياغة", "wording_patterns"), ("الخيارات الخاطئة", "distractor_style"),
                         ("الصعوبة", "difficulty"), ("ملاحظات لغوية", "language_notes")):
            v = p.get(key)
            if v:
                st.markdown(f"**{lab}:** " + ("؛ ".join(v) if isinstance(v, list) else str(v)))
    else:
        st.info("لم يُستنتج نمط لهذا الكتاب بعد.")
    if st.button("🔄 تحديث نمط الأسئلة من الأسئلة المعتمدة", disabled=len(approved) < MIN_FOR_STYLE, key=f"ms_{slug}"):
        auth_ui.require_quota_or_stop(user)
        with st.spinner("جارٍ تحليل الأسئلة..."):
            prof = build_style(get_client(), approved, lang)
        if prof:
            save_style(slug, prof, len(approved))
            _clear_caches()
            st.rerun()
        else:
            st.error("تعذّر استنتاج النمط. حاول مرة أخرى.")
    if len(approved) < MIN_FOR_STYLE:
        st.caption(f"يلزم {MIN_FOR_STYLE} أسئلة معتمدة على الأقل.")


def render_ministry(book, flat_lessons, user, lang="ar"):
    st.subheader("📜 أسئلة وزارية سابقة")
    can_manage = _can_manage(user, book)
    if not can_manage:
        if not is_visible(book["slug"]):
            st.info("هذا البنك غير متاح حاليًا لهذا المبحث.")
            return
        _bank_tab(book, user, False, lang)
        return
    t1, t2, t4, t3 = st.tabs(["📚 البنك", "⬆️ رفع ومراجعة", "🏦 نقل إلى بنك قيّمني", "🎯 نمط الأسئلة"])
    with t1:
        _bank_tab(book, user, True, lang)
    with t2:
        _upload_section(book, flat_lessons, user)
        st.markdown("---")
        _review_section(book, flat_lessons, user, lang)
    with t4:
        _transfer_section(book, flat_lessons, user)
    with t3:
        _style_section(book, user, lang)
