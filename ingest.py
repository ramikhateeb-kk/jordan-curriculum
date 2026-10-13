"""
استخراج نص الكتاب صفحةً صفحة (بلا تقطيع عشوائي) للبحث والإجابة الدقيقة. لا يستخدم أي ذكاء اصطناعي.
"""
import json
import re
import unicodedata
import urllib.request

try:
    import pymupdf as fitz
except ImportError:  # نسخ قديمة
    import fitz

from config import PDF_DIR, INDEX_DIR

MIN_TEXT_PER_PAGE = 30  # أقل من هذا العدد من الأحرف يعني أن الصفحة على الأغلب صورة (بلا نص قابل للقراءة)


# ---------------------------------------------------------------- أدوات النص
def clean(t: str) -> str:
    t = unicodedata.normalize("NFKC", t)  # يوحّد أشكال الحروف العربية
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _norm(t):
    t = unicodedata.normalize("NFKC", t)
    t = re.sub("[\u064B-\u065F\u0670\u0640]", "", t)
    return t.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))


def _words(t):
    return {w for w in re.findall(r"[\u0600-\u06FF]{3,}", _norm(t))}


def extract_pages(doc):
    """يعيد قائمة صفحات [{"page","text"}]، ويتجاوز الصفحات شبه الخالية من النص (على الأغلب صور)."""
    pages = []
    for pno, page in enumerate(doc, start=1):
        text = clean(page.get_text())
        if len(text) >= MIN_TEXT_PER_PAGE:
            pages.append({"page": pno, "text": text})
    return pages


def scanned_ratio(doc):
    """نسبة الصفحات شبه الخالية من النص، لتحذير المشرف إن كان الكتاب ممسوحًا ضوئيًا."""
    empty = sum(1 for page in doc if len(clean(page.get_text())) < MIN_TEXT_PER_PAGE)
    return empty / max(doc.page_count, 1)


# ---------------------------------------------------------------- تحميل الكتاب
def normalize_url(url):
    """يحوّل رابط Google Drive العادي إلى رابط تحميل مباشر."""
    m = re.search(r"drive\.google\.com/file/d/([^/]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return url


def pdf_path(book):
    return PDF_DIR / str(book["grade"]) / str(book["semester"]) / f"{book['slug']}.pdf"


def index_dir(book):
    return INDEX_DIR / f"{book['grade']}_{book['semester']}_{book['slug']}"


def ensure_pdf(book):
    """يحمّل الكتاب من رابطه إن لم يكن موجودًا. يرفع RuntimeError برسالة عربية عند الفشل."""
    path = pdf_path(book)
    if path.exists():
        return path
    url = (book.get("pdf_url") or "").strip()
    if not url.startswith("http"):
        raise RuntimeError("رابط الكتاب غير مُدخل أو غير صحيح. عدّله من صفحة إدارة الكتب.")
    try:
        req = urllib.request.Request(normalize_url(url), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"تعذّر تحميل الكتاب من الرابط: {e}")
    if not data.startswith(b"%PDF"):
        raise RuntimeError("الرابط لا يُرجع ملف PDF مباشرًا (ربما صفحة ويب). استخدم رابط تحميل مباشر.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------- الفهرسة (استخراج نص فقط، بلا ذكاء اصطناعي)
def ensure_index(book):
    """يبني نص الكتاب صفحة صفحة إن لم يكن موجودًا أو تغيّر رابطه. يعيد True إن أعاد البناء."""
    d = index_dir(book)
    meta_f = d / "meta.json"
    if (d / "pages.json").exists() and meta_f.exists():
        try:
            if json.loads(meta_f.read_text(encoding="utf-8")).get("pdf_url") == book["pdf_url"]:
                return False
        except Exception:  # noqa: BLE001
            pass
        p = pdf_path(book)          # تغيّر الرابط: نحذف الملف القديم لنعيد تحميله
        if p.exists():
            p.unlink()
    path = ensure_pdf(book)
    doc = fitz.open(path)
    pages = extract_pages(doc)
    ratio = scanned_ratio(doc)
    d.mkdir(parents=True, exist_ok=True)
    (d / "pages.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    meta_f.write_text(json.dumps({
        "pdf_url": book["pdf_url"], "pages": doc.page_count,
        "text_pages": len(pages), "scanned_ratio": round(ratio, 2),
    }), encoding="utf-8")
    return True  # تحذير الصفحات الممسوحة ضوئيًا يُعرض من app.py عبر meta.json، دون إيقاف الموقع


# ---------------------------------------------------------------- معاينة للتحقق (للمشرف، بلا ذكاء اصطناعي)
def check_book(book, cfg, offset):
    """لكل وحدة/درس: أي صفحة PDF تقابله، وهل عنوانه ظاهر فعليًا في نصها؟ (تحقق نصي مباشر)."""
    doc = fitz.open(ensure_pdf(book))
    rows = []

    def check(kind, title, printed):
        page = printed + offset
        if not 1 <= page <= doc.page_count:
            rows.append({"النوع": kind, "العنوان": title, "صفحة PDF": page,
                        "النتيجة": "❌ خارج الكتاب", "بداية النص": ""})
            return
        text = clean(doc[page - 1].get_text())
        key = _words(title.split(":", 1)[-1])
        ok = bool(key) and len(key & _words(text)) >= max(1, (len(key) + 1) // 2)
        warn = len(text) < MIN_TEXT_PER_PAGE
        result = "🖼️ صفحة بلا نص (صورة؟)" if warn else ("✅ مطابق" if ok else "⚠️ راجع")
        rows.append({"النوع": kind, "العنوان": title, "صفحة PDF": page,
                    "النتيجة": result, "بداية النص": text.replace("\n", " ")[:90]})

    for u in cfg:
        check("وحدة", u["title"], u["start"])
        for l in u["lessons"]:
            check("درس", l["title"], l["start"])
    return rows, doc.page_count
