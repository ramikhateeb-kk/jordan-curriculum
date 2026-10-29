"""
ميزة (قيمني): أسئلة سؤالًا تلو الآخر من درس أو أكثر (حتى من وحدات مختلفة)، مع تقييم فوري.
لتقليل طلبات Gemini: تُخزَّن الأسئلة المولَّدة في قاعدة بيانات (qbank)، وقبل توليد أي سؤال جديد
يُفحص إن كان مخزَّنًا سلفًا لهذا الدرس ونوع السؤال، وتُختار الأسئلة عشوائيًا فلا يتكرر ترتيبها نفسه لكل طالب.
تقييم الإجابات الكتابية يستخدم الإجابة النموذجية والتوضيح المحفوظين فقط، دون إعادة إرسال نص الدرس، لتقليل التوكنز.
"""
import json
import random
import re

import streamlit as st
from google.genai import types

import html as _html
import re as _re

import companion
import catalog
import prompts as prompt_store
import images
import rag
import ministry
import qbank
import reading_texts
import subject_profiles as sp
from config import GEMINI_MODEL
from rag import get_client, select_context

QTYPES = {
    "اختيار من متعدد": "mcq",
    "صح أو خطأ": "tf",
    "أكمل الفراغ": "fill",
    "سؤال قصير": "short",
    "مختلط": "mixed",
}

SYSTEM = (
    "أنت معلم للمنهاج الأردني يضع أسئلة تقويمية دقيقة. التزم بالآتي بصرامة:\n"
    "1) استخدم فقط نص الكتاب المرفق، ولا تستخدم أي معلومة من خارجه، ولا تخترع تفاصيل ليست فيه.\n"
    "2) يجب أن تكون إجابة السؤال موجودة صراحة في النص المرفق، لا مُستنتجة أو مُخمَّنة.\n"
    "3) اكتب بالعربية الفصحى الواضحة، وضع رقم الصفحة التي أخذت منها السؤال بدقة.\n"
    "4) في الاختيار من متعدد اجعل الخيارات الثلاثة الخاطئة معقولة، لكن غير موجودة في النص كإجابة صحيحة.\n"
    "أعد JSON فقط بلا أي نص آخر."
)
def _md_u(text):
    """يعرض النص؛ وما بين [[ ]] يظهر مسطَّرًا (الكلمات المسطَّرة في الأسئلة الوزارية)."""
    text = str(text)
    if "[[" not in text:
        st.markdown(text)
        return
    esc = _re.sub(r"\[\[(.+?)\]\]", r"<u>\1</u>", _html.escape(text), flags=_re.S).replace("\n", "<br>")
    st.markdown(esc, unsafe_allow_html=True)


SYSTEM_EN = (
    "You are a teacher of the Jordanian curriculum writing accurate assessment questions in English. Follow strictly:\n"
    "1) Use ONLY the attached book text; do not use outside information or invent details.\n"
    "2) The answer must be explicitly supported by the attached text, not inferred or guessed.\n"
    "3) Write clear English and give the exact page number you took the question from.\n"
    "4) For multiple choice, make the three wrong options plausible but not correct according to the text.\n"
    "5) Practice material from the workbook, if provided, is only a guide to question types and language points; "
    "the page number must be a page of the book text, never of the workbook.\n"
    "Return JSON only, no other text."
)
GRADE_SYSTEM = (
    "أنت مصحّح دقيق. قارن إجابة الطالب بالإجابة النموذجية المعطاة فقط (لا مصدر آخر عندك). "
    "اقبل اختلاف الصياغة والمرادفات ما دام المعنى صحيحًا. أعد JSON فقط بلا أي نص آخر."
)

CONTEXT_BUDGET = 30000  # حد أقصى لطول نص الدرس المُرسَل عند توليد سؤال جديد (لا يُستخدم عند التصحيح)

SPECS_EN = {
    "mcq": "a multiple-choice question with four options and exactly one correct answer",
    "tf": "a statement the student judges as true or false",
    "fill": "a fill-in-the-blank sentence with exactly one blank written ______ whose answer is a word or short phrase",
    "short": "a short question answered in one or two sentences",
    "writing": "an extended free-writing task requiring a paragraph, essay, email, report, or other genre explicitly taught in the lesson, with a model response and marking rubric",
}

