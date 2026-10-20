"""
plan_cache.py
تخزين محتوى خطط الدروس، والخطط الفصلية، وتحليل المحتوى، ودليل المعلم المولَّدة بالذكاء الاصطناعي،
لإعادة استخدامها لأي معلم يطلب المبحث/الدرس نفسه لاحقًا دون تكرار الطلب إلى Gemini.
"""
import json
import requests

import catalog
from config import BASE

LOCAL_LESSON_FILE = BASE / "data" / "plan_cache.json"
LOCAL_SEMESTER_FILE = BASE / "data" / "semester_plan_cache.json"
LOCAL_ANALYSIS_FILE = BASE / "data" / "content_analysis_cache.json"
LOCAL_GUIDE_FILE = BASE / "data" / "teacher_guide_cache.json"

TIMEOUT = 20


# ==============================================================================
# 1. خطة الدرس اليومية (Lesson Plans)
# ==============================================================================

def get_plan(slug, page_start, page_end):
    """يعيد محتوى خطة الدرس المخزَّنة لهذا النطاق من الكتاب، أو None إن لم توجد."""
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/lesson_plans", headers=h, timeout=TIMEOUT, params={
            "select": "data", "slug": f"eq.{slug}",
            "page_start": f"eq.{page_start}", "page_end": f"eq.{page_end}"})
        catalog._check(r)
        rows = r.json()
        return rows[0]["data"] if rows else None
    rows = json.loads(LOCAL_LESSON_FILE.read_text(encoding="utf-8")) if LOCAL_LESSON_FILE.exists() else []
    for row in rows:
        if row["slug"] == slug and row["page_start"] == page_start and row["page_end"] == page_end:
            return row["data"]
    return None


def save_plan(slug, page_start, page_end, data):
    row = {"slug": slug, "page_start": page_start, "page_end": page_end, "data": data}
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/lesson_plans",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                          timeout=TIMEOUT, params={"on_conflict": "slug,page_start,page_end"},
                          data=json.dumps([row]))
        catalog._check(r)
        return
    rows = json.loads(LOCAL_LESSON_FILE.read_text(encoding="utf-8")) if LOCAL_LESSON_FILE.exists() else []
    rows = [r for r in rows if not (r["slug"] == slug and r["page_start"] == page_start
                                    and r["page_end"] == page_end)]
    rows.append(row)
    LOCAL_LESSON_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_LESSON_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


# ==============================================================================
# 2. الخطة الفصلية (Semester Plans)
# ==============================================================================

def get_semester_plan(slug):
    """يعيد محتوى الخطة الفصلية المخزَّنة لهذا المبحث (slug)، أو None إن لم توجد."""
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/semester_plans", headers=h, timeout=TIMEOUT, params={
            "select": "data", "slug": f"eq.{slug}"})
        catalog._check(r)
        rows = r.json()
        return rows[0]["data"] if rows else None
    rows = json.loads(LOCAL_SEMESTER_FILE.read_text(encoding="utf-8")) if LOCAL_SEMESTER_FILE.exists() else []
    for row in rows:
        if row["slug"] == slug:
            return row["data"]
    return None


def save_semester_plan(slug, data):
    """يحفظ الخطة الفصلية للمبحث في Supabase أو الملف المحلي."""
    row = {"slug": slug, "data": data}
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/semester_plans",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                          timeout=TIMEOUT, params={"on_conflict": "slug"},
                          data=json.dumps([row]))
        catalog._check(r)
        return
    rows = json.loads(LOCAL_SEMESTER_FILE.read_text(encoding="utf-8")) if LOCAL_SEMESTER_FILE.exists() else []
    rows = [r for r in rows if r["slug"] != slug]
    rows.append(row)
    LOCAL_SEMESTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_SEMESTER_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


# ==============================================================================
# 3. تحليل المحتوى (Content Analysis)
# ==============================================================================

def get_content_analysis(slug):
    """يعيد محتوى تحليل المحتوى المخزَّن لهذا المبحث (slug)، أو None إن لم توجد."""
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/content_analysis", headers=h, timeout=TIMEOUT, params={
            "select": "data", "slug": f"eq.{slug}"})
        catalog._check(r)
        rows = r.json()
        return rows[0]["data"] if rows else None
    rows = json.loads(LOCAL_ANALYSIS_FILE.read_text(encoding="utf-8")) if LOCAL_ANALYSIS_FILE.exists() else []
    for row in rows:
        if row["slug"] == slug:
            return row["data"]
    return None


def save_content_analysis(slug, data):
    """يحفظ تحليل المحتوى للمبحث في Supabase أو الملف المحلي."""
    row = {"slug": slug, "data": data}
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/content_analysis",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                          timeout=TIMEOUT, params={"on_conflict": "slug"},
                          data=json.dumps([row]))
        catalog._check(r)
        return
    rows = json.loads(LOCAL_ANALYSIS_FILE.read_text(encoding="utf-8")) if LOCAL_ANALYSIS_FILE.exists() else []
    rows = [r for r in rows if r["slug"] != slug]
    rows.append(row)
    LOCAL_ANALYSIS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_ANALYSIS_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


# ==============================================================================
# 4. دليل المعلم الشامل (Teacher Guides)
# ==============================================================================

def get_teacher_guide(lesson_key):
    """يعيد محتوى دليل الشرح المخزن لهذا الدرس/الصف."""
    if catalog.backend_name() == "supabase":
        try:
            url, h = catalog._sb()
            r = requests.get(
                f"{url}/rest/v1/teacher_guides", 
                headers=h, 
                timeout=TIMEOUT, 
                params={"select": "content", "book_slug": f"eq.{lesson_key}"}
            )
            catalog._check(r)
            rows = r.json()
            return rows[0]["content"] if rows else None
        except Exception as e:
            print("خطأ جلب دليل الشرح من Supabase:", e)
            return None

    rows = json.loads(LOCAL_GUIDE_FILE.read_text(encoding="utf-8")) if LOCAL_GUIDE_FILE.exists() else []
    for row in rows:
        if row.get("book_slug") == lesson_key:
            return row.get("content")
    return None


def save_teacher_guide(lesson_key, content, subject):
    """يحفظ دليل الشرح في Supabase أو الملف المحلي."""
    row = {
        "book_slug": lesson_key,
        "lesson_title": lesson_key,
        "subject": subject,
        "content": content
    }
    if catalog.backend_name() == "supabase":
        try:
            url, h = catalog._sb()
            r = requests.post(
                f"{url}/rest/v1/teacher_guides",
                headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                timeout=TIMEOUT,
                params={"on_conflict": "book_slug,lesson_title"},
                data=json.dumps([row])
            )
            catalog._check(r)
            return True
        except Exception as e:
            print("خطأ حفظ دليل الشرح في Supabase:", e)
            return False

    rows = json.loads(LOCAL_GUIDE_FILE.read_text(encoding="utf-8")) if LOCAL_GUIDE_FILE.exists() else []
    rows = [r for r in rows if r.get("book_slug") != lesson_key]
    rows.append(row)
    LOCAL_GUIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_GUIDE_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
