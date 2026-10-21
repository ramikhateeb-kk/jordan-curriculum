"""
البحث والإجابة اعتمادًا على المنهاج فقط.
- استخراج نص كل صفحة كاملة (لا تقطيع عشوائي) ليبقى كل مقطع متماسكًا ومرتبطًا برقم صفحته بدقة.
- عند اختيار درس أو وحدة: يُرسل نصّه كاملًا إلى Gemini (ضمن حد آمن) لضمان عدم فقدان أي جزء منه، وهذا هو الضامن الأهم للدقة.
- عند نطاق كبير جدًا (كل الكتاب): يُستخدم بحث محلي (BM25) لاختيار أنسب الصفحات، دون أي استدعاء لـ Gemini في هذه الخطوة.
- درجة حرارة توليد منخفضة (0) لتقليل الحشو والتخمين، وتعليمات صارمة بعدم الخروج عن النص وبذكر رقم الصفحة لكل معلومة.
"""
import json
import math
import os
import re
import threading
import time
import unicodedata
from collections import Counter
from functools import lru_cache

from google import genai
from google.genai import types

from config import INDEX_DIR, GEMINI_MODEL

SYSTEM = (
    "أنت مساعد تعليمي دقيق للمنهاج الأردني. التزم بما يلي:\n"
    "1) المصدر الأول للإجابة: نص الكتاب المرفق (وما أُرفق معه من تمارين الكتاب المرافق والصفحات التي ذكرها الطالب). "
    "اذكر رقم الصفحة بين قوسين بعد كل معلومة تنقلها منه، مثل: (صفحة 12). لا تنسب للكتاب ما لم يذكره.\n"
    "2) الأولوية الصارمة لمحتوى المنهاج: كتاب الطالب والكتب المرافقة ودفاتر الأنشطة والتمارين المعتمدة. استخدم أمثلة من هذه المصادر فقط متى توفرت. "
    "لا تنشئ أمثلة خارجية من عندك إذا كان ذلك قد يُدخل مفردات أو تراكيب لم يدرسها الطالب. إذا لم يكفِ المحتوى، وضّح ما ينقصك واطلب من الطالب تحديد الدرس/الصفحة أو إرسال صورة النص قبل الشرح. لا تخمّن ولا تستبدل المصدر بنص مشابه.\n"
    "3) إن طلب الطالب حلّ سؤال أو تمرين من صفحة معيّنة فابحث عنه في «الصفحات التي ذكرها الطالب» واشرح الحل خطوة بخطوة ثم اذكر "
    "الإجابة النهائية. وإن لم يظهر نصه فاطلب منه كتابة نص السؤال.\n"
    "4) فقط إن كان السؤال لا علاقة له بمبحث الكتاب إطلاقًا (مثل سؤال عن دورة الماء في كتاب التاريخ) فأعد السطر التالي وحده بلا أي "
    "كلام آخر: <<UNRELATED>> — ولا تستعمله إلا إذا كنت متأكدًا.\n"
    "5) اكتب بالعربية الفصحى الواضحة والمبسطة المناسبة لطالب مدرسي، ولا تُدخل آراءك الشخصية.\n"
    "6) قبل الإجابة، تحقق من أن الطلب والمصدر محددان بما يكفي. إذا كان هناك غموض مؤثر (مثل نص أو صفحة أو درس غير محدد، أو أكثر من تطابق محتمل)، "
    "اطرح سؤالًا توضيحيًا واحدًا قصيرًا في كل مرة وانتظر إجابة الطالب؛ لا تولّد الشرح قبل حسم الغموض. لا تسأل عن معلومة اختارها الطالب مسبقًا في الواجهة. "
    "إذا كان الطلب واضحًا والمصدر متاحًا، أجب مباشرة دون أسئلة زائدة.\n"
    "7) لا تستخدم أمثلة خارج المنهاج افتراضيًا؛ إن لم تجد مثالًا من الكتاب الرئيسي أو الكتب المرافقة، صرّح بذلك واطلب تحديد المصدر أو صورة الصفحة."
)