SPECS = {
    "mcq": ('سؤال اختيار من متعدد بأربعة خيارات وإجابة صحيحة واحدة فقط',
            '{"type":"mcq","question":"...","options":["...","...","...","..."],'
            '"correct_index":0,"explanation":"...","page":12}'),
    "tf": ('عبارة يحكم عليها الطالب بالصواب أو الخطأ',
           '{"type":"tf","question":"عبارة ...","correct":true,"explanation":"...","page":12}'),
    "fill": ('سؤال أكمل الفراغ: جملة من الكتاب فيها فراغ واحد مكتوب ______ وإجابته كلمة أو عبارة قصيرة',
             '{"type":"fill","question":"... ______ ...","model_answer":"...","explanation":"...","page":12}'),
    "short": ('سؤال قصير يُجاب عنه بجملة أو جملتين',
              '{"type":"short","question":"...","model_answer":"...","explanation":"...","page":12}'),
    "writing": ('مهمة كتابة حرة تطلب نصًا ممتدًا من النوع الذي يدرّسه الدرس، مع إجابة نموذجية وسلم تصحيح',
                 '{"type":"writing","question":"Write ...","model_answer":"A complete model text ...","marking_rubric":{"task_achievement":"...","organisation":"...","grammar":"...","vocabulary":"...","register":"..."},"explanation":"...","page":12}'),
}


def _json(client, system, prompt, temperature=0.4):
    for _ in range(2):
        try:
            r = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=temperature,
                    response_mime_type="application/json"))
            txt = re.sub(r"^```(?:json)?|```$", "", r.text.strip()).strip()
            return json.loads(txt)
        except Exception as e:  # noqa: BLE001
            print("خطأ في توليد/قراءة JSON:", e)
    return None


def _valid(q, qtype, ctx_pages):
    if not isinstance(q, dict) or not str(q.get("question", "")).strip():
        return False
    valid_pages = {p["page"] for p in ctx_pages}
    if q.get("page") is not None and int(q.get("page", -1)) not in valid_pages:
        return False  # رقم صفحة غير موجود فعلًا في النص المُرسَل: نرفض السؤال
    if qtype == "mcq":
        o = q.get("options")
        return isinstance(o, list) and len(o) == 4 and len(set(map(str, o))) == 4 \
            and isinstance(q.get("correct_index"), int) and 0 <= q["correct_index"] < 4
    if qtype == "tf":
        return isinstance(q.get("correct"), bool)
    if qtype == "writing":
        return bool(str(q.get("model_answer", "")).strip()) and isinstance(q.get("marking_rubric", {}), dict)
    return bool(str(q.get("model_answer", "")).strip())


def _finalize(q, qtype, lesson=None):
    """يثبّت نوع السؤال ويخلط خيارات الاختيار من متعدد، ويسجّل رقم الصفحة المطبوعة (للعرض للطالب)."""
    q["type"] = qtype
    if lesson is not None and lesson.get("page_offset") is not None and q.get("page") is not None:
        q["page_printed"] = int(q["page"]) - int(lesson["page_offset"])
    if qtype == "mcq":
        correct = str(q["options"][q["correct_index"]])
        opts = [str(o) for o in q["options"]]
        random.shuffle(opts)
        q["options"], q["correct_index"] = opts, opts.index(correct)
    return q


def _save(slug, lesson, qtype, q):
    try:
        return qbank.add_question(slug, lesson["start"], lesson["end"], qtype, q)
    except Exception as e:  # noqa: BLE001
        print("تعذّر حفظ السؤال في قاعدة البيانات:", e)  # لا نوقف التقييم بسبب هذا
        return None


def _generate_passage(client, idx, slug, lesson, qtype, asked_texts, passage, style):
    """درس قراءة (إنجليزي): يعرض قطعة حرفية من الكتاب ثم سؤالًا عليها بأنماط الامتحان الوزاري. يعيد (سؤال، معرّف) أو None
    إن لم توجد قطعة نثرية في الدرس (فيُستعمل التوليد العادي)."""
    passage = passage or sp.pick_passage(idx, lesson, avoid=lesson.get("_seen_passages", ()))
    if not passage:
        return None
    schema = SPECS[qtype][1].replace('"page":12}', '"page":12,"underline":null}')
    asked = "\n".join(f"- {a}" for a in asked_texts) or "none"
    prompt = sp.reading_prompt(lesson, passage, qtype, asked, schema, sp.glossary_of(idx, lesson, passage["page"]), style)
    ctx_pages = [{"page": passage["page"], "text": passage["text"]}]
    for _ in range(2):
        q = _json(client, sp.SYSTEM_READING_EN, prompt)
        if isinstance(q, dict):
            q["page"] = passage["page"]
        if _valid(q, qtype, ctx_pages) and not ministry.too_similar(slug, str(q.get("question", ""))):
            marked = sp.apply_underline(passage["text"], q.pop("underline", None))
            if "underlined" in str(q.get("question", "")).lower() and not marked:
                continue          # سؤال عن كلمة مسطَّرة لا يمكن تسطيرها في القطعة المعروضة: نرفضه ونعيد المحاولة
            q["passage"] = marked or passage["text"]
            q["passage_key"] = passage["key"] + (f"-u{random.randint(10, 99)}" if marked else "")
            _finalize(q, qtype, lesson)
            return q, _save(slug, lesson, qtype, q)
    return None


