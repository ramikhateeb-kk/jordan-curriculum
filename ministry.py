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
import math
import random
import re
import uuid
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
import grammar_ext
import reading_texts
import subject_profiles as sp
from config import BASE, GEMINI_MODEL
from rag import _norm, get_client, select_context

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
             "order": "exam_id.desc,id.asc"}
        if status:
            p["status"] = f"eq.{status}"
        if exam_id:
            p["exam_id"] = f"eq.{exam_id}"
        return sorted(_get("ministry_questions", p),
                      key=lambda q: (-q["exam_id"], (q.get("data") or {}).get("seq") or q.get("number") or 10**6, q["id"]))
    rows = [q for q in _local()["questions"] if q["book_slug"] == book_slug
            and (not status or q["status"] == status) and (not exam_id or q["exam_id"] == exam_id)]
    return sorted(rows, key=lambda q: (-q["exam_id"], (q.get("data") or {}).get("seq") or q.get("number") or 10**6, q["id"]))


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
    "أنت مساعد يستخرج الأسئلة من امتحان وزاري سابق (نص أو صور صفحاته المتتابعة) إلى JSON هرمي. التزم بصرامة:\n"
    "1) انسخ كل نص بلغته الأصلية (عربي أو إنجليزي) كما هو حرفيًا، دون ترجمة أو تصحيح أو تلخيص أو إعادة صياغة، "
    "ولا تضف سؤالًا أو خيارًا أو إجابة من عندك.\n"
    "2) البنية: groups = قائمة بالأسئلة الرئيسية بترتيب ظهورها. المجموعة (group) هي سؤال رئيسي أو فرع منه "
    "(مثل Question One، أو Question Two - A، أو Question Two - B، أو C: Literature Spot، أو Question Three). لكل مجموعة: "
    "title عنوانها كما ورد، instruction تعليمات السؤال الرئيسي كما وردت (بكل اللغات المكتوبة)، marks علاماتها إن ظهرت، "
    "passage، وquestions أسئلتها الفرعية.\n"
    "3) النص الرئيسي passage: إذا طُلب في السؤال الرئيسي قراءة نص أو مقال أو مقتطف أو قصيدة أو حوار ثم طُرحت أسئلة عليه، "
    "فضع النص كاملًا مرة واحدة في passage مع عنوانه وفقراته وفواصل الأسطر كما طُبع، ولا تكرره في الأسئلة الفرعية. "
    "كل سؤال فرعي يحتوي في question على نص سؤاله وحده. إن لم يوجد نص مشترك (مثل 28 سؤال اختيار من متعدد "
    "مستقلة) فاجعل passage = null وضع كل سؤال مستقلًا في questions.\n"
    "4) type لكل سؤال فرعي: mcq (له خيارات)، tf (صح/خطأ)، fill (فراغ؛ اكتب الفراغ ______)، short (إجابة قصيرة أو أسئلة فهم)، "
    "essay (كتابة مطوّلة أو موضوع تعبير)، matching (مطابقة)، other (غير ذلك؛ نصه كاملًا في question). "
    "خيارات الاختيار من متعدد في options بلا حروف الترقيم (A، B، أ، ب).\n"
    "5) number رقم السؤال الفرعي المطبوع، marks علامته إن ظهرت (مثل (3 points) فتكون 3). ضع الإجابة الصحيحة "
    "(correct_index أو correct أو model_answer) فقط إذا كانت معلَّمة صراحةً في المدخل، وإلا null.\n"
    "6) أي كلمة أو عبارة مسطَّرة (underlined) في المدخل، سواء في نص رئيسي أو سؤال أو خيار، أحِطها بـ [[ ]] "
    "مثل: When he [[gave the final line of the joke]], nobody laughed.\n"
    "7) تجاهل الترويسات والملحوظات الإدارية وأرقام الصفحات وعبارات مثل SEE PAGE TWO وصفحات الإجابة الفارغة.\n"
    "8) إذا اعتمد سؤال على شكل أو رسم أو صورة أو جدول أو مخطط، فأعد figure_page = رقم الصفحة (1 للأولى) وfigure_box = "
    "[ymin, xmin, ymax, xmax] بإحداثيات من 0 إلى 1000 تحيط بالشكل وحده، وإلا null. لا تعتبر النص المطبوع شكلًا.\n"
    "أعد JSON فقط بلا أي نص آخر."
)
EXTRACT_SCHEMA = (
    '{"groups":[{"title":"Question One","instruction":"...","marks":null,"passage":null,"questions":['
    '{"number":1,"type":"mcq","question":"...","options":["...","...","...","..."],"correct_index":null,"correct":null,'
    '"model_answer":null,"marks":null,"figure_page":null,"figure_box":null}]}]}'
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
    return {"number": int(n) if n is not None else None, "qtype": qt, "data": d, "box": it.get("figure_box"),
            "pid": it.get("passage_id")}


def _as_images(image):
    if image is None:
        return []
    return list(image) if isinstance(image, (list, tuple)) else [image]


def extract(client, text, image):
    """يستخرج أسئلة امتحان من نص و/أو صفحة أو عدة صفحات متتابعة (طلب واحد) إلى أسئلة مرتّبة.
    كل سؤال فرعي يحمل: section (عنوان السؤال الرئيسي)، instruction، passage (النص الرئيسي المشترك) وpassage_key،
    وseq (ترتيبه في الامتحان). image: صورة PIL أو قائمة صور لصفحات متتابعة."""
    imgs = _as_images(image)
    prompt = (f"استخرج أسئلة هذا الامتحان بهذا الشكل بالضبط:\n{EXTRACT_SCHEMA}\n\n")
    if text:
        prompt += f"المدخل:\n{text}"
    elif len(imgs) > 1:
        prompt += f"المدخل: {len(imgs)} صفحات متتابعة من الامتحان نفسه مرفقة كصور بترتيبها (الصفحة 1 هي الأولى)."
    else:
        prompt += "المدخل: صفحة الامتحان المرفقة كصورة."
    contents = prompt
    if imgs:
        contents = []
        for i, im in enumerate(imgs, start=1):
            contents += [f"الصفحة {i}:", im]
        contents.append(prompt)
    data = _ask_json(client, EXTRACT_SYSTEM, contents)
    groups = data.get("groups") if isinstance(data, dict) else None
    if groups is None and isinstance(data, dict) and isinstance(data.get("questions"), list):
        groups = [{"questions": data["questions"]}]            # شكل مبسّط
    if groups is None and isinstance(data, list):
        groups = [{"questions": data}]                          # قائمة أسئلة فقط (شكل قديم)
    got, cache = [], {}
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        passage = str(g.get("passage") or "").strip()
        pkey = f"p{uuid.uuid4().hex[:8]}" if passage else None
        title = str(g.get("title") or "").strip() or None
        instr = str(g.get("instruction") or "").strip() or None
        gmarks = _num(g.get("marks"))
        for qd in g.get("questions") or []:
            it = clean_item(qd)
            if not it:
                continue
            d = it["data"]
            d["section"] = d.get("section") or title
            d["instruction"] = d.get("instruction") or instr
            if gmarks is not None:
                d["section_marks"] = gmarks
            if passage:
                d["passage"], d["passage_key"] = passage, pkey
            d["seq"] = len(got) + 1
            d["number"] = it.get("number")
            # اقتطاع شكل السؤال من الصفحة المقصودة
            box, pg = it.pop("box", None), _num(qd.get("figure_page")) if isinstance(qd, dict) else None
            if box and imgs and isinstance(box, (list, tuple)) and len(box) == 4:
                src = imgs[int(pg) - 1] if pg and 1 <= int(pg) <= len(imgs) else (imgs[0] if len(imgs) == 1 else None)
                if src is not None:
                    try:
                        key = (id(src),) + tuple(round(float(v) / 20) for v in box)
                    except (TypeError, ValueError):
                        key = None
                    if key:
                        if key not in cache:
                            crop = images.crop_box(src, box)
                            cache[key] = images.save(*images.prepare(crop)) if crop is not None else None
                        if cache[key]:
                            d["image_id"] = cache[key]
            it.pop("pid", None)
            got.append(it)
    return got


ANSWER_SYSTEM = (
    "You are an expert teacher answering past Ministry exam questions. A human reviewer will check your answers before "
    "they are approved. Rules:\n"
    "1) LANGUAGE: every item has an \"answer_language\" field. Write \"note\" and any free-text \"answer\" ONLY in that language "
    "(English -> English; Arabic -> Arabic). Never write Arabic for an English item, even if other text is Arabic.\n"
    "2) For an item with a passage_key, answer from the matching text in \"passages\" only, and set source_pages to [].\n"
    "3) type mcq: you MUST choose exactly one of the given options. Return correct_index (0-based position in options) AND "
    "correct_option_text (copy the chosen option exactly as written).\n"
    "4) type tf: return correct (true or false). Types fill and short: return answer, a brief correct answer "
    "(for fill: only the missing word or phrase).\n"
    "5) Text inside [[ ]] was underlined in the original exam and is often what the question is about.\n"
    "6) If an item has book_excerpts (pages of the textbook), use them as the primary evidence: set source_pages to the "
    "page numbers of the excerpts that support the answer (ONLY numbers present in that item's book_excerpts). If the "
    "excerpts do not contain the answer, answer from general knowledge and set source_pages to [].\n"
    "7) If you are not sure, set the answer fields to null and confidence to \"low\". Do not guess or invent.\n"
    "8) confidence is high, medium or low. note is one short sentence explaining why, in answer_language.\n"
    "Return one JSON object per item, in a JSON list, and cover EVERY item.")
ANSWER_TYPES = ("mcq", "tf", "fill", "short")
_AR = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")


def _lang_name(*texts):
    """لغة السؤال (للتعليمات): Arabic إن غلبت الحروف العربية وإلا English."""
    t = " ".join(str(x) for x in texts if x)
    return "Arabic" if len(_AR.findall(t)) > len(re.findall(r"[A-Za-z]", t)) else "English"


def _pick_option(v, options):
    """يحدد رقم الخيار الصحيح من ردّ النموذج بأكثر من طريقة: نص الخيار، ثم الحرف، ثم الرقم.
    يعيد (index أو None, تضارب?)."""
    n = len(options)
    by_text = None
    txt = v.get("correct_option_text") or (v.get("answer") if isinstance(v.get("answer"), str) else None)
    if txt:
        t = _n(txt)
        for i, o in enumerate(options):
            if _n(o) == t:
                by_text = i
                break
        if by_text is None:
            for i, o in enumerate(options):          # احتواء جزئي كملاذ أخير
                if t and (t in _n(o) or _n(o) in t) and len(_n(o)) > 1:
                    by_text = i
                    break
    by_letter = None
    letter = v.get("correct_letter") or v.get("letter")
    if isinstance(letter, str) and letter.strip():
        L = letter.strip().strip(").").upper()
        pos = ("ABCDE".find(L) if L in "ABCDE" else "أبجدهـ".find(letter.strip()[0]))
        by_letter = pos if 0 <= pos < n else None
    by_int = None
    ci = v.get("correct_index")
    if isinstance(ci, str) and ci.strip().isdigit():
        ci = int(ci.strip())
    if isinstance(ci, int) and not isinstance(ci, bool) and 0 <= ci < n:
        by_int = ci
    chosen = by_text if by_text is not None else (by_letter if by_letter is not None else by_int)
    return chosen, (by_text is not None and by_int is not None and by_text != by_int)


def _best_window(text, query, size=800):
    """أنسب مقطع (~size حرف) من صفحة لسؤال معيّن (تداخل الكلمات) كي لا تُرسَل الصفحة كلها."""
    if len(text) <= size:
        return text
    words = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 3}
    best, best_i, step = -1, 0, max(size // 4, 100)
    low = text.lower()
    for i in range(0, max(len(text) - size, 0) + step, step):
        sc = sum(1 for w in words if w in low[i:i + size])
        if sc > best:
            best, best_i = sc, i
    return text[best_i:best_i + size]


def _excerpts(ctx, d, k=2):
    """أقرب صفحات الكتاب لسؤال: [{"page": رقم مطبوع, "text": مقطع}] أو [] إن لم يتوفر فهرس الكتاب."""
    if not ctx or not ctx.get("idx") or d.get("passage"):
        return []
    query = d["question"] + " " + " ".join(d.get("options") or [])
    try:
        pages = select_context(ctx["idx"], query, None, max_chars=3000, k=k)[:k]
    except Exception:  # noqa: BLE001
        return []
    off = ctx.get("offset", 0)
    return [{"page": p["page"] - off, "text": _best_window(p["text"], query)} for p in pages]


def _lesson_of(ctx, printed_page):
    pdf = printed_page + (ctx or {}).get("offset", 0)
    for l in (ctx or {}).get("lessons") or []:
        if l["start"] <= pdf <= l["end"]:
            return l["title"]
    return None


def _list_from(data):
    """يقبل: قائمة نتائج، أو كائنًا يغلّفها، أو نتيجة واحدة، أو كائنًا مفتاحه رقم السؤال."""
    if isinstance(data, dict):
        for key in ("results", "answers", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        lists = [v for v in data.values() if isinstance(v, list)]
        if lists:
            return lists[0]
        if "n" in data or "id" in data:                    # نتيجة واحدة
            return [data]
        keyed = [{"n": k, **v} for k, v in data.items() if isinstance(v, dict) and str(k).strip().isdigit()]
        return keyed
    return data if isinstance(data, list) else []


def _ask_answers(client, chunk, ctx):
    """طلب واحد لمجموعة أسئلة. يعيد {معرّف السؤال: نتيجة}."""
    passages, items, by_n, pages_of = {}, [], {}, {}
    for n, r in enumerate(chunk, start=1):
        d = r["data"]
        lang = _lang_name(d["question"], d.get("passage"))
        pk = None
        if d.get("passage"):
            pk = d.get("passage_key") or f"p{r['id']}"
            passages[pk] = d["passage"]
        instr = d.get("instruction") or None
        if instr and lang == "English":                 # تعليمات عربية طويلة تدفع النموذج للرد بالعربية
            instr = re.sub(r"\s+", " ", _AR.sub("", re.sub(r"[\u0600-\u06FF\u0750-\u077F]+", "", instr))).strip(" .,:;()-")
        ex = _excerpts(ctx, d)
        pages_of[n] = {e["page"] for e in ex}
        by_n[n] = r
        item = {"n": n, "type": r["qtype"], "answer_language": lang, "instruction": instr or None,
                "passage_key": pk, "question": d["question"], "options": d.get("options")}
        if ex:
            item["book_excerpts"] = ex
        items.append(item)
    prompt = (f"passages:\n{json.dumps(passages, ensure_ascii=False)}\n\nitems:\n{json.dumps(items, ensure_ascii=False)}\n\n"
              'Return a JSON list with one object per item: [{"n":1,"correct_index":1,"correct_option_text":"exact option text",'
              '"correct":null,"answer":null,"source_pages":[],"confidence":"high","note":"one short sentence in answer_language"}]. '
              "IMPORTANT: cover every item; write notes in each item's answer_language.")
    out = {}
    for v in _list_from(_ask_json(client, ANSWER_SYSTEM, prompt)):
        if not isinstance(v, dict):
            continue
        key = v.get("n", v.get("id"))
        key = int(key) if isinstance(key, str) and key.strip().isdigit() else key
        r = by_n.get(key)
        if not r:
            continue
        d, qt = r["data"], r["qtype"]
        conf = v.get("confidence") if v.get("confidence") in ("high", "medium", "low") else "low"
        res = {"ai_answer": True, "ai_conf": conf, "ai_note": str(v.get("note") or "").strip()[:300] or None}
        if _lang_name(d["question"], d.get("passage")) == "English" and res["ai_note"] and _AR.search(res["ai_note"]):
            res["ai_note"] = None                         # ملاحظة عربية لسؤال إنجليزي: تُهمَل
        if qt == "mcq":
            idx, conflict = _pick_option(v, d.get("options") or [])
            if idx is None:
                continue
            res["correct_index"] = idx
            if conflict:
                res["ai_conf"] = "low"
        elif qt == "tf":
            if not isinstance(v.get("correct"), bool):
                continue
            res["correct"] = v["correct"]
        else:
            ans = str(v.get("answer") or "").strip()
            if not ans:
                continue
            res["model_answer"] = ans
        sp = sorted({int(p) for p in (v.get("source_pages") or []) if isinstance(p, (int, float, str))
                     and str(p).strip().lstrip("-").isdigit() and int(p) in pages_of[key]})
        if sp:
            res["source_pages"] = sp
            res["ai_lessons"] = [t for t in dict.fromkeys(_lesson_of(ctx, p) for p in sp) if t]
        out[r["id"]] = res
    return out


def suggest_answers(client, rows, ctx=None):
    """يقترح إجابات (rows: [{id, qtype, data}]) مع الصفحات والدروس التي أُخذت منها إن توفر فهرس الكتاب (ctx).
    الأسئلة تُرسَل في دفعات صغيرة (4 مع الكتاب، 8 بدونه) وبالتوازي، ثم كل سؤال سقط من ردّه يُعاد طلبه وحده؛
    فلا يتوقف النظام عند أول سؤال إن اختصر النموذج ردّه. لا يُجيب عن المقالي والمطابقة وغيرهما."""
    from concurrent.futures import ThreadPoolExecutor
    cand = [r for r in rows if r["qtype"] in ANSWER_TYPES]
    size = 4 if (ctx and ctx.get("idx")) else 8
    chunks = [cand[i:i + size] for i in range(0, len(cand), size)]
    out = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(lambda c: _ask_answers(client, c, ctx), chunks):
            out.update(res)
        missing = [r for r in cand if r["id"] not in out]
        for res in ex.map(lambda r: _ask_answers(client, [r], ctx), missing):    # سؤال سؤال للناقص
            out.update(res)
    return out


def _apply_ai(user, rows, replace_existing=False, ctx=None):
    """يطلب الإجابات ويحفظها في المسوّدات (علامة ai_answer تبقى حتى يعتمدها مراجع) ويعيد (المحفوظ، المطلوب)."""
    todo = []
    for r in rows:
        d = r["data"]
        has = (d.get("correct_index") is not None if r["qtype"] == "mcq" else
               d.get("correct") is not None if r["qtype"] == "tf" else bool(d.get("model_answer")))
        if r["qtype"] in ANSWER_TYPES and (replace_existing or not has):
            todo.append(r)
    if not todo:
        return 0, 0, []
    auth_ui.require_quota_or_stop(user)
    res = suggest_answers(get_client(), todo, ctx)
    for r in todo:
        if r["id"] not in res:
            continue
        got = res[r["id"]]
        patch = {"data": {**r["data"], **{k: v for k, v in got.items() if k != "ai_lessons"}, "ai_lessons": got.get("ai_lessons")}}
        if got.get("ai_lessons") and not r.get("lesson_title"):
            patch["lesson_title"] = got["ai_lessons"][0]
        update_question(r["id"], patch)
        for suffix in ("c", "a", "sp", "l"):                # لتتحدّث عناصر الشاشة
            st.session_state.pop(f"mr_{r['id']}_{suffix}", None)
    return len(res), len(todo), [r for r in todo if r["id"] not in res]


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


def examples_for_lessons(book_slug, lesson_titles, limit=6, lang="en"):
    """أسئلة وزارية معتمدة مرتبطة بهذه الدروس، منسّقة للاستشهاد بها في «اشرح لي». '' إن لم توجد."""
    try:
        titles = set(lesson_titles)
        rows = [r for r in _approved_cached(book_slug) if r.get("lesson_title") in titles]
    except Exception:  # noqa: BLE001
        return ""
    rows = sorted(rows, key=lambda r: r["id"])[:limit]
    return "\n\n".join(_fmt_example(r["data"], lang) for r in rows)


def _n(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]|_", " ", _norm(str(t)).lower())).strip()


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
    body = re.sub(r"\[\[(.+?)\]\]", r"<u>\1</u>", html.escape(str(text)), flags=re.S).replace("\n", "<br>")
    return f"<div dir='{d}' style='text-align:{a};{'font-weight:600;' if bold else ''}margin:2px 0'>{body}</div>"


def _render_q(r, exams, lang):
    d, ex = r["data"], exams.get(r["exam_id"], {})
    head = " · ".join(x for x in [str(ex.get("year") or ""), ex.get("session") or "", d.get("section") or "",
                                  (f"{d['marks']:g} علامة" if d.get("marks") else ""),
                                  QTYPE_AR.get(r["qtype"], "")] if x)
    st.markdown(f"<small style='color:gray'>{html.escape(head)}</small>", unsafe_allow_html=True)
    if d.get("instruction"):
        st.markdown(_box(d["instruction"], lang), unsafe_allow_html=True)
    if d.get("passage"):
        with st.expander("📄 النص الرئيسي للسؤال"):
            st.markdown(_box(d["passage"], lang), unsafe_allow_html=True)
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


def _batches(units, max_pages=6):
    """وحدات (نص, صورة) → دفعات: صفحات الصور المتتابعة تُرسَل معًا (حتى 6 صفحات) ليبقى النص الرئيسي مع أسئلته،
    وكل جزء نصي يُرسَل وحده."""
    out, cur = [], []
    for text, img in units:
        if img is None:
            if cur:
                out.append(("", cur))
                cur = []
            out.append((text, None))
        else:
            cur.append(img)
            if len(cur) >= max_pages:
                out.append(("", cur))
                cur = []
    if cur:
        out.append(("", cur))
    return out


def _upload_section(book, flat_lessons, user):
    slug = book["slug"]
    st.caption("ارفع ملفات امتحانات سابقة (TXT / Word / PDF / صور). تُحوَّل إلى مسوّدات تراجعها قبل الاعتماد. "
               "كل دفعة (حتى 6 صفحات متتابعة، أو جزء نصي) تُحتسب طلبًا واحدًا من الحصة اليومية. تُقتطع الأشكال من الصور تلقائيًا.")
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
            n_before = len(items)
            for text, image_group in _batches(units):
                auth_ui.require_quota_or_stop(user)
                got = extract(client, text, image_group)
                for it in got:                       # ترتيب الأسئلة عبر الأجزاء
                    it["data"]["seq"] = len(items) + it["data"].get("seq", 1)
                items += got
            if len(items) == n_before:
                failed.append(f"«{f.name}»: لم يُستخرج أي سؤال من هذا الملف.")
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


def _review_section(book, flat_lessons, user, lang, idx=None):
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
    all_drafts = list_questions(slug, status="draft")
    if not all_drafts:
        st.info("لا توجد مسوّدات بانتظار المراجعة.")
        return
    ex_by_id = {e["id"]: e for e in exams}
    ex_ids = sorted({q["exam_id"] for q in all_drafts}, reverse=True)
    ex_label = {i: f"{ex_by_id.get(i, {}).get('year') or '—'} {ex_by_id.get(i, {}).get('session') or ''} (#{i})".strip()
                for i in ex_ids}
    f1, f2 = st.columns(2)
    sel_ex = f1.selectbox("الامتحان", ["كل الامتحانات"] + ex_ids, key=f"mrex_{slug}",
                          format_func=lambda i: i if i == "كل الامتحانات" else ex_label[i])
    size = f2.selectbox("عدد الأسئلة في الصفحة", [5, 8, 15, 30], index=1, key=f"mrsz_{slug}")
    drafts = [q for q in all_drafts if sel_ex == "كل الامتحانات" or q["exam_id"] == sel_ex]
    n_pages = max(1, math.ceil(len(drafts) / size))
    pkey = f"mrp_{slug}"
    page = min(max(st.session_state.get(pkey, 1), 1), n_pages)
    st.session_state[pkey] = page
    nv1, nv2, nv3 = st.columns([1, 2, 1])
    if nv1.button("◀ السابقة", disabled=page <= 1, key=f"mrprev_{slug}"):
        st.session_state[pkey] = page - 1
        st.rerun()
    nv2.markdown(f"<div style='text-align:center'><b>{len(drafts)}</b> سؤال بانتظار المراجعة — صفحة <b>{page}</b> من "
                 f"<b>{n_pages}</b></div>", unsafe_allow_html=True)
    if nv3.button("التالية ▶", disabled=page >= n_pages, key=f"mrnext_{slug}"):
        st.session_state[pkey] = page + 1
        st.rerun()
    page_items = drafts[(page - 1) * size: page * size]
    ai_ctx = {"idx": idx, "offset": book.get("page_offset", 0), "lessons": flat_lessons}
    # ---- اقتراح الإجابات بالذكاء الاصطناعي للأسئلة المعروضة في هذه الصفحة
    ai_c1, ai_c2 = st.columns([3, 2])
    replace_all = ai_c2.checkbox("استبدال الإجابات الموجودة", key=f"mairep_{slug}")
    if ai_c1.button(f"🤖 اقتراح إجابات للأسئلة المعروضة ({len(page_items)})", key=f"maiall_{slug}"):
        with st.spinner("جارٍ اقتراح الإجابات..."):
            done_n, tried, failed_rows = _apply_ai(user, page_items, replace_all, ai_ctx)
        if not tried:
            msg = "لا توجد أسئلة تحتاج إجابة في هذه الصفحة."
        else:
            msg = f"اقتُرحت إجابات لـ {done_n} من {tried} سؤالًا. راجعها قبل الاعتماد."
            if failed_rows:
                nums = "، ".join(f"{(r['data'].get('section') or '')[-12:]} #{r['data'].get('number') or r.get('number') or r['id']}"
                                 for r in failed_rows)
                msg += f" تعذّر تحديد إجابة موثوقة لـ: {nums}."
        st.session_state[f"mainote_{slug}"] = msg
        st.rerun()
    if st.session_state.get(f"mainote_{slug}"):
        st.info(st.session_state.pop(f"mainote_{slug}"))
    if st.checkbox("أؤكد أنني راجعت المسوّدات وأريد اعتماد كل المعروضة بالفلتر الحالي دفعة واحدة", key=f"mall_{slug}"):
        safe = [q for q in drafts if not q["data"].get("ai_answer")]
        if len(safe) < len(drafts):
            st.caption(f"⚠️ سيُستثنى {len(drafts) - len(safe)} سؤال إجابته مقترحة من الذكاء الاصطناعي ولم تُراجَع بعد؛ "
                       "اعتمدها فرديًا بعد مراجعتها.")
        if st.button(f"✅ اعتماد كل المسوّدات ({len(safe)})", key=f"mallb_{slug}"):
            for q in safe:
                update_question(q["id"], {"status": "approved", "reviewed_by": user["id"], "reviewed_at": _now()})
            _clear_caches()
            st.rerun()
    lesson_titles = ["— بلا درس —"] + [l["title"] for l in flat_lessons]
    letters = "ABCDE" if lang == "en" else "أبجدهـ"
    exam_qs = {}      # أسئلة كل امتحان (لكل حالاتها) لمزامنة النص الرئيسي بين الأسئلة الفرعية
    for q in page_items:
        d, k = dict(q["data"]), f"mr_{q['id']}"
        if q["exam_id"] not in exam_qs:
            exam_qs[q["exam_id"]] = list_questions(slug, exam_id=q["exam_id"])
        siblings_all = exam_qs[q["exam_id"]]
        others = {}
        for r in siblings_all:
            pk = r["data"].get("passage_key")
            if pk and pk != d.get("passage_key") and r["data"].get("passage"):
                others.setdefault(pk, r["data"]["passage"])
        with st.container(border=True):
            sec = " — ".join(x for x in [d.get("section") or "",
                                         (f"({d['section_marks']:g} علامة)" if d.get("section_marks") else "")] if x)
            st.markdown(f"**السؤال الرئيسي:** {html.escape(sec) or '—'}")
            if d.get("instruction"):
                st.markdown(_box(d["instruction"], lang), unsafe_allow_html=True)
            orig_passage = d.get("passage") or ""
            if orig_passage:
                with st.container(border=True):
                    st.caption("📄 النص الرئيسي (مشترك بين الأسئلة الفرعية)")
                    st.markdown(_box(orig_passage, lang), unsafe_allow_html=True)
            st.caption(f"السؤال الفرعي رقم {d.get('number') or q.get('number') or ''} — {QTYPE_AR.get(q['qtype'], '')}")
            link_choice = None
            with st.expander("✏️ تعديل النص الرئيسي أو ربطه بنص آخر" if orig_passage else "➕ إضافة نص رئيسي لهذا السؤال"):
                d_pass = st.text_area("النص الرئيسي (اتركه فارغًا إن لم يوجد نص)", orig_passage, height=140, key=f"{k}_p",
                                      help="تعديله يُحدّث الأسئلة الفرعية الأخرى المرتبطة بالنص نفسه. "
                                           "ضع [[ ]] حول الكلمات المسطَّرة.")
                if others:
                    opts_l = ["— بلا ربط —"] + [f"{t[:60]}…" for t in others.values()]
                    pick_l = st.selectbox("ربط السؤال بنص رئيسي آخر من هذا الامتحان", range(len(opts_l)),
                                          format_func=lambda i, o=opts_l: o[i], key=f"{k}_pl")
                    if pick_l > 0:
                        link_choice = list(others.items())[pick_l - 1]
            preview = st.container()          # ملخّص السؤال والإجابة والمصدر؛ يُملأ بعد قراءة الحقول أدناه

            with st.expander("✏️ تعديل نص السؤال" + (" والخيارات" if q["qtype"] == "mcq" else "")):
                d["question"] = st.text_area("نص السؤال", d["question"], key=f"{k}_q")
                if q["qtype"] == "mcq":
                    opts = [o.strip() for o in st.text_area("الخيارات (خيار في كل سطر)", "\n".join(d.get("options") or []),
                                                            key=f"{k}_o").splitlines() if o.strip()]
                    d["options"] = opts
            opts = d.get("options") or []
            if q["qtype"] in ANSWER_TYPES:
                with st.expander("✏️ تعديل الإجابة"):
                    if q["qtype"] == "mcq":
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
                        d["model_answer"] = st.text_area("الإجابة النموذجية", d.get("model_answer") or "",
                                                         key=f"{k}_a").strip() or None
            else:
                with st.expander("✏️ تعديل الإجابة النموذجية (اختياري)"):
                    d["model_answer"] = st.text_area("الإجابة النموذجية", d.get("model_answer") or "",
                                                     key=f"{k}_a").strip() or None
            with st.expander("📍 الصفحات والدروس التي أُخذت منها الإجابة"):
                sp_default = ", ".join(str(p) for p in (d.get("source_pages") or []))
                sp_raw = st.text_input("أرقام الصفحات المطبوعة في الكتاب (مفصولة بفواصل)", sp_default, key=f"{k}_sp",
                                       help="الأرقام المطبوعة على صفحات الكتاب نفسها. تُنقل مع السؤال إلى بنك «قيّمني».")
                d["source_pages"] = sorted({int(x) for x in re.findall(r"\d+", sp_raw)})
                cur_l = lesson_titles.index(q["lesson_title"]) if q.get("lesson_title") in lesson_titles else 0
                les = st.selectbox("الدرس المرتبط", lesson_titles, index=cur_l, key=f"{k}_l")
            with st.expander("🖼️ صورة السؤال والعلامة"):
                rm_img, up_img = False, None
                if d.get("image_id"):
                    cur_img = images.load(d["image_id"])
                    if cur_img:
                        st.image(cur_img, width=320)
                    rm_img = st.checkbox("حذف صورة السؤال", key=f"{k}_rmimg")
                up_img = st.file_uploader("إضافة أو استبدال صورة السؤال (اختياري)", type=["png", "jpg", "jpeg"], key=f"{k}_img")
                d["marks"] = st.number_input("العلامة", 0.0, 100.0, float(d.get("marks") or 0.0), 0.5, key=f"{k}_m") or None

            # ---- الملخّص (بالقيم الحالية في الحقول)
            with preview:
                st.markdown(_box(d["question"], lang, bold=True), unsafe_allow_html=True)
                if d.get("image_id"):
                    _pi = images.load(d["image_id"])
                    if _pi:
                        st.image(_pi, width=260)
                if q["qtype"] == "mcq":
                    for i, o in enumerate(opts[:5]):
                        mark = "✅ " if d.get("correct_index") == i else ""
                        st.markdown(_box(f"{mark}{letters[i]}) {o}", lang), unsafe_allow_html=True)
                    if d.get("correct_index") is None:
                        st.caption("— لم تُحدَّد الإجابة الصحيحة بعد —")
                elif q["qtype"] == "tf":
                    st.markdown("الإجابة: " + {None: "— غير محددة —", True: "**صح**", False: "**خطأ**"}[d.get("correct")])
                elif d.get("model_answer"):
                    st.markdown("**الإجابة:** ")
                    st.markdown(_box(d["model_answer"], lang), unsafe_allow_html=True)
                src_bits = []
                if d.get("source_pages"):
                    src_bits.append("صفحة " + "، ".join(str(p) for p in d["source_pages"]))
                lesson_now = None if les == lesson_titles[0] else les
                if lesson_now:
                    src_bits.append(lesson_now)
                if src_bits:
                    st.caption("📍 المصدر: " + " — ".join(src_bits))
                if q["qtype"] in ANSWER_TYPES and d.get("ai_answer"):
                    conf = {"high": "عالية", "medium": "متوسطة", "low": "منخفضة"}.get(d.get("ai_conf"), "")
                    st.warning(f"🤖 إجابة مقترحة من الذكاء الاصطناعي (الثقة: {conf})"
                               + (f" — {d['ai_note']}" if d.get("ai_note") else "") + ". راجعها وعدّلها إن لزم قبل الاعتماد.")

            if q["qtype"] in ANSWER_TYPES and st.button("🤖 اقتراح الإجابة والمصدر لهذا السؤال", key=f"{k}_ai"):
                now_row = {"id": q["id"], "qtype": q["qtype"], "lesson_title": q.get("lesson_title"),
                           "data": {**q["data"], "question": d["question"], "options": d.get("options"),
                                    "passage": (link_choice[1] if link_choice else d_pass.strip()) or None}}
                with st.spinner("جارٍ اقتراح الإجابة..."):
                    got_n, _t, _f = _apply_ai(user, [now_row], replace_existing=True, ctx=ai_ctx)
                st.session_state[f"mainote_{slug}"] = ("اقتُرحت إجابة للسؤال؛ راجعها." if got_n
                                                       else "لم يستطع الذكاء الاصطناعي تحديد إجابة موثوقة لهذا السؤال.")
                st.rerun()
            b1, b2 = st.columns(2)

            def _patch(d=d, les=les, up_img=up_img, rm_img=rm_img, d_pass=d_pass, link_choice=link_choice,
                       orig_passage=orig_passage, q=q, siblings_all=siblings_all):
                for _f in ("ai_answer", "ai_conf", "ai_note", "ai_lessons"):    # اعتمده مراجع بشري
                    d.pop(_f, None)
                if not d.get("source_pages"):
                    d.pop("source_pages", None)
                key = d.get("passage_key")
                if link_choice:                                  # ربط بنص موجود
                    key, final = link_choice
                else:
                    final = d_pass.strip()
                if final:
                    key = key or f"p{q['id']}"
                    d["passage"], d["passage_key"] = final, key
                    if not link_choice and final != orig_passage.strip():   # مزامنة بقية الأسئلة الفرعية
                        for r in siblings_all:
                            if r["id"] != q["id"] and r["data"].get("passage_key") == key:
                                update_question(r["id"], {"data": {**r["data"], "passage": final}})
                else:
                    d.pop("passage", None)
                    d.pop("passage_key", None)
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


def to_qbank_item(row, lesson_ranges, page_offset=0):
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
    if d.get("source_pages"):                  # الصفحة المصدر بترقيم ملف الكتاب (كما يخزّنها بنك الأسئلة الأخرى)
        q["page"] = int(d["source_pages"][0]) + int(page_offset or 0)
        q["page_printed"] = int(d["source_pages"][0])
    if d.get("passage"):                       # السؤال الفرعي ينتقل مع نصه الرئيسي ليُفهم وحده
        q["passage"] = d["passage"]
        q["passage_key"] = d.get("passage_key") or f"p{row['id']}"
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
        item, why = to_qbank_item(r, ranges, book.get("page_offset", 0))
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


def _reading_section(book, flat_lessons, user, lang, idx):
    """نموذج إدخال نصوص القراءة (عربية أو إنجليزية) يدويًا للمدير والمشرف. الدرس الواحد قد يحوي أكثر من نص بموضوعات مختلفة،
    ولكل نص عنوانه، وكل سؤال يُبنى على نص واحد منها ويعرض الطالب ذلك النص وحده."""
    slug = book["slug"]
    st.caption("أضف نصوص أي درس بتنسيق الكتاب (سطر الكتاب = سطر، والفقرة تُفصل بسطر فارغ). **لكل نص عنوانه** وإن كان في الدرس "
               "أكثر من نص فأضف كلًّا منه على حدة: تُبنى أسئلة القراءة على نص واحد، ويعرض «قيّمني» ذلك النص وحده، وتطبع "
               "ورقة الاختبار كل نص مرة واحدة قبل أسئلته. يصلح للعربية والإنجليزية ولأي درس.")
    if not flat_lessons:
        st.info("لم تُدخل دروس هذا الكتاب بعد.")
        return
    reading_texts.input_direction_css(lang)
    saved = reading_texts.list_rows(slug)
    mark = {"ai": "🤖", "manual": "✅"}
    titles = [l["title"] for l in flat_lessons]
    only_read = lang == "en" and st.checkbox("إظهار دروس القراءة فقط (Reading / Culture / Literature)", value=True,
                                              key=f"rtonly_{slug}")
    if only_read:
        titles = [t for t in titles if sp.lesson_kind(t) in sp.PASSAGE_KINDS or t in saved]
    if not titles:
        st.info("لا توجد دروس مطابقة. ألغِ الفلتر لعرض كل الدروس.")
        return
    sel = st.selectbox("الدرس", titles, key=f"rtsel_{slug}",
                       format_func=lambda t: (f"{mark.get(saved[t]['source'], '✅')} {t} — {saved[t]['count']} نص"
                                              if t in saved else f"⬜ {t}"))
    lesson = next(l for l in flat_lessons if l["title"] == sel)
    k = f"rt_{slug}_{abs(hash(sel)) % 10**8}"
    rows = reading_texts.texts_of(slug, sel)
    ver = st.session_state.get(f"{k}_ver", 0)          # يتغير بعد كل حفظ لتفريغ حقول النص الجديد

    # ---- النصوص الحالية للدرس
    st.markdown(f"**نصوص هذا الدرس: {len(rows)}**" if rows else "**لا توجد نصوص لهذا الدرس بعد.**")
    for r in rows:
        kr = f"{k}_{r['key']}"
        with st.expander(f"{mark.get(r['source'], '✅')} {reading_texts.display_title(lesson, r, rows)}",
                         expanded=len(rows) == 1):
            with st.container(border=True):
                reading_texts.show({**r, "title": reading_texts.display_title(lesson, r, rows) if r.get("title") else None},
                                   lang)
            t_new = st.text_input("📄 عنوان النص", r.get("title") or "", key=f"{kr}_ti")
            x_new = st.text_area("📄 النص", r["text"], height=260, key=f"{kr}_t",
                                 help="الصق النص كما في الكتاب. اترك سطرًا فارغًا بين الفقرات. في الشعر: كل بيت/شطر في سطر.")
            b1, b2 = st.columns(2)
            if b1.button("💾 حفظ التعديل", key=f"{kr}_s", type="primary", disabled=not x_new.strip()):
                reading_texts.save_text(slug, sel, r["key"], t_new.strip() or None, x_new.strip(), "manual", user["id"])
                st.rerun()
            if b2.button("🗑️ حذف هذا النص", key=f"{kr}_d"):
                reading_texts.delete_text(slug, sel, r["key"])
                st.rerun()

    # ---- إضافة نص جديد
    with st.container(border=True):
        st.markdown("**➕ إضافة نص جديد إلى هذا الدرس**")
        n_title = st.text_input("📄 عنوان النص (يُنصح به إن كان في الدرس أكثر من نص)", key=f"{k}_nt{ver}")
        n_text = st.text_area("📄 النص", height=220, key=f"{k}_nx{ver}",
                              help="الصق النص كما في الكتاب. اترك سطرًا فارغًا بين الفقرات. في الشعر: كل بيت/شطر في سطر.")
        if st.button("💾 حفظ كنص جديد", key=f"{k}_add{ver}", type="primary", disabled=not n_text.strip()):
            reading_texts.save_text(slug, sel, None, n_title.strip() or None, n_text.strip(), "manual", user["id"])
            st.session_state[f"{k}_ver"] = ver + 1
            st.rerun()

    # ---- تمارين الدرس
    with st.expander("📝 تمارين الدرس أو ملاحظات للاستئناس عند توليد الأسئلة (اختياري)"):
        ex_new = st.text_area("📄 التمارين", reading_texts.exercises_of(slug, sel), height=140, key=f"{k}_ex")
        if st.button("💾 حفظ التمارين", key=f"{k}_exs"):
            reading_texts.save_exercises(slug, sel, ex_new, user["id"])
            st.rerun()

    # ---- مساعدة اختيارية
    if idx is not None:
        with st.expander("🤖 استخراج النصوص من صفحات الكتاب بالذكاء الاصطناعي (اختياري)"):
            ok = True
            if rows:
                ok = st.checkbox("أؤكد استبدال النصوص الحالية لهذا الدرس بالمستخرَجة", key=f"{k}_rep")
            if st.button("🤖 استخراج", key=f"{k}_ai", disabled=not ok):
                auth_ui.require_quota_or_stop(user)
                with st.spinner("جارٍ استخراج النصوص..."):
                    got = reading_texts.extract_with_ai(get_client(), idx, lesson)
                if got:
                    reading_texts.replace_lesson(slug, sel, got[0], got[1], "ai", user["id"])
                    st.rerun()
                else:
                    st.error("لم يُعثر على نص قراءة في صفحات هذا الدرس. أدخله يدويًا أعلاه.")
        with st.expander("📋 النص الخام لصفحات هذا الدرس (للنسخ منه)"):
            raw = "\n\n".join(f"--- صفحة {p['page'] - int(lesson.get('page_offset') or 0)} ---\n{p['text']}"
                               for p in select_context(idx, sel, (lesson["start"], lesson["end"]), max_chars=200000))
            st.text_area("النص كما استُخرج من ملف الكتاب", raw, height=240, key=f"{k}_raw")
    if saved:
        with st.expander(f"📑 الدروس التي لها نصوص ({len(saved)})"):
            for t, v in saved.items():
                st.write(f"{mark.get(v['source'], '✅')} {t} — {v['count']} نص، {v['words']} كلمة")


def _grammar_section(book, flat_lessons, user, lang, idx):
    slug = book["slug"]
    st.caption("شرح مبسّط وشامل لقاعدة كل درس Grammar من **مصادر خارجية غير المنهاج** (شرح عربي وأمثلة إنجليزية)، يُولَّد مرة واحدة "
               "بالبحث في الإنترنت ثم يُعرض للطالب في «اشرح لي». راجعه وعدّله هنا، أو أعد توليده.")
    if lang != "en":
        st.info("هذه الميزة لكتب اللغة الإنجليزية.")
        return
    lessons = [l for l in flat_lessons if sp.lesson_kind(l["title"]) in grammar_ext.GRAMMAR_KINDS]
    if not lessons:
        st.info("لا توجد دروس قواعد (Grammar) في هذا الكتاب.")
        return
    rows = grammar_ext.list_rows(slug)
    sel = st.selectbox("الدرس", [l["title"] for l in lessons], key=f"gx_sel_{slug}",
                       format_func=lambda t: (("✅ " if rows[t].get("source") == "manual" else "🤖 ") + t) if t in rows else "⬜ " + t)
    lesson = next(l for l in lessons if l["title"] == sel)
    k = f"gx_{slug}_{abs(hash(sel)) % 10**8}"
    row = rows.get(sel)
    if row:
        with st.container(border=True):
            st.markdown(grammar_ext.render_md(row))
    else:
        st.info("لم يُولَّد شرح لهذا الدرس بعد (يُولَّد تلقائيًا عند أول طلب شرح، أو ولّده الآن).")
    if idx is not None and st.button("🔎 توليد / إعادة توليد الشرح بالبحث في الإنترنت", key=f"{k}_gen"):
        auth_ui.require_quota_or_stop(user)
        with st.spinner("جارٍ البحث وإعداد الشرح..."):
            got = grammar_ext.generate(get_client(), idx, lesson)
        if got:
            grammar_ext.save_row(slug, sel, got[0], got[1], got[2], "ai", user["id"])
            st.session_state.pop(f"{k}_txt", None)
            st.rerun()
        else:
            st.error("تعذّر إعداد الشرح. حاول مرة أخرى.")
    txt = st.text_area("تعديل الشرح (Markdown)", (row or {}).get("content") or "", height=320, key=f"{k}_txt")
    c1, c2 = st.columns(2)
    if c1.button("💾 حفظ كشرح معتمد", key=f"{k}_save", type="primary", disabled=not txt.strip()):
        grammar_ext.save_row(slug, sel, (row or {}).get("title"), txt.strip(), (row or {}).get("sources"), "manual", user["id"])
        st.rerun()
    if row and c2.button("🗑️ حذف الشرح", key=f"{k}_del"):
        grammar_ext.delete_row(slug, sel)
        st.session_state.pop(f"{k}_txt", None)
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


def render_ministry(book, flat_lessons, user, lang="ar", idx=None):
    st.subheader("📜 أسئلة وزارية سابقة")
    can_manage = _can_manage(user, book)
    if not can_manage:
        if not is_visible(book["slug"]):
            st.info("هذا البنك غير متاح حاليًا لهذا المبحث.")
            return
        _bank_tab(book, user, False, lang)
        return
    t1, t2, t4, t5, t6, t3 = st.tabs(["📚 البنك", "⬆️ رفع ومراجعة", "🏦 نقل إلى بنك قيّمني", "📄 نصوص القراءة",
                                      "📘 شرح القواعد", "🎯 نمط الأسئلة"])
    with t1:
        _bank_tab(book, user, True, lang)
    with t2:
        _upload_section(book, flat_lessons, user)
        st.markdown("---")
        _review_section(book, flat_lessons, user, lang, idx)
    with t4:
        _transfer_section(book, flat_lessons, user)
    with t5:
        _reading_section(book, flat_lessons, user, lang, idx)
    with t6:
        _grammar_section(book, flat_lessons, user, lang, idx)
    with t3:
        _style_section(book, user, lang)
