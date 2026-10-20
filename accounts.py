"""
accounts.py
نظام الحسابات والصلاحيات: تسجيل/دخول، جلسة واحدة نشطة لكل حساب، حالة الاشتراك،
صلاحيات المعلم (مباحث/صفوف معتمدة)، صلاحيات المشرف (مباحث إشراف)، والحصة اليومية لجيمناي.
لا علاقة له بمحتوى الكتب أو الأسئلة؛ catalog.py/qbank.py تبقى كما هي.
"""
import hashlib
import json
import secrets
from datetime import date

import requests

import catalog
from config import GRADES
from hijri import hijri_school_year

TIMEOUT = 20
ROLE_AR = {"student": "طالب", "teacher": "معلم", "supervisor": "مشرف", "admin": "مدير عام",
           "trial": "معلم تجريبي"}   # «trial» ليس دورًا مخزَّنًا؛ يُستخدم فقط كمفتاح لحدّه اليومي
SESSION_RECHECK_SECONDS = 60   # كم ثانية بين كل تحقق من الجلسة (لتقليل عدد الطلبات إلى Supabase)
DEFAULT_LIMITS = {"student": 8, "teacher": 15, "supervisor": 30, "trial": 5}
# مزايا المعلم القابلة للتقييد في الحساب التجريبي (المفتاح الداخلي → الاسم المعروض)
TRIAL_FEATURES = {
    "lesson_plan": "خطة الدرس (العدد = دروس)", "semester_plan": "الخطة الفصلية (العدد = دروس)",
    "content_analysis": "تحليل المحتوى", "exam": "إنشاء اختبار", "slides": "العرض التقديمي",
    "teach_help": "مساعد الشرح", "attendance": "دفتر الحضور والغياب", "marks_book": "دفتر العلامات",
}
# المزايا المحسوبة بالأعداد؛ البقية تعمل «مفتوحة/مقفلة» فقط (0 = مقفلة)
TRIAL_COUNTED = ("lesson_plan", "semester_plan")


# ---------------------------------------------------------------- أدوات عامة
def _sb():
    return catalog._sb()


def _rest(method, path, headers_extra=None, **kw):
    url, h = _sb()
    if headers_extra:
        h = {**h, **headers_extra}
    r = requests.request(method, f"{url}/rest/v1/{path}", headers=h, timeout=TIMEOUT, **kw)
    catalog._check(r)
    return r.json() if r.text else None


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return f"{salt}${h.hex()}"


def verify_password(password, stored):
    try:
        salt, _ = stored.split("$", 1)
    except (ValueError, AttributeError):
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def today():
    return date.today().isoformat()


def class_label(grade, track=None):
    """«العاشر هندسي» أو «التاسع» — الاسم المستخدم في النماذج والملفات."""
    name = GRADES[int(grade) - 1]
    return f"{name} {track}".strip() if track else name


# ---------------------------------------------------------------- تسجيل حساب جديد
def phone_exists(phone):
    rows = _rest("GET", "users", params={"select": "id", "phone": f"eq.{phone}"})
    return bool(rows)


def register_student(name, phone, password, grade, email=None, track_id=None):
    if phone_exists(phone):
        raise ValueError("رقم الهاتف مستخدم مسبقًا. إن كان لديك حساب يمكنك تسجيل الدخول مباشرة.")
    row = {"name": name.strip(), "phone": phone.strip(), "email": (email or "").strip() or None,
           "password_hash": hash_password(password), "role": "student", "status": "pending",
           "grade": int(grade), "track_id": int(track_id) if track_id else None}
    _rest("POST", "users", data=json.dumps([row]), headers_extra={"Prefer": "return=minimal"})