def _generate_reference(client, idx, slug, lesson, qtype, asked_texts, style, lang="en"):
    """درس قراءة (إنجليزي/عربي): سؤال محايد يشير إلى النص دون ذكر عنوانه أو صفحته (يُضيفهما النظام)، ويُحفظ مرجعه منفصلًا.
    المصدر: النص المحفوظ للدرس (المستخرج أو المُدخَل يدويًا) مع صفحات الكتاب للتحقق من الصفحة والاقتباسات."""
    off = int(lesson.get("page_offset") or 0)
    pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=CONTEXT_BUDGET)
    rows = reading_texts.get_texts(slug, lesson, idx)               # نصوص الدرس (قد يكون فيه أكثر من نص بموضوعات مختلفة)
    chosen = None
    if rows:                                                        # نسأل عن نص واحد في كل سؤال، ونتجنّب تكرار النص السابق
        pool = [r for r in rows if r["key"] != lesson.get("_last_text")] or rows
        chosen = random.choice(pool)
        lesson["_last_text"] = chosen["key"]
    clean = ((chosen or {}).get("text") or "").strip()
    raw_words = len(sp.fix_ligatures(" ".join(p["text"] for p in pages)).split())
    if not clean and raw_words < 60:
        return None                                    # لا يوجد نص كافٍ في الدرس
    blocks = []
    if clean:
        head = reading_texts.display_title(lesson, chosen, rows)
        note = (f" The lesson has {len(rows)} different texts; the question must be about THIS text only."
                if len(rows) > 1 else "")
        blocks.append(f"READING TEXT \"{head}\" (as printed in the book).{note}\n" + clean)
    if pages:
        blocks.append("BOOK PAGES (with PRINTED page numbers):\n" + "\n\n".join(
            f"=== page {p['page'] - off} ===\n{sp.fix_ligatures(p['text'])}" for p in pages))
    schema = SPECS[qtype][1].replace('"page":12}', '"page":6,"quotes":[]}')
    asked = "\n".join(f"- {a}" for a in asked_texts) or ("none" if lang == "en" else "لا يوجد")
    exercises = (reading_texts.exercises_of(slug, lesson["title"]) + "\n\n" + companion.exercises_text(lesson, 3000)).strip()
    if lang == "ar":
        system, prompt = sp.SYSTEM_REFERENCE_AR, sp.reference_prompt_ar(lesson, "\n\n".join(blocks), qtype, asked, schema,
                                                                       style, exercises)
    else:
        system, prompt = sp.SYSTEM_REFERENCE_EN, sp.reference_prompt(lesson, "\n\n".join(blocks), qtype, asked, schema,
                                                                      style, exercises)
    valid_printed = {p["page"] - off for p in pages}
    corpus = clean if clean else " ".join(p["text"] for p in pages)       # الاقتباس من النص المسؤول عنه السؤال
    for _ in range(2):
        q = _json(client, system, prompt)
        if not isinstance(q, dict):
            continue
        try:
            printed = int(q.get("page"))
        except (TypeError, ValueError):
            printed = None
        if printed is not None and printed not in valid_printed:
            printed = None                             # صفحة غير موجودة: نتجاهلها إن كان النص المحفوظ يكفي
        if printed is None and not clean:
            continue
        if not sp.quotes_ok(q.pop("quotes", None), corpus):
            continue                                   # اقتباس غير حرفي: نرفض ونعيد
        if re.search(r"(\bpages?\s*\d+|صفحة\s*\d+)", str(q.get("question", "")), re.I):
            continue                                   # النظام هو من يضيف الصفحة؛ لا تُكتب داخل السؤال
        q["page"] = (printed + off) if printed is not None else None
        ctx_ok = pages if printed is not None else [{"page": None, "text": ""}]
        if q["page"] is None:
            q.pop("page")
        if _valid(q, qtype, ctx_ok) and not ministry.too_similar(slug, str(q.get("question", ""))):
            q["ref_title"] = reading_texts.display_title(lesson, chosen, rows) if chosen else sp.text_title(lesson["title"])
            if chosen:
                q["ref_text_key"] = chosen["key"]
            q["ref_page"], q["ref_lesson"], q["ref_lang"] = printed, lesson["title"], lang
            _finalize(q, qtype, lesson)
            return q, _save(slug, lesson, qtype, q)
    return None


