"""
btec_store.py
طبقة قاعدة بيانات BTEC: Supabase (REST) إن توفرت مفاتيحه، وإلا ملف محلي data/btec_local.json (للتجربة).
فلاتر المساواة فقط: {"col": value}؛ value=None → is.null؛ list → in.(...).
"""
import json

import requests

import catalog
from config import BASE

LOCAL = BASE / "data" / "btec_local.json"
TIMEOUT = 25
PK = {"btec_staff": ("user_id", "track_id"), "btec_progress": ("assignment_id", "student_id", "criterion")}


def _sb():
    return catalog.backend_name() == "supabase"


def _f(filters):
    out = {}
    for k, v in (filters or {}).items():
        if v is None:
            out[k] = "is.null"
        elif isinstance(v, (list, tuple, set)):
            out[k] = "in.(" + ",".join(str(x) for x in v) + ")"
        else:
            out[k] = f"eq.{v}"
    return out


def _load():
    return json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}


def _save(db):
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")


def _match(row, filters):
    for k, v in (filters or {}).items():
        rv = row.get(k)
        if v is None:
            if rv is not None:
                return False
        elif isinstance(v, (list, tuple, set)):
            if rv not in v:
                return False
        elif rv != v:
            return False
    return True


def select(table, filters=None, columns="*", order=None, limit=None):
    if _sb():
        url, h = catalog._sb()
        p = {"select": columns, **_f(filters)}
        if order:
            p["order"] = order
        if limit:
            p["limit"] = limit
        r = requests.get(f"{url}/rest/v1/{table}", headers=h, timeout=TIMEOUT, params=p)
        catalog._check(r)
        return r.json()
    rows = [dict(r) for r in _load().get(table, []) if _match(r, filters)]
    if order:
        col, _, d = order.partition(".")
        rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=(d == "desc"))
    return rows[:limit] if limit else rows


def insert(table, row):
    """يعيد الصف المُدرج (مع id)."""
    if _sb():
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/{table}", headers={**h, "Prefer": "return=representation"},
                          timeout=TIMEOUT, data=json.dumps([row]))
        catalog._check(r)
        return r.json()[0]
    db = _load()
    rows = db.setdefault(table, [])
    new = {**row, "id": max([r.get("id", 0) for r in rows] or [0]) + 1}
    rows.append(new)
    _save(db)
    return new


def upsert(table, rows, on_conflict):
    if not rows:
        return []
    if _sb():
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/{table}", params={"on_conflict": on_conflict}, timeout=TIMEOUT,
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=representation"},
                          data=json.dumps(rows))
        catalog._check(r)
        return r.json()
    cols = on_conflict.split(",")
    db = _load()
    cur = db.setdefault(table, [])
    out = []
    for row in rows:
        old = next((r for r in cur if all(r.get(c) == row.get(c) for c in cols)), None)
        if old:
            old.update(row)
            out.append(old)
        else:
            new = {**row}
            if table not in PK:
                new["id"] = max([r.get("id", 0) for r in cur] or [0]) + 1
            cur.append(new)
            out.append(new)
    _save(db)
    return out


def update(table, filters, values):
    if _sb():
        url, h = catalog._sb()
        r = requests.patch(f"{url}/rest/v1/{table}", params=_f(filters), timeout=TIMEOUT,
                           headers={**h, "Prefer": "return=minimal"}, data=json.dumps(values))
        catalog._check(r)
        return
    db = _load()
    for r in db.get(table, []):
        if _match(r, filters):
            r.update(values)
    _save(db)


def delete(table, filters):
    if _sb():
        url, h = catalog._sb()
        r = requests.delete(f"{url}/rest/v1/{table}", params=_f(filters), timeout=TIMEOUT,
                            headers={**h, "Prefer": "return=minimal"})
        catalog._check(r)
        return
    db = _load()
    db[table] = [r for r in db.get(table, []) if not _match(r, filters)]
    _save(db)


# ---------------------------------------------------------------- واجهات جاهزة
def staff_rows(user_id):
    return select("btec_staff", {"user_id": user_id})


def assignments_for(grade, track_id, published_only=False, columns="*", subject="all"):
    """subject: "all" = كل المباحث، "none" = بلا مبحث، أو رقم مبحث."""
    f = {"grade": grade, "track_id": track_id}
    if published_only:
        f["published"] = True
    if subject == "none":
        f["subject_id"] = None
    elif subject != "all":
        f["subject_id"] = int(subject)
    return select("btec_assignments", f, columns=columns, order="id.desc")


def subjects_for(track_id, active_only=True):
    f = {"track_id": track_id}
    if active_only:
        f["active"] = True
    return select("btec_subjects", f, order="sort_order.asc")


def assignment(aid):
    rows = select("btec_assignments", {"id": aid})
    return rows[0] if rows else None


# ---------------------------------------------------------------- مباحث BTEC في تسجيل المعلمين
BTEC_PREFIX = "BTEC: "   # يُضاف لاسم المبحث في قائمة التسجيل ليتميّز عن مباحث الكتب


def btec_subject_names():
    """أسماء مباحث BTEC الفعّالة (بلا تكرار) لعرضها في نموذج تسجيل المعلم."""
    return sorted({r["name"] for r in select("btec_subjects", {"active": True}, columns="name")})


def btec_subject_pairs():
    """{(track_id, name)} لكل مبحث BTEC فعّال."""
    return {(r["track_id"], r["name"]) for r in select("btec_subjects", {"active": True}, columns="track_id,name")}


def assign_teacher(user_id, track_ids):
    """يعيّن المعلم «معلم BTEC» على هذه التخصصات/الصفوف دون المساس بدور المشرف إن كان معيّنًا فيها."""
    have = {r["track_id"] for r in select("btec_staff", {"user_id": user_id})}
    rows = [{"user_id": user_id, "track_id": t, "role": "teacher"} for t in track_ids if t not in have]
    upsert("btec_staff", rows, "user_id,track_id")