# ------------------------------------------------------------ الانتقال التلقائي بين نماذج Gemini
# عند تجاوز الحد المسموح (429) أو انشغال الخدمة (503) أو عدم وجود النموذج (404) يُجرَّب النموذج التالي في السلسلة تلقائيًا.
# السلسلة: GEMINI_MODEL ثم GEMINI_FALLBACK_MODELS (أسماء مفصولة بفواصل في متغير بيئة أو في secrets). لكل نموذج حصة مستقلة غالبًا.
_DEFAULT_FALLBACKS = "gemini-2.5-flash-lite,gemini-2.0-flash"
_COOL = {}                       # نموذج -> وقت انتهاء فترة الراحة
_LOCK = threading.Lock()
LAST_QUOTA = [0.0]               # آخر مرة فشلت فيها كل النماذج بسبب الحد المسموح
LAST_USED = [None]


def _fallbacks():
    raw = os.getenv("GEMINI_FALLBACK_MODELS")
    if raw is None:
        try:
            import streamlit as st
            raw = st.secrets.get("GEMINI_FALLBACK_MODELS")
        except Exception:
            raw = None
    return [m.strip() for m in (raw if raw is not None else _DEFAULT_FALLBACKS).split(",") if m.strip()]


def model_chain(primary=None):
    """النماذج بترتيب التجربة: ما ليس في فترة راحة أولًا، ثم الباقي حسب أقرب انتهاء للراحة (فلا نتوقف إن كانت كلها مرهقة)."""
    chain = list(dict.fromkeys([primary or GEMINI_MODEL] + _fallbacks()))
    now = time.time()
    with _LOCK:
        ready = [m for m in chain if _COOL.get(m, 0) <= now]
        cooling = sorted((m for m in chain if m not in ready), key=lambda m: _COOL[m])
    return ready + cooling


def model_status():
    """[(نموذج, 'جاهز' أو 'راحة N ث')] للتشخيص."""
    now = time.time()
    return [(m, "جاهز" if _COOL.get(m, 0) <= now else f"راحة {int(_COOL[m] - now)} ث") for m in model_chain()]


def _classify(e):
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    msg = str(e)
    low = msg.lower()
    if code in (401, 403) or "api key not valid" in low or "permission_denied" in low:
        return "fatal"
    if code == 429 or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
        return "quota"
    if code in (500, 502, 503, 504) or "unavailable" in low or "overloaded" in low or "deadline" in low:
        return "busy"
    if code == 404 or "not found" in low or "not supported" in low:
        return "missing"
    return "other"


def _cool(model, kind, e):
    low = str(e).lower()
    secs = {"quota": 3600 if ("perday" in low or "per day" in low or "daily" in low) else 60,
            "busy": 30, "missing": 3600, "other": 10}[kind]
    with _LOCK:
        _COOL[model] = time.time() + secs


class _Models:
    def __init__(self, client):
        self._c = client

    def generate_content(self, *, model=None, **kw):
        last, kinds = None, []
        for m in model_chain(model):
            try:
                r = self._c.models.generate_content(model=m, **kw)
                LAST_USED[0] = m
                return r
            except Exception as e:  # noqa: BLE001
                kind = _classify(e)
                if kind == "fatal":
                    raise
                print(f"Gemini: النموذج {m} فشل ({kind}): {str(e)[:160]} — الانتقال إلى النموذج التالي")
                _cool(m, kind, e)
                last = e
                kinds.append(kind)
        if kinds and all(k == "quota" for k in kinds):
            LAST_QUOTA[0] = time.time()
        raise last

    def __getattr__(self, name):
        return getattr(self._c.models, name)


class _Client:
    """غلاف حول genai.Client يحتفظ به حيًّا (إغلاقه يقطع الطلبات) ويضيف الانتقال التلقائي بين النماذج."""
    def __init__(self, client):
        self._c = client
        self.models = _Models(client)

    def __getattr__(self, name):
        return getattr(self._c, name)