def _generate(client, idx, slug, lesson, qtype, asked_texts, passage=None):
    """يولّد سؤالًا جديدًا من نص الدرس، ويحفظه في قاعدة البيانات ليُعاد استخدامه لاحقًا.
    يعيد (السؤال، معرّفه الجديد في قاعدة البيانات أو None إن تعذّر الحفظ)."""
    desc, schema = SPECS[qtype]
    lang = lesson.get("lang", "ar")
    ctx_pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=CONTEXT_BUDGET)
    if not ctx_pages:
        return None, None
    style = ministry.style_snippet(slug, qtype, lang)              # نمط الأسئلة الوزارية (إن وُجد)
    kind = sp.lesson_kind(lesson["title"]) if lang == "en" else None
    stored = reading_texts.texts_of(slug, lesson["title"])         # نصوص قراءة محفوظة لهذا الدرس (آليًا أو يدويًا، أي لغة)
    if kind in sp.PASSAGE_KINDS or stored:
        if sp.READING_MODE == "reference" or lang != "en":         # سؤال يشير إلى النص (الافتراضي)
            res = _generate_reference(client, idx, slug, lesson, qtype, asked_texts, style, lang)
        else:                                                      # عرض قطعة حرفية ثم سؤال عليها
            res = _generate_passage(client, idx, slug, lesson, qtype, asked_texts, passage, style)
        if res is not None:
            return res
    practice = companion.exercises_text(lesson)                    # تمارين الكتاب المرافق (إن وُجد نظير للدرس)
    asked = "\n".join(f"- {a}" for a in asked_texts) or ("none" if lang == "en" else "لا يوجد")
    if lang == "en":
        ctx = "\n\n".join(f"=== Page {p['page']} ===\n{p['text']}" for p in ctx_pages)
        # استرجاع برومت التقييم المحفوظ حسب المبحث والصف والفصل؛ لا يعتمد على برومت ثابت داخل الكود فقط.
        try:
            _book = next((b for b in catalog.list_books() if b.get("slug") == slug and not b.get("parent_slug")), {})
            _subject_prompt = prompt_store.get_prompt(_book.get("subject", "English Language"),
                                                      _book.get("grade", 11), _book.get("semester", 1), slug=slug)
        except Exception as _prompt_error:
            print("تعذّر تحميل برومت المبحث، سيستخدم النظام تعليمات الإنجليزية الافتراضية:", _prompt_error)
            _subject_prompt = prompt_store.DEFAULT_EN_G11_PROMPT
        # Prompt مخصص لمبحث اللغة الإنجليزية/الصف الأول الثانوي، مع تمرير الدرس المرتبط من كتاب الأنشطة عند توفره.
        lesson_type = "TYPE A — comprehensive (reading/writing workshop)" if kind in ("reading", "writing", "culture", "literature") else "TYPE B — focused language lesson"
        prompt = (
            f"Subject: English Language — Jordan High Note, Grade 11 (Tawjihi 2025/2026)\n"
            f"Unit/Lesson: {lesson['title']}\nLesson classification hint: {lesson_type}\n"
            f"Requested item type: {SPECS_EN[qtype]}\n\n"
            f"STUDENT'S BOOK — primary curriculum source; page numbers below are the indexed book pages:\n{ctx}\n\n"
            + (f"LINKED WORKBOOK LESSON — paired by unit/lesson number; use to identify aligned practice, exceptions and question styles. "
               f"Do not silently attribute workbook material to the Student's Book:\n{practice}\n\n" if practice else
               "No matching Workbook lesson was found. Use the Student's Book only and do not claim that a Workbook source exists.\n\n")
            + (f"Official Ministry-style reference (style guidance only):\n{style}\n\n" if style else "")
            + f"LESSON-SPECIFIC QUESTION PATTERN GUIDANCE:\n{sp.en_guidance(kind)}\n\n"
            + f"ACTIVE SUBJECT PROMPT FROM THE ADMIN DATABASE (authoritative subject-specific policy):\n{_subject_prompt}\n\n"
            + "Rules: focused grammar/vocabulary/functions lessons produce MCQs only; a lesson whose actual task is free writing MUST produce a writing task, not an MCQ. "
            + "For any MCQ, provide exactly four distinct options and exactly one correct answer. "
            "Use a contextual clue in each newly written sentence; distractors should reflect common learner errors. Do not create an outside reading passage. "
            "For Reading questions, use only the actual textbook passage and follow the app's short-answer reading mode. "
            "Provide a concise explanation/rationale and a real printed page reference; never invent page numbers. "
            "If the answer is supported by Student's Book text, set source_book to 'Student's Book'. If the item genuinely depends on a Workbook page, "
            "set source_book to 'Workbook'. Add source_page only when that printed page is explicitly identifiable in the supplied material. "
            "The app's current schema uses page for the verified Student's Book page; keep page valid and do not substitute a Workbook page into it.\n\n"
            f"Do not repeat these existing questions for this lesson:\n{asked}\n\n"
            f"Return JSON in exactly this format (add source_book and source_page only when verifiable):\n{schema}")
        system = sp.SYSTEM_EN + "\n\nADMIN-DEFINED SUBJECT PROMPT: Follow this prompt for lesson-type decisions and output behavior, together with the exact JSON schema supplied in the user prompt.\n" + _subject_prompt
    else:
        ctx = "\n\n".join(f"=== صفحة {p['page']} ===\n{p['text']}" for p in ctx_pages)
        prompt = (
            f"الدرس: {lesson['title']}\n\nنص من الكتاب (المصدر الوحيد المسموح به):\n{ctx}\n\n"
            + (f"تمارين الكتاب المرافق لهذا الدرس (للاسترشاد بأنواع الأسئلة فقط، ورقم الصفحة من الكتاب الأساسي):\n{practice}\n\n" if practice else "")
            + (f"{style}\n\n" if style else "")
            + f"أنشئ {desc}، اعتمادًا على هذا النص فقط.\n"
            f"لا تكرر هذه الأسئلة الموجودة سلفًا لهذا الدرس:\n{asked}\n\n"
            f"أعد JSON بهذا الشكل بالضبط:\n{schema}")
        try:
            _book = next((b for b in catalog.list_books() if b.get("slug") == slug and not b.get("parent_slug")), {})
            _subject_prompt = prompt_store.get_prompt(_book.get("subject", lesson.get("subject", "")),
                                                      _book.get("grade", 0), _book.get("semester", 1), slug=slug)
        except Exception as _prompt_error:
            print("تعذّر تحميل برومت المبحث:", _prompt_error)
            _subject_prompt = "استخدم نص المنهاج المرفق فقط، والتزم بنوع السؤال المطلوب ومخطط JSON المحدد."
        system = SYSTEM + "\n\nتعليمات المبحث المحفوظة في قاعدة البيانات: اتبعها مع الالتزام بمخطط JSON المرسل.\n" + _subject_prompt
    for _ in range(2):
        q = _json(client, system, prompt)
        if _valid(q, qtype, ctx_pages) and not ministry.too_similar(slug, str(q.get("question", ""))):
            _finalize(q, qtype, lesson)
            # لا نعرض مرجعًا اختلقه النموذج: التحقق الحالي يثبت صفحة السؤال من صفحات Student's Book فقط.
            # صفحات Workbook تُستخدم للمطابقة ونمط التمرين، ولا تُنسب إليها الإجابة ما لم يوجد تحقق مستقل لها.
            q["source_book"] = "Student's Book"
            q["source_page"] = q.get("page_printed") or q.get("page")
            _finalize(q, qtype, lesson)
            return q, _save(slug, lesson, qtype, q)
    return None, None