def register_teacher(name, phone, password, subjects_grades, directorate, division, school_name, email=None):
    """subjects_grades: [{"subject": "...", "grade": 11, "track_id": 3 (اختياري للصفوف 10-12)}, ...] — يبقى الحساب قيد المراجعة حتى يعتمده المدير.
    directorate (المديرية)، division (اللواء)، school_name (اسم المدرسة، إجباري) تُستخدم كترويسة للملفات الرسمية."""
    if phone_exists(phone):
        raise ValueError("رقم الهاتف مستخدم مسبقًا. إن كان لديك حساب يمكنك تسجيل الدخول مباشرة.")
    if not subjects_grades:
        raise ValueError("يرجى اختيار مبحث وصف واحد على الأقل.")
    if not school_name or not school_name.strip():
        raise ValueError("اسم المدرسة إجباري.")
    row = {"name": name.strip(), "phone": phone.strip(), "email": (email or "").strip() or None,
           "password_hash": hash_password(password), "role": "teacher", "status": "pending",
           "requested_subjects": subjects_grades, "directorate": (directorate or "").strip() or None,
           "division": (division or "").strip() or None, "school_name": school_name.strip()}
    _rest("POST", "users", data=json.dumps([row]), headers_extra={"Prefer": "return=minimal"})


# ---------------------------------------------------------------- الدخول + الجلسة الواحدة
def login(phone, password):
    """يتحقق من كلمة المرور، ينشئ رمز جلسة جديد (يُبطل أي جلسة سابقة)، ويعيد بيانات المستخدم أو يرفع خطأ."""
    rows = _rest("GET", "users", params={"select": "*", "phone": f"eq.{phone.strip()}"})
    if not rows:
        raise ValueError("رقم الهاتف أو كلمة المرور غير صحيحة.")
    user = rows[0]
    if not verify_password(password, user["password_hash"]):
        raise ValueError("رقم الهاتف أو كلمة المرور غير صحيحة.")
    if user["status"] == "pending":
        raise ValueError("حسابك قيد المراجعة من الإدارة، يرجى الانتظار حتى يتم تفعيله.")
    if user["status"] == "rejected":
        raise ValueError("تم رفض طلب تسجيلك. يرجى التواصل مع الإدارة لمزيد من التفاصيل.")
    if user["status"] == "suspended":
        raise ValueError("تم إيقاف حسابك. يرجى التواصل مع الإدارة.")

    token = secrets.token_hex(24)
    _rest("PATCH", "users", params={"id": f"eq.{user['id']}"},
          data=json.dumps({"session_token": token, "session_created_at": "now()"}),
          headers_extra={"Prefer": "return=minimal"})
    user["session_token"] = token
    return user


def session_still_valid(user_id, local_token):
    """يقارن رمز الجلسة المحلي مع الرمز الحالي في قاعدة البيانات؛ يُستخدم لإنفاذ "جلسة واحدة فقط"."""
    rows = _rest("GET", "users", params={"select": "session_token", "id": f"eq.{user_id}"})
    return bool(rows) and rows[0]["session_token"] == local_token


def logout(user_id):
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"},
          data=json.dumps({"session_token": None}), headers_extra={"Prefer": "return=minimal"})


def get_user(user_id):
    rows = _rest("GET", "users", params={"select": "*", "id": f"eq.{user_id}"})
    return rows[0] if rows else None


# ---------------------------------------------------------------- حالة الاشتراك
def subscription_active(user):
    if user["role"] == "admin":
        return True
    end = user.get("subscription_end")
    return bool(end) and end >= today()


# ---------------------------------------------------------------- صلاحيات المعلم/المشرف (مباحث وصفوف)
def teacher_scope(user_id):
    """يعيد [{"subject","grade","track_id"}, ...] المعتمدة فعليًا لهذا المعلم.
    track_id=None للصفوف 10-12 يعني «كل تخصصات الصف»؛ وللصفوف 1-9 لا معنى له."""
    rows = _rest("GET", "teacher_subjects", params={"select": "subject,grade,track_id", "user_id": f"eq.{user_id}"})
    return rows or []


def teacher_subjects_set(user_id):
    return {r["subject"] for r in teacher_scope(user_id)}


def _scope_allows(row, subject, grade, track_id):
    return (row["subject"] == subject and row["grade"] == int(grade)
            and (row.get("track_id") is None or track_id is None or row["track_id"] == track_id))


def teacher_allowed(user_id, subject, grade, track_id=None):
    return any(_scope_allows(r, subject, grade, track_id) for r in teacher_scope(user_id))


