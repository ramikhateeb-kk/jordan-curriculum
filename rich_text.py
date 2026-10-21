"""
rich_text.py
عرض نص ماركداون (شرح عربي + أمثلة إنجليزية) باتجاه صحيح: كل فقرة/بند/خلية تتبع لغتها (dir="auto")،
والجداول والقوائم باتجاه الكتاب (الإنجليزي من اليسار لليمين). وتنظيف نصوص صفحات الكتاب من الأسطر الفارغة وأرقام الأسطر الهامشية.
"""
import html
import re

import streamlit as st

try:
    import markdown as _md
except ImportError:  # noqa: BLE001
    _md = None

_STYLE = ("<style>.bidi-rt table{border-collapse:collapse;width:100%;margin:.4em 0 1em}"
          ".bidi-rt th,.bidi-rt td{border:1px solid rgba(128,128,128,.45);padding:6px 10px}"
          ".bidi-rt th{background:rgba(128,128,128,.12)}.bidi-rt p{margin:0 0 .7em}"
          ".bidi-rt h2,.bidi-rt h3{margin:1em 0 .4em}.bidi-rt code{direction:ltr;unicode-bidi:isolate}</style>")
_BLOCK = re.compile(r"<(p|li|h[1-6]|td|th|blockquote)(\s|>)")


def normalize_markdown(md):
    """إصلاح أشهر أخطاء تنسيق Markdown الصادرة عن النموذج قبل العرض."""
    text = str(md or "").replace("\\|", "|")
    lines = text.splitlines()
    fixed = []
    for line in lines:
        # أحيانًا يدمج النموذج نهاية صف العناوين مع صف فواصل الجدول: | English | العربية | | :--- | :--- |
        line = re.sub(r"\|\s*\|\s*((?::?[-]{3,}[^|]*(?:\|[^|]*)*\|?)\s*$", r"|\n| \1", line)
        fixed.extend(line.split("\n"))
    text = "\n".join(fixed)
    # توحيد صفوف فواصل الجداول، مع الإبقاء على الأعمدة كما كتبها النموذج.
    text = re.sub(r"(?m)^\s*\|?\s*:?-{3,}[^\n]*$", lambda m: "| " + m.group(0).strip().strip("|").strip() + " |", text)
    return text


def to_html(md, base="ltr"):
    """ماركداون → HTML. base: اتجاه الجداول والقوائم (ltr لكتاب إنجليزي)."""
    md = normalize_markdown(md)
    if _md is None:
        return None
    safe = str(md).replace("&", "&amp;").replace("<", "&lt;")            # لا نسمح بـ HTML خام من النموذج
    body = _md.markdown(safe, extensions=["tables", "sane_lists", "fenced_code"])
    body = _BLOCK.sub(lambda m: f'<{m.group(1)} dir="auto"{m.group(2)}', body)
    body = re.sub(r"\n\s*\n", "\n", body)           # سطر فارغ داخل HTML يقطع الكتلة في عارض الماركداون
    return f'<div class="bidi-rt" dir="{base}" style="text-align:start">{body}</div>'


def show(md, base="ltr"):
    """يعرض الماركداون باتجاه صحيح لكل فقرة. يعود إلى st.markdown إن لم تتوفر مكتبة markdown."""
    md = normalize_markdown(md)
    h = to_html(md, base)
    if h is None:
        st.markdown(md)
    else:
        st.markdown(_STYLE + h, unsafe_allow_html=True)


def clean_text(text):
    """نص صفحة كتاب نظيفًا: بلا أسطر فارغة متتالية ولا أرقام الأسطر الهامشية ولا علامة المسودة، مع إصلاح الحروف المقطّعة."""
    out = []
    for ln in str(text).splitlines():
        s = ln.strip()
        if not s:
            if out and out[-1] != "":
                out.append("")
            continue
        if re.fullmatch(r"\d{1,3}", s) or "قيد الإعداد" in s:
            continue
        out.append(s)
    while out and out[-1] == "":
        out.pop()
    t = "\n".join(out)
    try:
        from subject_profiles import fix_ligatures
        t = fix_ligatures(t)
    except Exception:  # noqa: BLE001
        pass
    return t


def show_page_text(text):
    """يعرض نص صفحة كتاب بأسطره (اتجاه كل سطر تلقائي) دون أسطر فارغة زائدة."""
    body = html.escape(clean_text(text))
    st.markdown(f"<div dir='auto' style='white-space:pre-wrap;text-align:start;line-height:1.7'>{body}</div>",
                unsafe_allow_html=True)