PASSAGE_REUSE = 3          # أقصى عدد أسئلة متتالية على القطعة نفسها قبل الانتقال إلى قطعة أخرى


def _base_key(q):
    return str(q.get("passage_key") or "").split("-u")[0]


def _plain(text):
    return re.sub(r"\[\[(.+?)\]\]", r"\1", str(text), flags=re.S)


def _english_assessment_type(slug, lesson):
    """اختيار نوع السؤال بحسب محتوى الدرس: قراءة=قصير، كتابة حرة=writing، وبقية دروس اللغة=MCQ."""
    title = str(lesson.get("title", ""))
    is_english = "english" in str(slug or "").lower() or bool(re.search(r"\b(reading|vocabulary|grammar|listening|writing|speaking)\b", title, re.I))
    if not is_english:
        # اسم المبحث قد يكون في سجل الكتاب بينما المعرّف مشفر؛ يُتحقق منه في قاعدة الكتب.
        try:
            book = next((b for b in catalog.list_books() if b.get("slug") == slug), {})
            is_english = book.get("lang") == "en"
        except Exception:
            pass
    if not is_english:
        return None
    kind = sp.lesson_kind(title)
    if kind == "reading":
        return "short"
    if kind == "writing":
        return "writing"
    return "mcq"


def next_question(client, idx, slug, lessons, quiz):
    """يفحص أولًا قاعدة الأسئلة عبر الدروس المطلوبة، ويختار سؤالًا غير مستخدم إن وُجد.
    في تقييم الإنجليزية يُفرض short على دروس Reading وmcq على بقية الدروس، حتى عند اختيار عدة دروس."""
    if quiz.get("qtype") == "english_auto":
        possible = { _english_assessment_type(slug, lesson) for lesson in lessons }
        possible.discard(None)
        qtype = random.choice(sorted(possible)) if possible else "mcq"
        lessons = [lesson for lesson in lessons if _english_assessment_type(slug, lesson) == qtype]
    else:
        qtype = quiz["qtype"] if quiz["qtype"] != "mixed" else random.choice(["mcq", "tf", "fill", "short"])

    # --- 1) سؤال آخر على القطعة الحالية
    ps = quiz.get("passage")
    lesson_p = next((l for l in lessons if ps and l["title"] == ps["lesson"]), None)
    if ps and lesson_p and ps["n"] < PASSAGE_REUSE:
        bank = qbank.list_questions(slug, lesson_p["start"], lesson_p["end"], qtype)
        same = [(qid, d) for qid, d in bank if _base_key(d) == ps["key"] and qid not in quiz["asked_ids"]
                and d.get("question") not in quiz["asked_texts"]]
        if same:
            qid, data = random.choice(same)
            out = dict(data)
            out["_lesson"] = lesson_p["title"]
            quiz["asked_ids"].add(qid)
            ps["n"] += 1
            return out
        out, new_id = _generate(client, idx, slug, lesson_p, qtype, quiz["asked_texts"],
                                passage={"key": ps["key"], "text": ps["text"], "page": ps["page"]})
        if out:
            out["_lesson"] = lesson_p["title"]
            if new_id is not None:
                quiz["asked_ids"].add(new_id)
            ps["n"] += 1
            return out

    # --- 2) سؤال من البنك أو توليد جديد (قطعة جديدة في دروس القراءة)
    seen = quiz.setdefault("seen_passages", set())
    pool = []
    for lesson in lessons:
        bank = qbank.list_questions(slug, lesson["start"], lesson["end"], qtype)
        pool += [(lesson, qid, data) for qid, data in bank
                if qid not in quiz["asked_ids"] and data.get("question") not in quiz["asked_texts"]]
    fresh = [p for p in pool if not p[2].get("passage_key") or _base_key(p[2]) not in seen] or pool
    chosen = None
    if fresh:
        lesson, qid, data = random.choice(fresh)
        chosen = dict(data)
        chosen["_lesson"] = lesson["title"]
        quiz["asked_ids"].add(qid)
    else:
        for lesson in random.sample(lessons, len(lessons)):  # البنك فارغ لهذا النوع: نولّد سؤالًا جديدًا
            lesson["_seen_passages"] = seen
            q, new_id = _generate(client, idx, slug, lesson, qtype, quiz["asked_texts"])
            if q:
                q["_lesson"] = lesson["title"]
                if new_id is not None:  # نستثنيه فورًا حتى لا يُعرَض مجددًا بوصفه "من البنك" في السؤال التالي
                    quiz["asked_ids"].add(new_id)
                chosen = q
                break
    if chosen and chosen.get("passage_key"):               # نتذكر القطعة لسؤال لاحق عليها
        key = _base_key(chosen)
        seen.add(key)
        quiz["passage"] = {"lesson": chosen["_lesson"], "key": key, "text": _plain(chosen.get("passage", "")),
                           "page": chosen.get("page"), "n": 1}
    elif chosen:
        quiz["passage"] = None
    return chosen


