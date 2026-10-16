"""
subject_profiles.py
توجيه توليد الأسئلة حسب المبحث. مبني على تحليل امتحان وزاري حقيقي (اللغة الإنجليزية، الصف 11، توجيهي 2026) ومقارنته بكتاب
الطالب وكتاب الأنشطة. اللغة الإنجليزية الآن؛ وتُضاف العربية لاحقًا كملف جديد بالبنية نفسها (نوع الدرس ← نمط السؤال).

أنماط الامتحان الوزاري (الإنجليزية) كما استُنتجت:
  V1 مفردات في سياق: جملة فيها فراغ (............) وأربعة خيارات من الفئة النحوية نفسها (جملة الكتاب نفسها أحيانًا).
  V2 تعبير اصطلاحي/فعل مركّب/تشكيل كلمات: (get rid of, off the record, institution→institutional...).
  V3 استبدال الجزء المسطَّر: "The underlined part ... can be replaced with ......".
  G1 قاعدة في جملة: اختيار الصيغة الصحيحة (future perfect, relative pronouns, gerund/infinitive, used to, wish, articles).
  G2 تحويل: جملة ثم "The correct ... form of the sentence above is ......" وأربع جمل كاملة (reported speech, impersonal
     passive, negative inversion) أو "This means that ......" (conditionals).
  F1 وظائف لغوية: "The above sentences indicate that the speaker is ......" (suggesting, clarifying, deciding...).
  R1 قطعة قراءة من وحدات الكتاب (مقتطعة/مختصرة) + أسئلة قصيرة: عدّد، فسّر، "find a word which means '<glossary>'"،
     "write down the sentence which indicates...", مرجع الضمير المسطَّر، رأيك في جملتين.
  R2 Culture Spot/Literature Spot: مقتطف + سؤال استنتاج أو سؤال شعري (مقاطع/صورة...).
  W1 كتابة حرة: اختر موضوعًا من اثنين (مقال/مقالة) — تُقابل دروس Writing.
"""
import hashlib
import random
import re

from rag import select_context

PASSAGE_KINDS = ("reading", "culture", "literature")
# كيف تُسأل أسئلة القراءة: "reference" = يُذكر اسم النص ورقم صفحته ويفتح الطالب كتابه (لا يُخزَّن نص)،
# "passage" = تُعرض قطعة حرفية داخل السؤال. الافتراضي: reference.
READING_MODE = "reference"

_KIND_RULES = [
    ("reading", r"\breading\b"), ("listening", r"\blistening\b"), ("writing", r"\bwriting\b"),
    ("speaking", r"\bspeaking\b"), ("culture", r"culture spot"), ("literature", r"literature spot"),
    ("life", r"life skills"), ("vocab_grammar", r"vocabulary and grammar"), ("grammar", r"\bgrammar\b"),
    ("vocab", r"\bvocabulary\b"),
]


def lesson_kind(title):
    """نوع الدرس من عنوانه: reading / listening / writing / speaking / culture / literature / life /
    vocab_grammar / grammar / vocab / other."""
    t = (title or "").lower()
    for kind, rx in _KIND_RULES:
        if re.search(rx, t):
            return kind
    return "other"


# ------------------------------------------------------------------ تعليمات الإنجليزية
SYSTEM_EN = (
    "You are a Jordanian Ministry of Education English exam writer (Grade 11 Jordan High Note). You write accurate questions "
    "in the style of the real Ministry exam. Follow strictly:\n"
    "1) Use ONLY the attached book text for facts and for what the lesson teaches; never invent details. New sentences "
    "may be written to test the lesson's language points, but they must be natural, correct British English.\n"
    "2) The correct answer must be certain and defensible; exactly one option is correct; the three wrong options are plausible "
    "(same part of speech or grammar form, related meaning or similar form) but clearly wrong. Never use 'all of the above'.\n"
    "3) Ministry style: short clear stems; a blank is written as ............ (12 dots); options are short and parallel; "
    "no trick questions.\n"
    "4) Text inside [[ ]] marks an underlined word or phrase in the stem.\n"
    "5) Workbook practice, if provided, is only a guide to question types and language points; the page number must be a "
    "page of the book text, never of the workbook.\n"
    "Return JSON only, no other text."
)