def recent_quota_error(seconds=180):
    return time.time() - LAST_QUOTA[0] < seconds


def get_client():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
    if not key:
        raise RuntimeError("لم يتم العثور على GEMINI_API_KEY")
    return _Client(genai.Client(api_key=key))


# ------------------------------------------------------------ البحث المحلي (BM25) — للنطاقات الكبيرة فقط
def _norm(t):
    t = unicodedata.normalize("NFKC", t)
    t = re.sub("[\u064B-\u065F\u0670\u0640]", "", t)
    return t.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))


_STOP = {_norm(w) for w in (
    "في من على الى إلى عن هذا هذه ذلك تلك التي الذي الذين كان كانت ان أن إن او أو ثم قد لا ما لم لن "
    "هو هي هم كل بعد قبل بين حتى عند اذا إذا كما مع اي أي غير بعض عليه عليها منه منها له لها به بها").split()}
_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و")
_SUFFIXES = ("ات", "ون", "ين", "ان", "ها", "هم", "ه", "ي")


def tokenize(text):
    out = []
    for w in re.findall(r"[\u0600-\u06FF]{2,}|[A-Za-z0-9]{2,}", _norm(text)):
        if w in _STOP:
            continue
        for p in _PREFIXES:
            if w.startswith(p) and len(w) - len(p) >= 3:
                w = w[len(p):]
                break
        for s in _SUFFIXES:
            if w.endswith(s) and len(w) - len(s) >= 3:
                w = w[:-len(s)]
                break
        out.append(w)
    return out


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        n = len(docs)
        self.avg = (sum(self.len) / n) if n else 1.0
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query):
        qs = tokenize(query)
        res = [0.0] * len(self.tf)
        for i, c in enumerate(self.tf):
            norm = self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
            for t in qs:
                f = c.get(t)
                if f:
                    res[i] += self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return res


def index_path(grade, sem, slug):
    return INDEX_DIR / f"{grade}_{sem}_{slug}"


@lru_cache(maxsize=8)
def load_index(grade, sem, slug):
    """يعيد (صفحات الكتاب، فهرس البحث المحلي، بيانات الكتاب) أو None إن لم يُستخرج نصه بعد.
    كل عنصر في القائمة هو صفحة كاملة (لا تقطيع)، لضمان صحة الربط برقم الصفحة وتماسك النص."""
    d = index_path(grade, sem, slug)
    if not (d / "pages.json").exists():
        return None
    pages = json.loads((d / "pages.json").read_text(encoding="utf-8"))
    mp = d / "meta.json"
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    meta.setdefault("pages", len(pages))
    bm = BM25([tokenize(p["text"]) for p in pages])
    return pages, bm, meta


# حد آمن لطول النص المُرسَل دفعة واحدة (بالأحرف). كتاب مدرسي: الصفحة نحو 1000-1800 حرف،
# فيغطي هذا الحد عادة وحدة كاملة (10-20 صفحة) دون قطع، وهو أقل بكثير من نافذة سياق Gemini.
FULL_SEND_LIMIT = 45000
MAX_RANKED_PAGES = 25  # عند تجاوز الحد (كل الكتاب مثلًا) تُختار أفضل هذا العدد من الصفحات


def select_context(idx, query, pages=None, max_chars=FULL_SEND_LIMIT, k=MAX_RANKED_PAGES):
    """يختار نص الصفحات اللازمة للإجابة، دون أي استدعاء لـ Gemini في هذه الخطوة.
    - داخل نطاق درس/وحدة محدَّد: يُرسل **كل** صفحاته دون اختصار، ما دام ضمن الحد الآمن، لضمان عدم فقدان معلومة.
    - عند تجاوز الحد (نطاق واسع كـ"كل الكتاب"): تُختار أفضل k صفحة مطابقة للسؤال بالبحث المحلي."""
    all_pages, bm, _ = idx
    if pages:
        cand = [i for i, p in enumerate(all_pages) if pages[0] <= p["page"] <= pages[1]]
    else:
        cand = list(range(len(all_pages)))
    if not cand:
        return []
    total = sum(len(all_pages[i]["text"]) for i in cand)
    if total <= max_chars:
        chosen = cand
    else:
        sc = bm.scores(query)
        ranked = sorted(cand, key=lambda i: -sc[i])
        chosen, used = [], 0
        for i in ranked:
            ln = len(all_pages[i]["text"])
            if chosen and used + ln > max_chars:
                break
            chosen.append(i)
            used += ln
            if len(chosen) >= k:
                break
        chosen = chosen or cand[:1]
        chosen.sort()
    return [all_pages[i] for i in chosen]