def correct_text(q):
    if q["type"] == "mcq":
        return q["options"][q["correct_index"]]
    if q["type"] == "tf":
        return "صح" if q["correct"] else "خطأ"
    return q["model_answer"]


def grade(client, q, ans):
    """يعيد (الدرجة من 0 إلى 1، ملاحظة). الاختيار من متعدد وصح/خطأ محليًا بلا Gemini.
    الأسئلة الكتابية تُصحَّح بمقارنة إجابة الطالب بالإجابة النموذجية المحفوظة فقط (بلا إعادة إرسال نص الدرس)."""
    if q["type"] == "mcq":
        return (1.0 if ans == q["options"][q["correct_index"]] else 0.0), ""
    if q["type"] == "tf":
        return (1.0 if (ans == "صح") == q["correct"] else 0.0), ""
    prompt = (
        f"السؤال: {q['question']}\nالإجابة النموذجية: {q['model_answer']}\n"
        f"توضيح إضافي: {q.get('explanation', '')}\n"
        f"سلم تصحيح الكتابة إن وجد: {json.dumps(q.get('marking_rubric', {}), ensure_ascii=False)}\n"
        f"إجابة الطالب: {ans}\n\n"
        "قيّم المعنى والمحتوى والتنظيم والقواعد والمفردات ومدى الالتزام بالمطلوب عند وجود مهمة كتابة حرة. "
        "لا تشترط مطابقة الإجابة النموذجية حرفيًا، واقبل الإجابات الصحيحة البديلة. "
        "الدرجة: 1 إن كانت الإجابة صحيحة ومكتملة، 0.5 إن كانت صحيحة جزئيًا أو ناقصة، 0 إن كانت خاطئة أو خارج المطلوب. "
        'أعد JSON: {"score": 1, "feedback": "ملاحظة قصيرة ومشجعة"}')
    r = _json(client, GRADE_SYSTEM, prompt, temperature=0) or {}
    try:
        score = float(r.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score)), str(r.get("feedback", ""))