SYSTEM_READING_EN = (
    "You are a Jordanian Ministry of Education English exam writer. The student is shown a PASSAGE taken verbatim from the "
    "textbook, then answers ONE question about it. Follow strictly:\n"
    "1) The question and its answer must be answerable from the passage (plus the glossary definitions given, if any) and "
    "from nothing else. Do not copy a question the student has already been asked.\n"
    "2) Use one of these Ministry reading-question patterns, whichever fits the passage and the requested type:\n"
    "   a) Vocabulary: 'Find a word in the passage which means \"<definition>\".' (answer = one word from the passage)\n"
    "   b) Reference: 'What does the underlined pronoun \"they\" refer to?' — give the exact pronoun to underline in "
    "\"underline\" (see schema).\n"
    "   c) Evidence: 'Write down the sentence which indicates ...' (answer = a sentence copied from the passage)\n"
    "   d) Detail: 'Write down two/three ... mentioned in the passage.' or a wh-question on a stated fact.\n"
    "   e) Inference/opinion: 'Why does the writer mention ...?' or 'In two sentences, write your point of view on ...'.\n"
    "3) For multiple choice: four plausible options, one correct, all answerable from the passage. For true/false: a statement "
    "that is clearly true or false according to the passage.\n"
    "4) Write the question in English only. Return JSON only, no other text."
)

_KIND_GUIDE = {
    "vocab": (
        "Pattern V1/V2/V3 (choose ONE at random): (V1) a NEW sentence with a blank (............) testing a target word or "
        "collocation from this lesson, options all the same part of speech; (V2) an idiom, phrasal verb, compound noun or "
        "word-formation item from this lesson's lists (e.g. options institutionalise / institution / institutional / "
        "institutionally); (V3) a sentence with an underlined phrase marked [[ ]] and the stem 'The underlined part of the "
        "above sentence can be replaced with ............'. Test words and phrases that appear in this lesson's lists/exercises."),
    "grammar": (
        "Pattern G1/G2 (choose what suits the grammar point): (G1) a NEW sentence with a blank (............) and four forms "
        "of the same grammar point (e.g. will be / would be / would have been / will have been); or (G2) a transformation: "
        "a sentence, a blank line, then 'The correct <grammar point> form of the sentence above is ............' with four COMPLETE "
        "sentences that differ only in the target feature (word order, tense, passive, reported speech, inversion); or "
        "'This means that ............' for conditionals/wishes. Test exactly the grammar point(s) taught in this lesson."),
    "vocab_grammar": (
        "Pattern V1-V3 or G1-G2 (choose ONE, vary between calls): a vocabulary-in-context item testing a target word or "
        "collocation from the lesson, or a grammar item on the grammar point taught (gap with four forms, or a transformation: "
        "'The correct ... form of the sentence above is ............')."),
    "speaking": (
        "Pattern F1: two short sentences or a mini-exchange, then the stem 'The above sentences indicate that the speaker is "
        "............' with four language functions taken from this lesson's Speaking box (e.g. expressing indecision, "
        "agreement, relief, annoyance, making suggestions, asking for clarification). Only one function fits."),
    "listening": (
        "The audio is not available. Test the vocabulary or fixed phrases taught in this lesson with Pattern V1 "
        "(a sentence with a blank and four options of the same part of speech)."),
    "writing": (
        "Test the writing skills in this lesson's Writing box: formal/impersonal phrases, linkers, topic sentences, essay or "
        "email conventions. E.g. 'Which of the following is the most formal way of saying ...?' or a sentence with a blank "
        "(............) testing a linker/phrase from the box."),
    "life": ("Test a key idea or phrase from the Life Skills box using a short, clear item with four parallel options."),
    "other": ("Test a language point taught in this lesson with a short, clear Ministry-style item."),
}


def en_guidance(kind):
    return _KIND_GUIDE.get(kind, _KIND_GUIDE["other"])


# ------------------------------------------------------------------ اقتطاع قطعة القراءة
_CUES_ANY = re.compile(
    r"(SPEAKING|CRITICAL THINKING|REFLECT|VALUES|THINK BACK|ACTIVE|GLOSSARY|LESSON|□|Workbook|Grammar Reference)")
_CUES_START = re.compile(
    r"^(Match |Complete |Discuss|In pairs|In groups|Exercise|Study |Listen|Choose |Read the|Look at|Write |Go to|Underline|"
    r"Tick |Find |Answer the|Check |Decide|Say why|Say whether|Which |What do you|Do you|How far)", re.I)


class _Cues:
    """تعليمات التمارين لا تُعدّ نثرًا: كلمات التمارين الكبيرة في أي موضع، وأفعال الأمر في أول الجملة فقط
    (فلا تُرفض جملة نثرية تحوي «which» مثلًا في وسطها)."""
    @staticmethod
    def search(sentence):
        return _CUES_ANY.search(sentence) or _CUES_START.search(sentence)


_CUES = _Cues()
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"'‘])")