def supervisor_subjects(user_id):
    rows = _rest("GET", "supervisor_subjects", params={"select": "subject", "user_id": f"eq.{user_id}"})
    return [r["subject"] for r in (rows or [])]


def filter_books_for_user(user, books, scope=None):
    """كل الكتب التي يحق لهذا المستخدم رؤيتها في أي صف/تخصص (للتحقق من وجود شيء له أصلًا)."""
    if user["role"] == "admin":
        return books
    if user["role"] == "student":
        g = user.get("grade")
        return [b for b in books if catalog.book_in_track(b, g, user.get("track_id"))] if g else books
    if user["role"] == "teacher":
        scope = scope if scope is not None else teacher_scope(user["id"])
        return [b for b in books if any(
            _scope_allows(r, b["subject"], b["grade"], None) and
            (r.get("track_id") is None or catalog.is_common(b) or r["track_id"] in b["track_ids"])
            for r in scope)]
    if user["role"] == "supervisor":
        scope = scope if scope is not None else teacher_scope(user["id"])
        subs = set(supervisor_subjects(user["id"])) | {r["subject"] for r in scope}
        return [b for b in books if b["subject"] in subs]
    return []


def grade_options(user, books, scope=None):
    """الصفوف التي يختار منها المستخدم (أرقام 1-12)."""
    if user["role"] == "admin":
        return list(range(1, 13))
    if user["role"] == "student":
        return [user["grade"]] if user.get("grade") else []
    return sorted({b["grade"] for b in filter_books_for_user(user, books, scope)})


def tracks_for_user(user, tracks, grade, books=None, scope=None):
    """التخصصات التي يختار منها المستخدم في هذا الصف (قائمة فارغة = الصف بلا تخصصات)."""
    if grade not in catalog.TRACK_GRADES:
        return []
    active = catalog.tracks_of_grade(tracks, grade)
    if user["role"] == "student":
        return [t for t in active if t["id"] == user.get("track_id")]
    if user["role"] == "teacher":
        scope = scope if scope is not None else teacher_scope(user["id"])
        rows = [r for r in scope if r["grade"] == grade]
        if any(r.get("track_id") is None for r in rows):
            return active
        allowed = {r["track_id"] for r in rows}
        return [t for t in active if t["id"] in allowed]
    return active


def books_in_context(user, books, grade, track_id, scope=None):
    """كتب هذا الصف وهذا التخصص التي يحق للمستخدم رؤيتها: المشتركة + الخاصة بالتخصص."""
    in_ctx = [b for b in books if catalog.book_in_track(b, grade, track_id)]
    if user["role"] in ("admin", "student"):
        return in_ctx
    if user["role"] == "teacher":
        scope = scope if scope is not None else teacher_scope(user["id"])
        return [b for b in in_ctx if any(_scope_allows(r, b["subject"], grade, track_id) for r in scope)]
    if user["role"] == "supervisor":
        return [b for b in in_ctx if b in filter_books_for_user(user, in_ctx, scope)]
    return []


def class_options(user_id, tracks, scope=None):
    """الصفوف/التخصصات التي يُدرّسها المعلم كقائمة اختيار لنماذج الحضور والعلامات:
    [{"grade","track_id","track","label","subjects":[...]}]. صف 10-12 بلا تخصص محدد = يُوسَّع إلى كل تخصصات الصف."""
    scope = scope if scope is not None else teacher_scope(user_id)
    out = {}
    for r in scope:
        g = r["grade"]
        if g in catalog.TRACK_GRADES:
            active = catalog.tracks_of_grade(tracks, g)
            targets = active if r.get("track_id") is None else [t for t in active if t["id"] == r["track_id"]]
            targets = targets or [None]
        else:
            targets = [None]
        for t in targets:
            key = (g, t["id"] if t else None)
            o = out.setdefault(key, {"grade": g, "track_id": key[1], "track": t["name"] if t else "",
                                     "label": class_label(g, t["name"] if t else ""), "subjects": []})
            if r["subject"] not in o["subjects"]:
                o["subjects"].append(r["subject"])
    return sorted(out.values(), key=lambda o: (o["grade"], o["track"]))


