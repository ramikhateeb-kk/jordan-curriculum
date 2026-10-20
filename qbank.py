"""
قاعدة بيانات أسئلة "قيمني": الأسئلة المولَّدة تُخزَّن هنا وتُعاد الاستفادة منها لأي طالب لاحقًا،
فلا يُطلب من Gemini توليد سؤال جديد لنفس الدرس إلا عند نفاد الأسئلة المخزَّنة له.
يستخدم نفس تخزين catalog.py (Supabase إن وُجدت مفاتيحه، وإلا ملف محلي مؤقت).
"""
import json

import requests

import catalog
from config import BASE

LOCAL_FILE = BASE / "data" / "qbank.json"
TIMEOUT = 20


def _local_all():
    return json.loads(LOCAL_FILE.read_text(encoding="utf-8")) if LOCAL_FILE.exists() else []


def list_questions(slug, page_start, page_end, qtype):
    """يعيد [(id, بيانات السؤال)] لهذا الكتاب والدرس ونوع السؤال."""
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/questions", headers=h, timeout=TIMEOUT, params={
            "select": "id,data", "slug": f"eq.{slug}",
            "page_start": f"eq.{page_start}", "page_end": f"eq.{page_end}", "qtype": f"eq.{qtype}"})
        catalog._check(r)
        return [(row["id"], row["data"]) for row in r.json()]
    rows = _local_all()
    return [(i, r["data"]) for i, r in enumerate(rows)
            if r["slug"] == slug and r["page_start"] == page_start and r["page_end"] == page_end
            and r["qtype"] == qtype]


def add_question(slug, page_start, page_end, qtype, q):
    """يحفظ سؤالًا مولَّدًا حديثًا ليُعاد استخدامه لاحقًا، ويعيد معرّف الصف الجديد (id)
    ليتمكن المستدعي من استثنائه فورًا من الاختيار العشوائي في الجلسة الحالية (وإلا فقد يُعرَض
    السؤال نفسه الذي وُلِّد للتو مرة أخرى بوصفه "من البنك")."""
    row = {"slug": slug, "page_start": page_start, "page_end": page_end, "qtype": qtype, "data": q}
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/questions", headers={**h, "Prefer": "return=representation"},
                          timeout=TIMEOUT, data=json.dumps([row]))
        catalog._check(r)
        try:
            return r.json()[0]["id"]
        except Exception:  # noqa: BLE001
            return None
    rows = _local_all()
    rows.append(row)
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return len(rows) - 1


def list_by_slugs(slugs):
    """يعيد [(id, slug, page_start, page_end, qtype, بيانات السؤال)] لكل أسئلة مجموعة من الكتب (slugs)،
    تُستخدم لاستعراض بنك الأسئلة حسب المبحث (مجموعة كتب هذا المبحث عبر الصفوف) في لوحة المشرف/المدير."""
    if not slugs:
        return []
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/questions", headers=h, timeout=TIMEOUT, params={
            "select": "id,slug,page_start,page_end,qtype,data", "slug": f"in.({','.join(slugs)})"})
        catalog._check(r)
        return [(row["id"], row["slug"], row["page_start"], row["page_end"], row["qtype"], row["data"])
                for row in r.json()]
    rows = _local_all()
    return [(i, r["slug"], r["page_start"], r["page_end"], r["qtype"], r["data"])
            for i, r in enumerate(rows) if r["slug"] in slugs]


def update_question(question_id, data):
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.patch(f"{url}/rest/v1/questions", headers={**h, "Prefer": "return=minimal"},
                           timeout=TIMEOUT, params={"id": f"eq.{question_id}"}, data=json.dumps({"data": data}))
        catalog._check(r)
        return
    rows = _local_all()
    rows[question_id]["data"] = data
    LOCAL_FILE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def delete_question(question_id):
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.delete(f"{url}/rest/v1/questions", headers=h, timeout=TIMEOUT,
                            params={"id": f"eq.{question_id}"})
        catalog._check(r)
        return
    rows = _local_all()
    rows.pop(question_id)
    LOCAL_FILE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