# ------------------------------------------------------------ توليد الإجابة
SYSTEM_EXPLAIN_EN = (
    "أنت معلم لغة إنجليزية خبير للمنهاج الأردني تشرح لطلاب المدرسة. التزم بما يلي:\n"
    "1) المصدر الأول: نص كتاب الطالب المرفق (وتمارين كتاب الأنشطة والأسئلة الوزارية والصفحات التي ذكرها الطالب إن وُجدت). اذكر رقم "
    "الصفحة بين قوسين بعد ما تنقله من الكتاب، مثل (صفحة 12). ترجمة الكلمات والجمل إلى العربية مسموحة.\n"
    "2) تمارين كتاب الأنشطة والأسئلة الوزارية المرفقة: استعملها أمثلةً للتطبيق ولبيان كيف يُسأل الطالب في الامتحان، ولا تغيّر نصّها، "
    "ولا تذكر إجابة صحيحة إلا إن وردت معها.\n"
    "3) الأولوية الصارمة لأمثلة المنهاج الأردني: كتاب الطالب، كتاب الأنشطة، الكتب المرافقة، وتمارين وأسئلة المنهاج الموثقة. "
    "استخدم مفردات وتراكيب وأمثلة من هذه المصادر فقط قدر الإمكان. تجنّب الأمثلة الخارجية، خصوصًا المفردات غير الواردة في المنهاج. "
    "إذا لم تجد مثالًا مناسبًا أو لم يتضح الدرس/النص المقصود، فلا تخترع مثالًا ولا تنتقل إلى مصدر خارجي تلقائيًا؛ اسأل الطالب سؤالًا توضيحيًا قصيرًا أو اطلب صورة الصفحة.\n"
    "4) إن طلب الطالب حلّ سؤال أو تمرين من صفحة معيّنة فابحث عنه في «الصفحات التي ذكرها الطالب» (كتاب الطالب أو كتاب الأنشطة)، واشرح "
    "الحل خطوة بخطوة ثم اذكر الإجابة النهائية. وإن لم يظهر نصه فاطلب منه كتابة نص السؤال.\n"
    "5) أسئلة القواعد (Grammar): اشرح القاعدة اعتمادًا على نصوص المنهاج والكتب المرافقة وتمارينها وأمثلتها فقط. "
    "إذا لم يتضمن المحتوى المتاح شرحًا كافيًا، لا تُصدر الرمز <<NOT_IN_CURRICULUM>> ولا تطلب من النظام البحث الخارجي تلقائيًا؛ "
    "اطلب من الطالب تحديد الوحدة/الدرس أو إرسال صورة الصفحة، ثم أعد البحث في مواد المنهاج. لا تستخدم أمثلة خارجية إلا إذا طلب الطالب ذلك صراحةً.\n"
    "6) فقط إن كان السؤال لا علاقة له بمبحث الكتاب إطلاقًا فأعد السطر التالي وحده: <<UNRELATED>> — ولا تستعمله إلا إذا كنت متأكدًا.\n"
    "7) اللغة والتنسيق: الشرح بالعربية المبسطة، وكل الجمل والأمثلة الإنجليزية بالإنجليزية. نظّم الإجابة بعناوين (##) وفقرات قصيرة، "
    "واعرض الأمثلة في جدول بعمودين (| English | العربية |). لا تخلط العربية والإنجليزية في السطر الواحد إلا للمصطلحات.\n"
    "8) طلب الترجمة: إذا طلب الطالب ترجمة فقرة/الجملة الأولى من نص محدد، فانقل الفقرة المطلوبة من النص المرفق كما هي ثم ترجمها كاملةً إلى العربية جملةً بجملة؛ لا تكتفِ بملخص أو فكرة عامة، ولا تترك قسم الترجمة فارغًا. "
    "9) الكلمات المظللة: لا تخمّن الكلمات ولا تنقل كلمات من مقال آخر أو صفحة أخرى لمجرد تشابه الموضوع. استخدم فقط الكلمات/النص الموجود في المقطع الذي حدده الطالب. إذا لم تظهر الكلمات المظللة في النص المرفق، اطلب صورة الصفحة أو كتابة الكلمات بدل افتراض صفحة بديلة. "
    "10) إن كان الطلب سؤالًا محددًا فأجب عنه مباشرة وباختصار أولًا. وإن كان شرح درس فاستعمل هذا القالب وأسقط ما لا مادة له: "
    "## 🎯 الفكرة باختصار — ## 📖 كما ورد في كتابك — ## ✏️ تمارين من كتاب الأنشطة — ## 📝 كيف تُسأل في الامتحان — ## ✅ ملخص."
)