def render_quiz(idx, slug, lessons):
    """lessons: قائمة [{"title","start","end"}] اختارها الطالب، ويمكن أن تكون من وحدات مختلفة."""
    S = st.session_state
    if not lessons:
        st.info("اختر درسًا واحدًا على الأقل لتبدأ.")
        return

    sig = tuple(sorted((l["start"], l["end"]) for l in lessons))
    if S.get("quiz_sig") != sig:
        S.pop("quiz", None)
        S["quiz_sig"] = sig
    quiz = S.get("quiz")

    if quiz is None:
        st.subheader("اختبر نفسك")
        st.caption("الدروس المختارة: " + "، ".join(l["title"] for l in lessons))
        english_types = [_english_assessment_type(slug, lesson) for lesson in lessons]
        is_english_assessment = all(t is not None for t in english_types)
        if is_english_assessment:
            unique_types = set(english_types)
            if unique_types == {"short"}:
                st.info("نوع الأسئلة محدد تلقائيًا: أسئلة فهم مقروء قصيرة، لأن الدرس من نوع Reading.")
            elif unique_types == {"writing"}:
                st.info("نوع الأسئلة محدد تلقائيًا: مهمة كتابة حرة مع نموذج إجابة وسلم تصحيح، وليست اختيارًا من متعدد.")
            elif unique_types == {"mcq"}:
                st.info("نوع الأسئلة محدد تلقائيًا: اختيار من متعدد للدروس المركزة على القواعد والمفردات والوظائف اللغوية.")
            else:
                st.info("نوع السؤال يتبع الدرس: Reading = سؤال قصير، Writing = كتابة حرة، والدروس اللغوية المركزة = اختيار من متعدد.")
            qt = "english_auto"
        else:
            qt = QTYPES[st.selectbox("نوع الأسئلة", list(QTYPES))]
        n = st.number_input("عدد الأسئلة", min_value=1, value=5, step=1)
        if st.button("ابدأ التقييم", type="primary"):
            S["quiz"] = {"qtype": qt if is_english_assessment else qt, "n": int(n), "i": 0, "score": 0.0,
                         "asked_ids": set(), "asked_texts": [], "cur": None, "res": None, "hist": []}
            st.rerun()
        return

    if quiz["i"] >= quiz["n"]:
        pct = round(100 * quiz["score"] / quiz["n"]) if quiz["n"] else 0
        st.subheader("النتيجة النهائية")
        st.metric("الدرجة", f"{quiz['score']:g} / {quiz['n']}", f"{pct}%")
        if pct >= 85:
            st.success("ممتاز! مستواك رائع في هذه الدروس.")
        elif pct >= 60:
            st.info("جيد. راجع الأسئلة التي أخطأت فيها أدناه.")
        else:
            st.warning("تحتاج إلى مراجعة هذه الدروس، جرّب طلب شرحها ثم أعد التقييم.")
        with st.expander("مراجعة الأسئلة"):
            for k, h in enumerate(quiz["hist"], 1):
                icon = "✅" if h["score"] == 1 else ("🟡" if h["score"] > 0 else "❌")
                st.markdown(f"**{k}. {icon} {h['q']}**")
                st.write(f"إجابتك: {h['ans']}")
                st.write(f"الإجابة الصحيحة: {h['correct']}")
        if st.button("تقييم جديد"):
            S.pop("quiz", None)
            st.rerun()
        return

    client = get_client()
    if quiz["cur"] is None:
        with st.spinner("جارٍ إعداد السؤال..."):
            quiz["cur"] = next_question(client, idx, slug, lessons, quiz)
        if quiz["cur"] is None:
            if rag.recent_quota_error():
                st.error("تم تجاوز الحد المسموح لاستخدام الذكاء الاصطناعي مؤقتًا في كل النماذج المتاحة. حاول بعد دقيقة.")
            else:
                st.error("تعذّر إعداد سؤال موثّق من نص الدرس. حاول مرة أخرى.")
            if st.button("إعادة المحاولة"):
                st.rerun()
            return
        quiz["asked_texts"].append(quiz["cur"]["question"])
    q = quiz["cur"]

    st.progress(quiz["i"] / quiz["n"])
    st.markdown(f"**السؤال {quiz['i'] + 1} من {quiz['n']}** — {q.get('_lesson', '')}")
    if q.get("ref_title"):                         # سؤال على نص قراءة: يُذكر اسمه وصفحته، والنص الكامل عند الطلب
        if q.get("ref_lang") == "ar":
            st.caption(f'📖 من خلال قراءتك لنص «{q["ref_title"]}»' + (f" (صفحة {q['ref_page']})" if q.get("ref_page") else ""))
        else:
            st.caption(f'📖 From your reading of "{q["ref_title"]}"' + (f" (page {q['ref_page']})" if q.get("ref_page") else ""))
        _ref = next((l for l in lessons if l["title"] == q.get("ref_lesson")), None)
        _rows = reading_texts.get_texts(slug, _ref, idx) if _ref else []
        _mine = [r for r in _rows if r["key"] == q.get("ref_text_key")] or (_rows if len(_rows) == 1 or not q.get("ref_text_key") else [])
        if _mine:
            with st.expander("📄 عرض النص"):
                for _r in _mine:                                   # نص السؤال وحده؛ وإن لم يُعرف النص (سؤال قديم) كل نصوص الدرس
                    reading_texts.show({**_r, "title": reading_texts.display_title(_ref, _r, _rows)}, q.get("ref_lang") or "en")
    if q.get("passage"):
        with st.container(border=True):
            _md_u(q["passage"])
    _md_u(q["question"])
    if q.get("image_id"):
        _img = images.load(q["image_id"])
        if _img:
            st.image(_img, width=380)

    if quiz["res"] is None:
        key = f"ans_{quiz['i']}"
        if q["type"] == "mcq":
            ans = st.radio("اختر الإجابة", q["options"], index=None, key=key)
        elif q["type"] == "tf":
            ans = st.radio("الحكم", ["صح", "خطأ"], index=None, key=key, horizontal=True)
        elif q["type"] == "fill":
            ans = st.text_input("اكتب الكلمة أو العبارة المناسبة", key=key)
        else:
            ans = st.text_area("اكتب إجابتك", key=key)
        c1, c2 = st.columns([3, 1])
        if c1.button("أجب", disabled=not (ans and str(ans).strip())):
            with st.spinner("جارٍ تقييم إجابتك..."):
                score, fb = grade(client, q, str(ans).strip())
            quiz["score"] += score
            quiz["res"] = {"score": score, "fb": fb, "ans": str(ans).strip()}
            quiz["hist"].append({"q": q["question"], "ans": str(ans).strip(),
                                 "correct": correct_text(q), "score": score})
            st.rerun()
        if c2.button("⏹️ إنهاء التقييم الآن"):
            quiz["n"] = quiz["i"]
            st.rerun()
        return

    res = quiz["res"]
    if res["score"] == 1:
        st.success("إجابة صحيحة! 🎉")
    elif res["score"] > 0:
        st.warning("إجابة صحيحة جزئيًا")
    else:
        st.error("إجابة غير صحيحة")
    st.write(f"الإجابة الصحيحة: {correct_text(q)}")
    if q.get("explanation"):
        _pg = q.get("page_printed") or q.get("page")
        _src = str(q.get("source_book") or "Student's Book")
        page = f" — {_src}, page {q.get('source_page')}" if q.get("source_page") else (f" — {_src}, page {_pg}" if _pg else f" — {_src}; page not verified")
        st.info(f"{q['explanation']}{page}")
    elif q.get("source_book") or q.get("source_page"):
        _src = str(q.get("source_book") or "Source not verified")
        _spage = q.get("source_page")
        st.caption(f"Source: {_src}" + (f", page {_spage}" if _spage else "; page not verified"))
    if res["fb"]:
        st.caption(res["fb"])
    last = quiz["i"] + 1 >= quiz["n"]
    b1, b2 = st.columns([3, 1])
    if b1.button("عرض النتيجة" if last else "السؤال التالي ◀"):
        quiz["i"] += 1
        quiz["cur"] = None
        quiz["res"] = None
        st.rerun()
    if not last and b2.button("⏹️ إنهاء الآن"):
        quiz["n"] = quiz["i"] + 1
        quiz["i"] += 1
        quiz["cur"] = None
        quiz["res"] = None
        st.rerun()
