"""
btec_ai.py
كل استدعاءات Gemini الخاصة بـ BTEC: استخراج بيانات الواجب، دليل الطالب (نص + مواضع صور)، توليد الصور،
دليل شرح الواجب للمعلم، وفحص أدلة الطالب. البرومتات في btec_prompt.py.
"""
import json
import os
import re
import time

from google.genai import types

from btec_prompt import (BTEC_DATA_PROMPT, BTEC_DIALECT_ADDENDUM, BTEC_EVIDENCE_PROMPT, BTEC_FORMAT_ADDENDUM, BTEC_SYSTEM_PROMPT,
                         BTEC_TEACHER_EXPLAIN_PROMPT, ILLUSTRATION_STYLE_SUFFIX)
from config import GEMINI_MODEL
from rag import get_client

# نموذج توليد الصور؛ غيّره بمتغير GEMINI_IMAGE_MODEL إن تغيّر اسم النموذج المتاح لحسابك
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
MAX_ILLUSTRATIONS = 4
_IMG_RE = re.compile(r"\[\[IMG:\s*(.*?)\s*\|\s*(.*?)\s*\]\]", re.S)


def parts(items):
    out = []
    for it in items:
        if it["kind"] == "docx":
            out.append(f"[محتوى مستند Word: {it['name']}]\n{it['text'][:60000]}")
        else:
            out.append(types.Part.from_bytes(data=it["data"], mime_type=it["mime"]))
    return out


def _gen(contents, **cfg):
    return get_client().models.generate_content(model=GEMINI_MODEL, contents=contents,
                                                config=types.GenerateContentConfig(**cfg))


def _json(text):
    txt = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        d = json.loads(txt)
    except json.JSONDecodeError:
        return None
    return d if isinstance(d, dict) else None


def extract_data(items):
    d = _json(_gen([BTEC_DATA_PROMPT] + parts(items), temperature=0, response_mime_type="application/json").text)
    return d or {"readable": False, "reason": "تعذّر تحليل الملفات."}


def student_guide(items, data):
    ctx = "بيانات الواجب المستخرجة (للاسترشاد، والمرجع هو الملفات نفسها):\n" + json.dumps(data, ensure_ascii=False)
    ask = ("حلّل الواجب المرفق وأعد الدليل الإرشادي المطلوب. "
           "تنبيه مهم: اكتب الشرح والتوجيه كله باللهجة الأردنية العامية البيضاء كما في تعليمات اللهجة، لا بالفصحى ولا بلهجة بلد آخر.")
    res = _gen([ask, ctx] + parts(items),
               system_instruction=BTEC_SYSTEM_PROMPT + BTEC_FORMAT_ADDENDUM + BTEC_DIALECT_ADDENDUM, temperature=0.3)
    return (res.text or "").strip()


def split_illustrations(md):
    """يحوّل علامات [[IMG: وصف | prompt]] إلى [[IMG:n]] ويعيد (النص, [{n, caption, prompt}])."""
    found = []

    def repl(m):
        if len(found) >= MAX_ILLUSTRATIONS:
            return ""
        n = len(found) + 1
        found.append({"n": n, "caption": m.group(1).strip(), "prompt": m.group(2).strip()})
        return f"[[IMG:{n}]]"
    return _IMG_RE.sub(repl, md), found


def _retry_delay(msg):
    m = re.search(r"retry(?:Delay)?\D{0,12}(\d+(?:\.\d+)?)\s*s", msg, re.I)
    return float(m.group(1)) if m else None


def make_image(prompt, attempts=3):
    """يعيد ((bytes, mime) أو None, رسالة_الخطأ). يعيد المحاولة عند حدّ المعدّل/الانشغال، ويستخدم العميل الخام
    لأن الانتقال بين نماذج النص لا يناسب نموذج الصور."""
    last = ""
    for i in range(attempts):
        try:
            raw = get_client()._c
            mods = ["IMAGE", "TEXT"] if i == 0 else ["IMAGE"]
            res = raw.models.generate_content(
                model=IMAGE_MODEL, contents=[prompt + ILLUSTRATION_STYLE_SUFFIX],
                config=types.GenerateContentConfig(response_modalities=mods))
            for cand in res.candidates or []:
                for p in (cand.content.parts if cand.content else []) or []:
                    if getattr(p, "inline_data", None) and p.inline_data.data:
                        return (p.inline_data.data, (p.inline_data.mime_type or "image/png")), ""
            last = "لم يُرجع النموذج صورة (ربما رفض الطلب أو أرجع نصًا فقط)."
        except Exception as e:  # noqa: BLE001
            last = str(e)[:300]
            low = last.lower()
            if any(k in low for k in ("404", "not found", "not supported", "permission", "api key", "invalid")) and \
                    "429" not in low and "quota" not in low:
                break   # خطأ في اسم النموذج/الصلاحية: لا فائدة من التكرار
            time.sleep(min(_retry_delay(last) or 8 * (i + 1), 45))
            continue
        time.sleep(3)
    print("BTEC image generation failed:", last)
    return None, last


def teacher_explain(data, guide_md, notes=None):
    body = ("بيانات الواجب:\n" + json.dumps(data, ensure_ascii=False) +
            (f"\n\nملاحظات المشرف المهمة على الواجب:\n{notes}" if notes else "") +
            "\n\nدليل الطالب المعدّ لهذا الواجب:\n" + guide_md)
    res = _gen([body], system_instruction=BTEC_TEACHER_EXPLAIN_PROMPT, temperature=0.3)
    return (res.text or "").strip()


def review_evidence(data, items, student_name="", notes=None):
    head = ("بيانات الواجب ومعاييره (JSON):\n" + json.dumps(data, ensure_ascii=False) +
            (f"\n\nملاحظات المشرف المهمة على الواجب (راعها عند الحكم):\n{notes}" if notes else "") +
            (f"\n\nاسم الطالب: {student_name}" if student_name else "") + "\n\nأدلة الطالب المرفقة:")
    d = _json(_gen([head] + parts(items), system_instruction=BTEC_EVIDENCE_PROMPT, temperature=0,
                   response_mime_type="application/json").text)
    return d
