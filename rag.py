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
import unicodedata
from collections import Counter
from functools import lru_cache

from google import genai
from google.genai import types

from config import INDEX_DIR, GEMINI_MODEL

SYSTEM = (
    "أنت مساعد تعليمي دقيق للمنهاج الأردني. التزم بالقواعد التالية بصرامة:\n"
    "1) أجب فقط من نص الكتاب المرفق أدناه، ولا تستخدم أي معلومة من معرفتك العامة أو من خارج النص، "
    "حتى لو كانت صحيحة في الواقع.\n"
    "2) لا تخمّن ولا تكمل معلومة ناقصة في النص من عندك.\n"
    "3) إن لم يكن جزء من الطلب موجودًا في النص المرفق، صرّح بذلك بوضوح: «لم أجد هذه المعلومة في المنهاج» "
    "بدل تجاهله أو الاجتهاد فيه.\n"
    "4) اذكر رقم الصفحة بين قوسين بعد كل معلومة تنقلها من النص، مثل: (صفحة 12).\n"
    "5) اكتب بالعربية الفصحى الواضحة والمبسطة المناسبة لطالب مدرسي.\n"
    "6) لا تنسب للنص ما لم يذكره صراحة، ولا تُدخل آراءك أو تقييمك الشخصي."
)


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
    return genai.Client(api_key=key)


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
def build_prompt(question, pages_text):
    ctx = "\n\n".join(f"=== صفحة {p['page']} ===\n{p['text']}" for p in pages_text)
    return f"نص من كتاب المنهاج (المصدر الوحيد المسموح به للإجابة):\n{ctx}\n\nطلب الطالب/المعلم:\n{question}"


def answer(client, question, pages_text):
    if not pages_text:
        return "لم أجد نصًا لهذا الدرس في الكتاب لأجيب اعتمادًا عليه."
    prompt = build_prompt(question, pages_text)
    r = client.models.generate_content(
        model=GEMINI_MODEL, contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0))
    return r.text