def can_access_qbank_admin(user):
    return user["role"] in ("admin", "supervisor")


def qbank_subject_scope(user):
    """المباحث التي يحق لهذا المستخدم استعراض/تعديل/حذف أسئلتها في بنك الأسئلة. None = بلا قيد (كل المباحث)."""
    if user["role"] == "admin":
        return None
    if user["role"] == "supervisor":
        return set(supervisor_subjects(user["id"]))
    return set()   # المعلم العادي: لا صلاحية إطلاقًا (تُستخدم هذه القيمة الفارغة لإخفاء التبويب)


# ---------------------------------------------------------------- الحصة اليومية من جيمناي
def get_limit(role):
    rows = _rest("GET", "role_limits", params={"select": "daily_limit", "role": f"eq.{role}"})
    return rows[0]["daily_limit"] if rows else DEFAULT_LIMITS.get(role, 10)


def limit_role(user):
    """المفتاح الذي يُحسب عليه الحد اليومي: المعلم التجريبي له حدّه الخاص."""
    return "trial" if user.get("is_trial") and user["role"] == "teacher" else user["role"]


def set_limit(role, limit):
    _rest("POST", "role_limits", data=json.dumps([{"role": role, "daily_limit": int(limit)}]),
          params={"on_conflict": "role"}, headers_extra={"Prefer": "resolution=merge-duplicates,return=minimal"})


def usage_today(user_id):
    rows = _rest("GET", "daily_usage", params={"select": "count", "user_id": f"eq.{user_id}",
                                                "usage_day": f"eq.{today()}"})
    return rows[0]["count"] if rows else 0


def use_quota(user):
    """يتحقق من الحصة اليومية ويزيدها بمقدار 1 إن سُمح بالطلب. يُستدعى فقط قبل استدعاء فعلي لجيمناي،
    وليس عند الاسترجاع من قاعدة البيانات. يعيد (مسموح؟, رسالة الرفض إن وُجدت)."""
    if user["role"] == "admin":
        return True, ""
    limit = get_limit(limit_role(user))
    used = usage_today(user["id"])
    if used >= limit:
        return False, (f"لقد استنفدت عدد طلباتك اليوم ({limit} طلبًا) التي تحتاج الذكاء الاصطناعي. "
                       "يمكنك المحاولة غدًا، وتبقى الخدمات المحفوظة مسبقًا في قاعدة البيانات متاحة لك دون قيد.")
    _rest("POST", "daily_usage", data=json.dumps([{"user_id": user["id"], "usage_day": today(), "count": used + 1}]),
          params={"on_conflict": "user_id,usage_day"},
          headers_extra={"Prefer": "resolution=merge-duplicates,return=minimal"})
    return True, ""


# ---------------------------------------------------------------- لوحة المدير العام
def list_users(status=None, role=None):
    params = {"select": "*", "order": "created_at.desc"}
    if status:
        params["status"] = f"eq.{status}"
    if role:
        params["role"] = f"eq.{role}"
    return _rest("GET", "users", params=params) or []


def approve_teacher(user_id, approved_by_id, subjects_grades, subscription_end, trial=False):
    """يعتمد حساب معلم: يكتب فقط المباحث/الصفوف التي أبقاها المدير في القائمة إلى teacher_subjects،
    ثم يفعّل الحساب. subjects_grades: [{"subject":..., "grade":...}, ...] (بعد مراجعة/تعديل المدير)."""
    set_teacher_subjects(user_id, approved_by_id, subjects_grades)
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"},
          data=json.dumps({"status": "active", "approved_by": approved_by_id, "approved_at": "now()",
                           "subscription_end": subscription_end, "is_trial": bool(trial)}),
          headers_extra={"Prefer": "return=minimal"})


def approve_student(user_id, approved_by_id, subscription_end, track_id=None):
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"},
          data=json.dumps({"status": "active", "approved_by": approved_by_id, "approved_at": "now()",
                           "subscription_end": subscription_end, "track_id": track_id}),
          headers_extra={"Prefer": "return=minimal"})


