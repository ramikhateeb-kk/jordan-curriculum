"""
جدول الكتب: الصف، الفصل، المادة، رابط الكتاب، فرق الترقيم، والوحدات والدروس وأرقام صفحاتها.
التخزين: Supabase إن وُجدت مفاتيحه في Secrets (دائم)، وإلا ملف data/catalog.json (مؤقت على Streamlit Cloud).
لا يستخدم أي ذكاء اصطناعي.
"""
import hashlib
import json
import os

import requests

from config import BASE

LOCAL_FILE = BASE / "data" / "catalog.json"
LOCAL_TRACKS_FILE = BASE / "data" / "tracks.json"
TRACK_GRADES = (10, 11, 12)   # الصفوف التي تُقسَّم إلى تخصصات
TIMEOUT = 20
KIND_UNIT, KIND_LESSON = "وحدة", "درس"


# ---------------------------------------------------------------- الإعدادات
def secret(name):
    v = os.getenv(name)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:  # noqa: BLE001
        return None


def backend_name():
    return "supabase" if secret("SUPABASE_URL") and secret("SUPABASE_KEY") else "local"


def make_slug(grade, sem, subject, track_ids=None):
    """معرّف الكتاب. الكتب المشتركة (بلا تخصصات) تحتفظ بنفس المعرّف القديم تمامًا، فلا يتأثر أي
    شيء محفوظ سابقًا (أسئلة، خطط، أدلة). الكتب الخاصة بتخصص تُضاف أرقام تخصصاتها إلى البصمة، فيصبح
    «رياضيات – حادي عشر هندسي» غير «رياضيات – حادي عشر علمي» ولو تطابق الاسم. يُحسب المعرّف مرة واحدة
    عند إنشاء الكتاب فقط ولا يُعاد حسابه عند تعديل تخصصاته."""
    scope = ",".join(str(t) for t in sorted(set(track_ids or [])))
    raw = f"{grade}|{sem}|{subject.strip()}" + (f"|t{scope}" if scope else "")
    return "b" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]


def _sb():
    url = secret("SUPABASE_URL").rstrip("/")
    key = secret("SUPABASE_KEY")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return url, headers


def _check(r):
    if not r.ok:
        raise RuntimeError(f"خطأ من قاعدة البيانات ({r.status_code}): {r.text[:200]}")


def _clean(b):
    track_ids = b.get("track_ids")
    if track_ids is None:   # شكل الرد من Supabase عند طلب book_tracks(track_id)
        track_ids = [t["track_id"] for t in (b.get("book_tracks") or [])]
    subject = str(b["subject"]).strip()
    return {
        "id": b.get("id"),
        "grade": int(b["grade"]), "semester": int(b["semester"]),
        "subject": subject, "slug": str(b["slug"]),
        "pdf_url": str(b.get("pdf_url") or "").strip(),
        "page_offset": int(b.get("page_offset") or 0),
        "units": b.get("units") or [],
        "track_ids": sorted({int(t) for t in track_ids}),   # فارغة = كتاب مشترك لكل تخصصات الصف
        "lang": b.get("lang") or guess_lang(subject),
    }


def guess_lang(subject):
    """لغة الكتاب الافتراضية من اسم المبحث؛ يمكن للمدير تغييرها صراحةً من صفحة إدارة الكتب."""
    s = (subject or "").lower()
    return "en" if ("english" in s or "إنجليز" in s or "انجليز" in s) else "ar"


def is_english(book):
    return (book or {}).get("lang") == "en"


def is_common(book):
    """كتاب مشترك لكل تخصصات صفّه (مثل المهارات الرقمية)."""
    return not book.get("track_ids")


def book_in_track(book, grade, track_id):
    """هل يظهر هذا الكتاب لمن اختار هذا الصف وهذا التخصص؟
    - صف مختلف: لا.  - كتاب مشترك: نعم.  - لم يُختر تخصص (صفوف 1-9 أو تخصصات غير معرّفة): نعم للمشترك فقط."""
    if book["grade"] != grade:
        return False
    if is_common(book):
        return True
    return track_id is not None and track_id in book["track_ids"]


# ---------------------------------------------------------------- عمليات الجدول
def list_books():
    if backend_name() == "supabase":
        url, h = _sb()
        r = requests.get(f"{url}/rest/v1/books", headers=h, timeout=TIMEOUT,
                         params={"select": "*,book_tracks(track_id)", "order": "grade.asc,semester.asc,subject.asc"})
        _check(r)
        books = r.json()
    else:
        books = json.loads(LOCAL_FILE.read_text(encoding="utf-8")) if LOCAL_FILE.exists() else []
    books = [_clean(b) for b in books]
    return sorted(books, key=lambda b: (b["grade"], b["semester"], b["subject"]))