def _clean_page(text):
    lines = []
    for ln in str(text).splitlines():
        s = ln.strip()
        if not s or re.fullmatch(r"\d{1,3}", s) or "قيد الإعداد" in s:
            continue
        lines.append(s)
    return re.sub(r"\s+", " ", " ".join(lines))


def _prose(sentence):
    words = sentence.split()
    if len(words) < 7 or _CUES.search(sentence):
        return False
    if re.match(r"^\d+\s", sentence) or sum(c.isalpha() for c in sentence) < 0.7 * len(sentence):
        return False
    return sentence[-1] in ".!?”\"'"


def pick_passage(idx, lesson, avoid=(), min_words=70, max_words=170):
    """يقتطع من صفحات الدرس مقطعًا نثريًا متصلًا (حرفيًا من الكتاب) بطول 70-170 كلمة، ويفضّل مقطعًا لم يُعرض بعد.
    يعيد {"key","text","page"} أو None إن لم يحوِ الدرس نصًا نثريًا كافيًا (فتُستعمل الأسئلة العادية)."""
    try:
        pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=60000)
    except Exception:  # noqa: BLE001
        return None
    runs, cur = [], []                                      # مقاطع من جمل نثرية متتالية
    for p in pages:
        for s in _SENT.split(_clean_page(p["text"])):
            s = s.strip()
            if _prose(s):
                cur.append((p["page"], s))
            elif cur:
                runs.append(cur)
                cur = []
    if cur:
        runs.append(cur)
    cands = []
    for run in runs:
        if sum(len(s.split()) for _p, s in run) < min_words:
            continue
        for start in range(len(run)):
            words, end = 0, start
            while end < len(run) and words + len(run[end][1].split()) <= max_words:
                words += len(run[end][1].split())
                end += 1
            if words >= min_words:
                text = " ".join(s for _p, s in run[start:end])
                key = hashlib.md5(text[:80].encode("utf-8")).hexdigest()[:8]
                cands.append({"key": key, "text": text, "page": run[start][0], "first": start == 0})
    if not cands:
        return None
    fresh = [c for c in cands if c["key"] not in avoid] or cands
    starts = [c for c in fresh if c["first"]]
    pick = random.choice(starts if starts and random.random() < 0.6 else fresh)
    return {k: pick[k] for k in ("key", "text", "page")}


def apply_underline(passage_text, spec):
    """spec = {"snippet": مقطع حرفي من القطعة، "word": الكلمة المراد تسطيرها داخله}. يعيد القطعة مع [[ ]] أو None إن لم يُطابق."""
    if not isinstance(spec, dict):
        return None
    snip, word = str(spec.get("snippet") or ""), str(spec.get("word") or "")
    if not snip or not word or snip not in passage_text or word not in snip:
        return None
    marked = snip.replace(word, f"[[{word}]]", 1)
    return passage_text.replace(snip, marked, 1)


def reading_prompt(lesson, passage, qtype, asked, schema, glossary="", style=""):
    return (
        f"Lesson: {lesson['title']}\n\nPASSAGE (verbatim from the textbook, page {passage['page']}):\n{passage['text']}\n\n"
        + (f"Glossary from the same page:\n{glossary}\n\n" if glossary else "")
        + (f"{style}\n\n" if style else "")
        + f"Write ONE question of this kind: {qtype_desc(qtype)}.\n"
        f"Do not repeat questions already asked about this lesson:\n{asked}\n\n"
        "If you choose the 'underlined pronoun' pattern, set \"underline\" to {\"snippet\": a 6-12 word snippet copied EXACTLY "
        "from the passage that contains the pronoun, \"word\": the pronoun}; otherwise set \"underline\" to null.\n"
        f"Return JSON in exactly this format:\n{schema}")


def qtype_desc(qtype):
    return {"mcq": "multiple choice (four options, exactly one correct)",
            "tf": "true/false statement about the passage",
            "fill": "fill-in-the-blank: a sentence taken or adapted from the passage with ONE blank written ______",
            "short": "short-answer (answered in a word, a sentence or two sentences)"}[qtype]


def glossary_of(idx, lesson, passage_page):
    """سطور GLOSSARY في صفحة القطعة (تُعرض للنموذج كي يصوغ سؤال «find a word which means»)."""
    try:
        for p in select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=60000):
            if p["page"] != passage_page:
                continue
            m = re.search(r"GLOSSARY(.{0,400})", p["text"].replace("\n", " "), flags=re.S)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


