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
_DEFAULT_FALLBACKS = "gemini-3.8-flash,gemini-2.5-flash-lite"
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
    models = [m.strip() for m in (raw if raw is not None else _DEFAULT_FALLBACKS).split(",") if m.strip()]
    # أزيل نموذج Gemini 2.0 Flash المتوقف، حتى لو كان موجودًا في إعدادات Streamlit القديمة.
    return list(dict.fromkeys("gemini-3.8-flash" if m.lower().removeprefix("models/") == "gemini-2.0-flash" else m for m in models))


def model_chain(primary=None):
    """النماذج بترتيب التجربة: ما ليس في فترة راحة أولًا، ثم الباقي حسب أقرب انتهاء للراحة (فلا نتوقف إن كانت كلها مرهقة)."""
    candidates = [primary or GEMINI_MODEL] + _fallbacks()
    # قد يكون النموذج الأساسي نفسه مضبوطًا على الاسم القديم في Secrets أو Environment.
    candidates = ["gemini-3.8-flash" if str(m).lower().removeprefix("models/") == "gemini-2.0-flash" else m for m in candidates]
    chain = list(dict.fromkeys(candidates))
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