def reject_user(user_id):
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"},
          data=json.dumps({"status": "rejected"}), headers_extra={"Prefer": "return=minimal"})


def suspend_user(user_id, suspended=True):
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"},
          data=json.dumps({"status": "suspended" if suspended else "active", "session_token": None}),
          headers_extra={"Prefer": "return=minimal"})


def set_subscription(user_id, subscription_end):
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"},
          data=json.dumps({"subscription_end": subscription_end}), headers_extra={"Prefer": "return=minimal"})


def set_role(user_id, role):
    """تحويل معلم↔مشرف (أو أي تغيير دور يقرره المدير)."""
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"},
          data=json.dumps({"role": role}), headers_extra={"Prefer": "return=minimal"})


def set_teacher_subjects(user_id, approved_by_id, subjects_grades):
    """يستبدل مباحث/صفوف معلم بالكامل بقائمة جديدة يحددها المدير لاحقًا."""
    url, h = _sb()
    r = requests.delete(f"{url}/rest/v1/teacher_subjects", headers=h, timeout=TIMEOUT,
                        params={"user_id": f"eq.{user_id}"})
    catalog._check(r)
    if subjects_grades:
        seen, rows = set(), []
        for sg in subjects_grades:
            tid = sg.get("track_id") or None
            key = (sg["subject"], int(sg["grade"]), tid)
            if key not in seen:
                seen.add(key)
                rows.append({"user_id": user_id, "subject": sg["subject"], "grade": int(sg["grade"]),
                             "track_id": tid, "approved_by": approved_by_id})
        _rest("POST", "teacher_subjects", data=json.dumps(rows), headers_extra={"Prefer": "return=minimal"})


def add_supervisor_subject(user_id, subject):
    _rest("POST", "supervisor_subjects", data=json.dumps([{"user_id": user_id, "subject": subject}]),
          params={"on_conflict": "user_id,subject"},
          headers_extra={"Prefer": "resolution=merge-duplicates,return=minimal"})


def remove_supervisor_subject(user_id, subject):
    url, h = _sb()
    r = requests.delete(f"{url}/rest/v1/supervisor_subjects", headers=h, timeout=TIMEOUT,
                        params={"user_id": f"eq.{user_id}", "subject": f"eq.{subject}"})
    catalog._check(r)


def update_profile(user_id, directorate=None, division=None, school_name=None):
    """تعديل بيانات ترويسة المعلم (مديرية/لواء/مدرسة) من لوحة المدير أو لاحقًا من حساب المعلم نفسه."""
    patch = {}
    if directorate is not None:
        patch["directorate"] = directorate.strip() or None
    if division is not None:
        patch["division"] = division.strip() or None
    if school_name is not None:
        patch["school_name"] = school_name.strip() or None
    if patch:
        _rest("PATCH", "users", params={"id": f"eq.{user_id}"}, data=json.dumps(patch),
              headers_extra={"Prefer": "return=minimal"})


# ---------------------------------------------------------------- العطل والأعياد الرسمية (يديرها المدير)
def list_holidays():
    rows = _rest("GET", "holidays", params={"select": "*", "order": "holiday_date.asc"})
    return rows or []


def add_holiday(holiday_date, name=None):
    _rest("POST", "holidays", data=json.dumps([{"holiday_date": holiday_date, "name": (name or "").strip() or None}]),
          params={"on_conflict": "holiday_date"},
          headers_extra={"Prefer": "resolution=merge-duplicates,return=minimal"})


def remove_holiday(holiday_id):
    url, h = _sb()
    r = requests.delete(f"{url}/rest/v1/holidays", headers=h, timeout=TIMEOUT, params={"id": f"eq.{holiday_id}"})
    catalog._check(r)


def get_academic_calendar():
    """يعيد {"year1","sem1_start","sem1_end","sem2_start","sem2_end"} أو None إن لم يحدّدها المدير بعد."""
    rows = _rest("GET", "academic_calendar", params={"select": "*", "id": "eq.1"})
    return rows[0] if rows else None