# ------------------------------------------------------------------ أسئلة بالإشارة إلى النص (اسم النص + الصفحة)
SYSTEM_REFERENCE_EN = (
    "You are a Jordanian Ministry of Education English exam writer. The student has the Student's Book open. You write ONE "
    "question about a reading text (or Culture/Literature Spot) from the book text provided, and the question must POINT to the "
    "text instead of reproducing it. Follow strictly:\n"
    "1) Do NOT mention page numbers or the title of the text in the question: the system adds 'From your reading of "
    "\"<title>\" (page N)' and the full text itself. Refer to it only as 'the text', 'the article', 'the passage' or 'the poem'. "
    "Set \"page\" to the PRINTED page (from the page headers) where the answer is found.\n"
    "2) To locate a detail, quote at most 8 words copied EXACTLY from the text, e.g. 'In the sentence that begins \"She saw that "
    "different groups ...\", what does the pronoun \"they\" refer to?' or 'In the paragraph that begins \"At first, the "
    "animals ...\", find a word which means \"...\".' Never quote more than 8 words. List every quote in \"quotes\".\n"
    "3) Use Ministry reading patterns: (a) 'Find a word in the text which means \"<glossary/definition>\"'; (b) pronoun "
    "reference; (c) 'Write down the sentence which indicates ...'; (d) 'Write down three/two ... mentioned in the text'; (e) "
    "'Why does the writer mention ...?' / 'In two sentences, write your point of view on ...'; (f) author's opinion.\n"
    "4) The question must not contain its own answer, and the answer must be found in the text (or be the student's own opinion "
    "for opinion questions). For multiple choice: four plausible options, exactly one correct. For true/false: a clear statement.\n"
    "5) Write in English only. Return JSON only, no other text."
)


def fix_ligatures(text):
    """يصلح تقطّع الحروف المركّبة الذي يضيفه استخراج PDF: 'scientifi c' ← 'scientific'، 'fi gure' ← 'figure'."""
    t = re.sub(r"\b(\w*?(?:ffi|ffl|fi|fl))\s+(?=[a-z])", r"\1", str(text))
    return re.sub(r"\b(fi|ffi|fl|ff)\s+(?=[a-z]{2})", r"\1", t)


def text_title(lesson_title):
    """اسم النص من عنوان الدرس: 'Lesson 2A Reading and Vocabulary: Making contact' ← 'Making contact'."""
    t = str(lesson_title or "")
    return t.split(":", 1)[1].strip() if ":" in t else re.sub(r"^Lesson\s+\w+\s*", "", t).strip()


def _squash(t):
    return re.sub(r"[\W_]+", " ", fix_ligatures(t).lower()).strip()


def quotes_ok(quotes, corpus):
    """كل مقتطف اقتبسه السؤال موجود فعلًا في نص الكتاب؟ (يمنع اقتباسات متخيَّلة)"""
    base = _squash(corpus)
    return all(_squash(q) and _squash(q) in base for q in (quotes or []))


def reference_prompt(lesson, ctx_text, qtype, asked, schema, style=""):
    return (
        f"Reading text / lesson: \"{text_title(lesson['title'])}\" ({lesson['title']})\n\n"
        f"Book text with PRINTED page numbers (use these numbers in the question):\n{ctx_text}\n\n"
        + (f"{style}\n\n" if style else "")
        + f"Write ONE question of this kind: {qtype_desc(qtype)}.\n"
        f"Do not repeat questions already asked about this lesson:\n{asked}\n\n"
        "The question must NOT mention the title or any page number. Set \"page\" to the printed page where the answer "
        "is found. Set \"quotes\" to the list of exact quotations you used in the question (empty list if none).\n"
        f"Return JSON in exactly this format:\n{schema}")


_FULL_CACHE = {}


def full_reading_text(idx, lesson, min_run_words=50):
    """نص القراءة الكامل لدرس كما في الكتاب (حرفيًا): كل المقاطع النثرية المتصلة في صفحات الدرس بترتيبها، دون تمارين الكتاب.
    يُجلب من فهرس الكتاب عند الحاجة (عرض النص للطالب أو طباعته في ورقة الاختبار) ولا يُخزَّن في قاعدة البيانات."""
    key = (lesson["start"], lesson["end"], len(idx[0]))
    if key in _FULL_CACHE:
        return _FULL_CACHE[key]
    try:
        pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=200000)
    except Exception:  # noqa: BLE001
        return ""
    runs, cur = [], []
    for p in pages:
        for sent in _SENT.split(fix_ligatures(_clean_page(p["text"]))):
            sent = sent.strip()
            if _prose(sent):
                cur.append(sent)
            elif cur:
                runs.append(cur)
                cur = []
    if cur:
        runs.append(cur)
    blocks = [" ".join(r) for r in runs if sum(len(x.split()) for x in r) >= min_run_words]
    text = "\n\n".join(blocks)
    _FULL_CACHE[key] = text
    return text