def save_book(book):
    """إضافة كتاب أو تحديثه (المفتاح: الصف + الفصل + المعرّف) مع تخصصاته ولغته."""
    book = _clean(book)
    if backend_name() == "supabase":
        url, h = _sb()
        payload = {k: book[k] for k in ("grade", "semester", "subject", "slug", "pdf_url",
                                         "page_offset", "units", "lang")}
        r = requests.post(f"{url}/rest/v1/books",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=representation"},
                          timeout=TIMEOUT, params={"on_conflict": "grade,semester,slug"},
                          data=json.dumps([payload]))
        _check(r)
        book_id = r.json()[0]["id"]
        d = requests.delete(f"{url}/rest/v1/book_tracks", headers=h, timeout=TIMEOUT,
                            params={"book_id": f"eq.{book_id}"})
        _check(d)
        if book["track_ids"]:
            ins = requests.post(f"{url}/rest/v1/book_tracks",
                                headers={**h, "Prefer": "return=minimal"}, timeout=TIMEOUT,
                                data=json.dumps([{"book_id": book_id, "track_id": t} for t in book["track_ids"]]))
            _check(ins)
    else:
        books = list_books()
        books = [b for b in books if not (b["grade"] == book["grade"] and b["semester"] == book["semester"]
                                          and b["slug"] == book["slug"])]
        books.append(book)
        LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_FILE.write_text(json.dumps(books, ensure_ascii=False, indent=1), encoding="utf-8")


def delete_book(grade, sem, slug):
    if backend_name() == "supabase":
        url, h = _sb()
        r = requests.delete(f"{url}/rest/v1/books", headers=h, timeout=TIMEOUT,
                            params={"grade": f"eq.{grade}", "semester": f"eq.{sem}", "slug": f"eq.{slug}"})
        _check(r)
    else:
        books = [b for b in list_books()
                 if not (b["grade"] == grade and b["semester"] == sem and b["slug"] == slug)]
        LOCAL_FILE.write_text(json.dumps(books, ensure_ascii=False, indent=1), encoding="utf-8")


def export_json():
    return json.dumps(list_books(), ensure_ascii=False, indent=1)


def import_json(text):
    data = json.loads(text)
    if isinstance(data, dict):
        data = [data]
    for b in data:
        save_book(b)
    return len(data)


# ---------------------------------------------------------------- التخصصات (يديرها مدير النظام)
def _read_local_tracks():
    return json.loads(LOCAL_TRACKS_FILE.read_text(encoding="utf-8")) if LOCAL_TRACKS_FILE.exists() else []


def _write_local_tracks(rows):
    LOCAL_TRACKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_TRACKS_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def list_tracks(include_inactive=False):
    """كل التخصصات مرتبة حسب الصف ثم الترتيب ثم الاسم. [{id, grade, name, active}]"""
    if backend_name() == "supabase":
        url, h = _sb()
        params = {"select": "id,grade,name,sort_order,active", "order": "grade.asc,sort_order.asc,id.asc"}
        if not include_inactive:
            params["active"] = "eq.true"
        r = requests.get(f"{url}/rest/v1/tracks", headers=h, timeout=TIMEOUT, params=params)
        _check(r)
        return r.json()
    rows = _read_local_tracks()
    if not include_inactive:
        rows = [t for t in rows if t.get("active", True)]
    return sorted(rows, key=lambda t: (t["grade"], t.get("sort_order", 0), t["id"]))


def tracks_of_grade(tracks, grade):
    return [t for t in tracks if t["grade"] == grade and t.get("active", True)]


def track_name(tracks, track_id):
    return next((t["name"] for t in tracks if t["id"] == track_id), "")


def add_track(grade, name):
    grade, name = int(grade), (name or "").strip()
    if grade not in TRACK_GRADES:
        raise ValueError("التخصصات متاحة للصفوف العاشر والحادي عشر والثاني عشر فقط.")
    if not name:
        raise ValueError("اكتب اسم التخصص.")
    if any(t["grade"] == grade and t["name"] == name for t in list_tracks(include_inactive=True)):
        raise ValueError("هذا التخصص مضاف مسبقًا لهذا الصف.")
    if backend_name() == "supabase":
        url, h = _sb()
        r = requests.post(f"{url}/rest/v1/tracks", headers={**h, "Prefer": "return=minimal"}, timeout=TIMEOUT,
                          data=json.dumps([{"grade": grade, "name": name}]))
        _check(r)
    else:
        rows = _read_local_tracks()
        rows.append({"id": max([t["id"] for t in rows], default=0) + 1, "grade": grade, "name": name,
                     "sort_order": 0, "active": True})
        _write_local_tracks(rows)