def build_prompt(question, pages_text, extras=None, subject="", grade=""):
    from rich_text import clean_text
    ctx = "\n\n".join(f"=== صفحة {p['page']} ===\n{clean_text(p['text'])}" for p in pages_text)
    out = (f"مبحث الكتاب: {subject} — الصف: {grade}\n\n" if subject else "")
    out += f"نص من كتاب المنهاج (المصدر الأول للإجابة):\n{ctx}\n\n"
    extras = extras or {}
    for item in extras.get("pages_asked") or []:
        out += f"الصفحة {item['page']} من {item['source']} (ذكرها الطالب):\n{item['text']}\n\n"
    if extras.get("workbook"):
        out += f"تمارين كتاب الأنشطة لهذا الدرس (للتطبيق والأمثلة):\n{extras['workbook']}\n\n"
    if extras.get("ministry"):
        out += f"أسئلة وزارية سابقة على هذا الدرس (لبيان كيف يُسأل في الامتحان):\n{extras['ministry']}\n\n"
    if extras.get("grammar_topic"):
        out += f"موضوع القاعدة المطلوبة: {extras['grammar_topic']}\n\n"
    if extras.get("source_priority"):
        out += (
            "تعليمات إلزامية للسؤال المرتبط بصفحة محددة: استخدم نص الصفحة المعروض أعلاه وحده. "
            "تحقق أولًا أن النص يحتوي السؤال المطلوب وينتمي إلى المبحث المذكور. "
            "إذا كان النص لا يحتوي السؤال أو كان من مادة/موضوع مختلف، فلا تحل سؤالًا بديلًا ولا تخمّن؛ "
            "أخبر المستخدم أن السؤال المطلوب لم يظهر في نص الصفحة المسترجع واطلب صورة الصفحة أو نص السؤال.\n\n"
        )
    return out + f"طلب الطالب/المعلم:\n{question}"


def answer(client, question, pages_text, extras=None, book_lang="ar", subject="", grade=""):
    """توليد الشرح بأولوية صارمة لمحتوى المنهاج والكتب المرافقة، مع توجيه النموذج لطلب التوضيح عند غموض المصدر وتجنب الأمثلة الخارجية."""
    english = book_lang == "en" or bool(extras and any(extras.get(k) for k in ("workbook", "ministry", "grammar_topic")))
    system = SYSTEM_EXPLAIN_EN if english else SYSTEM
    r = client.models.generate_content(
        model=GEMINI_MODEL, contents=build_prompt(question, pages_text, extras, subject, grade),
        config=types.GenerateContentConfig(system_instruction=system, temperature=0))
    return r.text