def set_academic_calendar(year1, sem1_start, sem1_end, sem2_start, sem2_end, hijri_label=None):
    row = {"id": 1, "year1": int(year1), "sem1_start": sem1_start, "sem1_end": sem1_end,
           "sem2_start": sem2_start, "sem2_end": sem2_end, "hijri_label": (hijri_label or "").strip() or None}
    _rest("POST", "academic_calendar", data=json.dumps([row]), params={"on_conflict": "id"},
          headers_extra={"Prefer": "resolution=merge-duplicates,return=minimal"})


def year_labels(cal):
    """{"greg": "2026/2027", "hijri": "1448/1449"} من التقويم الدراسي، أو None إن لم يُحدَّد.
    العام الهجري: ما كتبه المدير يدويًا إن وُجد، وإلا يُحسب من بداية الفصل الأول ونهاية الفصل الثاني."""
    if not cal:
        return None
    hijri = (cal.get("hijri_label") or "").strip()
    if not hijri:
        hijri = hijri_school_year(date.fromisoformat(str(cal["sem1_start"])), date.fromisoformat(str(cal["sem2_end"])))
    return {"greg": f"{cal['year1']}/{cal['year1'] + 1}", "hijri": hijri}


# ---------------------------------------------------------------- تخصص الطالب + الحساب التجريبي
def set_user_track(user_id, track_id):
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"}, data=json.dumps({"track_id": track_id}),
          headers_extra={"Prefer": "return=minimal"})


def is_trial(user):
    return bool(user.get("is_trial")) and user["role"] == "teacher"


def set_trial(user_id, flag):
    _rest("PATCH", "users", params={"id": f"eq.{user_id}"}, data=json.dumps({"is_trial": bool(flag)}),
          headers_extra={"Prefer": "return=minimal"})


def trial_limits():
    """{feature: max_count} — القيم الافتراضية إن لم يضبطها المدير: خطة درس 1، خطة فصلية 1، والباقي مقفل."""
    limits = {f: (1 if f in TRIAL_COUNTED else 0) for f in TRIAL_FEATURES}
    for r in _rest("GET", "trial_limits", params={"select": "feature,max_count"}) or []:
        if r["feature"] in limits:
            limits[r["feature"]] = r["max_count"]
    return limits


def set_trial_limit(feature, max_count):
    _rest("POST", "trial_limits", data=json.dumps([{"feature": feature, "max_count": int(max_count)}]),
          params={"on_conflict": "feature"},
          headers_extra={"Prefer": "resolution=merge-duplicates,return=minimal"})


def trial_used(user_id, feature):
    rows = _rest("GET", "trial_usage", params={"select": "count", "user_id": f"eq.{user_id}",
                                                "feature": f"eq.{feature}"})
    return rows[0]["count"] if rows else 0


def trial_remaining(user, feature):
    """None = ليس حسابًا تجريبيًا (بلا قيد). وإلا المتبقي: للمزايا المحسوبة عدد الدروس المتبقية،
    وللبقية 1 إن كانت مفتوحة أو 0 إن كانت مقفلة."""
    if not is_trial(user):
        return None
    limit = trial_limits().get(feature, 0)
    if feature in TRIAL_COUNTED:
        return max(limit - trial_used(user["id"], feature), 0)
    return 1 if limit > 0 else 0


def trial_consume(user, feature, n=1):
    """يسجّل استهلاك المعلم التجريبي (لا يفعل شيئًا لغيره). يُستدعى بعد نجاح التوليد فقط."""
    if not is_trial(user) or feature not in TRIAL_COUNTED or n <= 0:
        return
    used = trial_used(user["id"], feature)
    _rest("POST", "trial_usage", data=json.dumps([{"user_id": user["id"], "feature": feature, "count": used + n}]),
          params={"on_conflict": "user_id,feature"},
          headers_extra={"Prefer": "resolution=merge-duplicates,return=minimal"})


def delete_user(user_id):
    url, h = _sb()
    r = requests.delete(f"{url}/rest/v1/users", headers=h, timeout=TIMEOUT, params={"id": f"eq.{user_id}"})
    catalog._check(r)