def set_track_active(track_id, active):
    if backend_name() == "supabase":
        url, h = _sb()
        r = requests.patch(f"{url}/rest/v1/tracks", headers={**h, "Prefer": "return=minimal"}, timeout=TIMEOUT,
                           params={"id": f"eq.{track_id}"}, data=json.dumps({"active": bool(active)}))
        _check(r)
    else:
        rows = _read_local_tracks()
        for t in rows:
            if t["id"] == track_id:
                t["active"] = bool(active)
        _write_local_tracks(rows)


def delete_track(track_id):
    """يحذف تخصصًا غير مستخدم. إن كان مرتبطًا بكتب أو طلاب أو معلمين يرفض القيد في قاعدة البيانات."""
    if backend_name() == "supabase":
        url, h = _sb()
        r = requests.delete(f"{url}/rest/v1/tracks", headers=h, timeout=TIMEOUT, params={"id": f"eq.{track_id}"})
        if r.status_code == 409:
            raise ValueError("لا يمكن حذف هذا التخصص لأنه مرتبط بكتب أو طلاب أو معلمين. استخدم «إيقاف» بدلًا من الحذف.")
        _check(r)
    else:
        if any(track_id in b["track_ids"] for b in list_books()):
            raise ValueError("لا يمكن حذف هذا التخصص لأنه مرتبط بكتب. استخدم «إيقاف» بدلًا من الحذف.")
        _write_local_tracks([t for t in _read_local_tracks() if t["id"] != track_id])


# ---------------------------------------------------------------- الجدول اليدوي (وحدات ودروس)
def _empty(v):
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() == ""


def rows_to_cfg(rows):
    """يحوّل صفوف الجدول [{النوع, العنوان, الصفحة}] إلى وحدات ودروس، ويعيد (cfg, أخطاء)."""
    errors, cfg, last = [], [], 0
    for n, r in enumerate(rows, start=1):
        kind, title, page = r.get("النوع"), r.get("العنوان"), r.get("الصفحة")
        if _empty(kind) and _empty(title) and _empty(page):
            continue  # صف فارغ
        kind = str(kind or "").strip()
        title = str(title or "").strip()
        if kind not in (KIND_UNIT, KIND_LESSON):
            errors.append(f"السطر {n}: اختر النوع (وحدة أو درس).")
            continue
        if not title:
            errors.append(f"السطر {n}: العنوان فارغ.")
            continue
        try:
            page = int(float(page))
            if page < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"السطر {n}: رقم الصفحة غير صحيح.")
            continue
        if page <= last:
            errors.append(f"السطر {n}: رقم الصفحة ({page}) يجب أن يكون أكبر من الذي قبله ({last}).")
        last = max(last, page)
        if kind == KIND_UNIT:
            cfg.append({"title": title, "start": page, "lessons": []})
        else:
            if not cfg:
                errors.append(f"السطر {n}: يجب أن يسبق الدرسَ سطرُ وحدة.")
                continue
            cfg[-1]["lessons"].append({"title": title, "start": page})
    for u in cfg:
        if not u["lessons"]:
            errors.append(f"الوحدة «{u['title']}» ليس فيها دروس.")
    if not cfg and not errors:
        errors.append("الجدول فارغ.")
    return cfg, errors


def cfg_to_rows(cfg):
    rows = []
    for u in cfg:
        rows.append({"النوع": KIND_UNIT, "العنوان": u["title"], "الصفحة": u["start"]})
        for l in u["lessons"]:
            rows.append({"النوع": KIND_LESSON, "العنوان": l["title"], "الصفحة": l["start"]})
    return rows


def compute_units(cfg, offset, page_count):
    """يحوّل الأرقام المطبوعة إلى نطاقات صفحات ملف PDF (برمجيًا)."""
    def pg(p):
        return min(max(int(p) + offset, 1), max(page_count, 1))

    units = []
    for ui, u in enumerate(cfg):
        ustart = pg(u["start"])
        uend = pg(cfg[ui + 1]["start"]) - 1 if ui + 1 < len(cfg) else page_count
        uend = max(ustart, uend)
        lessons = []
        for li, l in enumerate(u["lessons"]):
            s = pg(l["start"])
            e = pg(u["lessons"][li + 1]["start"]) - 1 if li + 1 < len(u["lessons"]) else uend
            lessons.append({"title": l["title"], "start": s, "end": max(s, e)})
        units.append({"title": u["title"], "start": ustart, "end": uend, "lessons": lessons})
    return units
