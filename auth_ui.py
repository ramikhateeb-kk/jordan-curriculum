"""
auth_ui.py
واجهات الحسابات: تسجيل دخول، تسجيل طالب/معلم جديد، بوابة التحقق (جلسة واحدة + اشتراك فعّال)،
ولوحة المدير العام لإدارة الحسابات والصلاحيات.
"""
import time

import streamlit as st

import accounts as acc
import catalog
from hijri import hijri_school_year
from config import GRADES

SUBJECTS_FALLBACK = ["لغة عربية", "لغة إنجليزية", "رياضيات", "علوم", "تاريخ", "جغرافيا",
                     "تربية إسلامية", "تربية وطنية", "فيزياء", "كيمياء", "أحياء"]


def _all_subjects():
    try:
        import catalog
        subs = sorted({b["subject"] for b in catalog.list_books()})
        return subs or SUBJECTS_FALLBACK
    except Exception:  # noqa: BLE001
        return SUBJECTS_FALLBACK


def _all_tracks():
    try:
        return catalog.list_tracks()
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------- نماذج التسجيل
def _register_student_form():
    tracks = _all_tracks()
    # الصف والتخصص خارج النموذج لأن قائمة التخصصات تتغير حسب الصف المختار
    grade_name = st.selectbox("الصف الدراسي", [f"الصف {g}" for g in GRADES], key="reg_st_grade")
    grade = GRADES.index(grade_name.replace("الصف ", "")) + 1
    grade_tracks = catalog.tracks_of_grade(tracks, grade)
    track_id = None
    if grade_tracks:
        pick = st.selectbox("التخصص", [t["name"] for t in grade_tracks], key=f"reg_st_track_{grade}")
        track_id = next(t["id"] for t in grade_tracks if t["name"] == pick)
    with st.form("register_student"):
        name = st.text_input("الاسم الكامل")
        phone = st.text_input("رقم الهاتف (يُستخدم لتسجيل الدخول)")
        email = st.text_input("البريد الإلكتروني (اختياري)")
        pw1 = st.text_input("كلمة المرور", type="password")
        pw2 = st.text_input("تأكيد كلمة المرور", type="password")
        submitted = st.form_submit_button("إنشاء حساب", type="primary")
    if not submitted:
        return
    if not (name.strip() and phone.strip() and pw1):
        st.error("يرجى تعبئة الاسم ورقم الهاتف وكلمة المرور.")
    elif len(pw1) < 6:
        st.error("يجب أن تتكون كلمة المرور من 6 خانات على الأقل.")
    elif pw1 != pw2:
        st.error("كلمتا المرور غير متطابقتين.")
    else:
        try:
            acc.register_student(name, phone, pw1, grade, email, track_id)
            st.success("✅ تم إرسال طلب التسجيل بنجاح. سيتم تفعيل حسابك من الإدارة بعد مراجعة الاشتراك.")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:  # noqa: BLE001
            st.error(f"حدث خطأ أثناء التسجيل: {e}")


def _register_teacher_form():
    subjects = _all_subjects()
    st.caption("اختر المباحث والصفوف التي تُدرّسها فعليًا فقط. سيراجع المدير طلبك قبل التفعيل، "
              "وقد يُطلب منك إثبات (مثل جدول حصصك) قبل الموافقة.")
    tracks = _all_tracks()
    # الصفوف والتخصصات خارج النموذج لأن قائمة التخصصات تتغير حسب الصفوف المختارة
    chosen_grades = st.multiselect("الصفوف التي تُدرّسها", [f"الصف {g}" for g in GRADES], max_selections=4,
                                   key="reg_t_grades")
    grades = [GRADES.index(g.replace("الصف ", "")) + 1 for g in chosen_grades]
    track_opts = {f"الصف {t['grade']} — {t['name']}": t for t in tracks if t["grade"] in grades}
    chosen_tracks = []
    if track_opts:
        chosen_tracks = st.multiselect("التخصصات التي تُدرّسها (للصفوف العاشر والحادي عشر والثاني عشر)",
                                       list(track_opts), key="reg_t_tracks")
    with st.form("register_teacher"):
        name = st.text_input("الاسم الكامل")
        phone = st.text_input("رقم الهاتف (يُستخدم لتسجيل الدخول)")
        email = st.text_input("البريد الإلكتروني (اختياري)")
        c1, c2 = st.columns(2)
        directorate = c1.text_input("المديرية")
        division = c2.text_input("اللواء")
        school_name = st.text_input("اسم المدرسة *")
        chosen_subjects = st.multiselect("المباحث التي تُدرّسها", subjects, max_selections=2)
        pw1 = st.text_input("كلمة المرور", type="password")
        pw2 = st.text_input("تأكيد كلمة المرور", type="password")
        note = st.text_area("ملاحظة للمراجعة (اختياري): الرقم الوظيفي...", height=70)
        submitted = st.form_submit_button("إرسال طلب التسجيل", type="primary")
    if not submitted:
        return
    pairs, missing_track = [], []
    for g in grades:
        g_tracks = [track_opts[k] for k in chosen_tracks if track_opts[k]["grade"] == g]
        if g in catalog.TRACK_GRADES and any(t["grade"] == g for t in tracks) and not g_tracks:
            missing_track.append(g)
        for s in chosen_subjects:
            if g_tracks:
                pairs += [{"subject": s, "grade": g, "track_id": t["id"]} for t in g_tracks]
            else:
                pairs.append({"subject": s, "grade": g})
    if missing_track:
        st.error("اختر تخصصًا واحدًا على الأقل لكل من: " + "، ".join(f"الصف {g}" for g in missing_track))
    elif not (name.strip() and phone.strip() and pw1):
        st.error("يرجى تعبئة الاسم ورقم الهاتف وكلمة المرور.")
    elif not school_name.strip():
        st.error("اسم المدرسة إجباري.")
    elif len(pw1) < 6:
        st.error("يجب أن تتكون كلمة المرور من 6 خانات على الأقل.")
    elif pw1 != pw2:
        st.error("كلمتا المرور غير متطابقتين.")
    elif not pairs:
        st.error("يرجى اختيار مبحث واحد على الأقل وصف واحد على الأقل.")
    else:
        try:
            if note.strip():
                pairs = pairs + [{"note": note.strip()}]
            acc.register_teacher(name, phone, pw1, pairs, directorate, division, school_name, email)
            st.success("✅ تم إرسال طلب التسجيل بنجاح. سيتم تفعيل حسابك بعد مراجعة الإدارة للمباحث المطلوبة والاشتراك.")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:  # noqa: BLE001
            st.error(f"حدث خطأ أثناء التسجيل: {e}")


def _login_form():
    with st.form("login_form"):
        phone = st.text_input("رقم الهاتف")
        pw = st.text_input("كلمة المرور", type="password")
        submitted = st.form_submit_button("تسجيل الدخول", type="primary")
    if not submitted:
        return
    try:
        user = acc.login(phone, pw)
        st.session_state["auth_user_id"] = user["id"]
        st.session_state["auth_session_token"] = user["session_token"]
        st.session_state["auth_checked_at"] = time.time()
        st.rerun()
    except ValueError as e:
        st.error(str(e))
    except Exception as e:  # noqa: BLE001
        st.error(f"تعذّر تسجيل الدخول: {e}")


def _login_and_register_gate():
    st.markdown("### 🔐 تسجيل الدخول")
    tabs = st.tabs(["تسجيل الدخول", "حساب طالب جديد", "حساب معلم جديد"])
    with tabs[0]:
        _login_form()
    with tabs[1]:
        _register_student_form()
    with tabs[2]:
        _register_teacher_form()
    st.stop()


# ---------------------------------------------------------------- البوابة الرئيسية
def require_login():
    """تُستدعى في أول app.py. تعيد بيانات المستخدم الحالي، أو تعرض شاشة الدخول/التسجيل وتوقف التنفيذ."""
    user_id = st.session_state.get("auth_user_id")
    token = st.session_state.get("auth_session_token")
    if not user_id or not token:
        _login_and_register_gate()
        return None  # لن تُنفَّذ (st.stop أعلاه)

    # تحقق من الجلسة الواحدة دوريًا فقط (وليس كل إعادة تشغيل) لتقليل عدد الطلبات
    last_check = st.session_state.get("auth_checked_at", 0)
    if time.time() - last_check > acc.SESSION_RECHECK_SECONDS:
        if not acc.session_still_valid(user_id, token):
            for k in ("auth_user_id", "auth_session_token", "auth_checked_at"):
                st.session_state.pop(k, None)
            st.warning("⚠️ تم تسجيل الدخول إلى حسابك من جهاز آخر، فتم إنهاء هذه الجلسة.")
            _login_and_register_gate()
            return None
        st.session_state["auth_checked_at"] = time.time()

    user = acc.get_user(user_id)
    if not user or user["status"] != "active":
        for k in ("auth_user_id", "auth_session_token", "auth_checked_at"):
            st.session_state.pop(k, None)
        st.error("حسابك لم يعد نشطًا. يرجى التواصل مع الإدارة.")
        _login_and_register_gate()
        return None

    if not acc.subscription_active(user):
        st.error("⛔ انتهى اشتراكك في المنصة. يرجى تجديد الاشتراك مع الإدارة لمتابعة استخدام الخدمات.")
        if st.button("تسجيل الخروج"):
            _do_logout(user)
        st.stop()

    with st.sidebar:
        st.markdown(f"**{user['name']}** — {acc.ROLE_AR.get(user['role'], user['role'])}")
        if user.get("subscription_end"):
            st.caption(f"الاشتراك ساري حتى: {user['subscription_end']}")
        if user["role"] != "admin":
            used = acc.usage_today(user["id"])
            limit = acc.get_limit(acc.limit_role(user))
            st.caption(f"طلبات الذكاء الاصطناعي اليوم: {used} / {limit}")
        if acc.is_trial(user):
            st.info("🧪 حساب تجريبي: بعض الخدمات محدودة أو مقفلة.")
            for f in acc.TRIAL_COUNTED:
                st.caption(f"{acc.TRIAL_FEATURES[f]}: المتبقي {acc.trial_remaining(user, f)}")
        if st.button("🚪 تسجيل الخروج"):
            _do_logout(user)

    return user


def _do_logout(user):
    acc.logout(user["id"])
    for k in ("auth_user_id", "auth_session_token", "auth_checked_at"):
        st.session_state.pop(k, None)
    st.rerun()


def require_quota_or_stop(user):
    """يُستدعى مباشرة قبل أي استدعاء فعلي لجيمناي. يوقف التنفيذ برسالة واضحة إن استُنفدت الحصة."""
    ok, msg = acc.use_quota(user)
    if not ok:
        st.error(f"🚫 {msg}")
        st.stop()


# ---------------------------------------------------------------- لوحة المدير العام
def render_admin_accounts_panel(current_user):
    st.subheader("👑 إدارة الحسابات والصلاحيات")
    tracks = catalog.list_tracks(include_inactive=True)
    tname = lambda tid: catalog.track_name(tracks, tid)   # noqa: E731
    tabs = st.tabs(["⏳ طلبات قيد المراجعة", "👥 كل الحسابات", "🎯 صلاحيات المشرفين", "⚙️ الحدود اليومية",
                   "🗓️ الأعياد والعطل", "🎓 التخصصات", "🧪 الحساب التجريبي"])

    # ---------- طلبات قيد المراجعة ----------
    with tabs[0]:
        pending = acc.list_users(status="pending")
        if not pending:
            st.info("لا توجد طلبات تسجيل قيد المراجعة حاليًا.")
        for u in pending:
            with st.expander(f"{u['name']} — {acc.ROLE_AR.get(u['role'])} — {u['phone']}"):
                st.write(f"📧 {u.get('email') or '—'}")
                sub_end = st.date_input("تاريخ انتهاء الاشتراك", key=f"sub_{u['id']}")
                if u["role"] == "student":
                    st.write(f"🎓 الصف: الصف {u.get('grade')}")
                    g_tracks = catalog.tracks_of_grade(tracks, u.get("grade"))
                    st_track = u.get("track_id")
                    if g_tracks:
                        names = [t["name"] for t in g_tracks]
                        cur = tname(st_track) if tname(st_track) in names else names[0]
                        pick = st.selectbox("التخصص (يمكنك تعديله قبل القبول)", names, index=names.index(cur),
                                            key=f"sttrack_{u['id']}")
                        st_track = next(t["id"] for t in g_tracks if t["name"] == pick)
                    c1, c2 = st.columns(2)
                    if c1.button("✅ قبول وتفعيل", key=f"approve_{u['id']}", type="primary"):
                        acc.approve_student(u["id"], current_user["id"], sub_end.isoformat(), st_track)
                        st.rerun()
                    if c2.button("❌ رفض", key=f"reject_{u['id']}"):
                        acc.reject_user(u["id"])
                        st.rerun()
                else:
                    req = u.get("requested_subjects") or []
                    notes = [r for r in req if "note" in r]
                    pairs = [r for r in req if "subject" in r]
                    if notes:
                        st.caption(f"ملاحظة المعلم: {notes[0]['note']}")
                    st.write("**المباحث/الصفوف المطلوبة (بإمكانك إلغاء تحديد ما لا يستحقه المعلم قبل الموافقة):**")
                    kept = []
                    for i, p in enumerate(pairs):
                        tr = f" — {tname(p['track_id'])}" if p.get("track_id") else ""
                        if st.checkbox(f"{p['subject']} — الصف {p['grade']}{tr}", value=True, key=f"keep_{u['id']}_{i}"):
                            kept.append(p)
                    as_trial = st.checkbox("🧪 اعتماده كحساب تجريبي (ميزات محدودة — تُضبط من تبويب الحساب التجريبي)",
                                           key=f"trial_{u['id']}")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ اعتماد المباحث المحددة وتفعيل الحساب", key=f"approve_{u['id']}", type="primary"):
                        if not kept:
                            st.error("يجب اعتماد مبحث واحد على الأقل، أو اختر رفض الطلب.")
                        else:
                            acc.approve_teacher(u["id"], current_user["id"], kept, sub_end.isoformat(), trial=as_trial)
                            st.rerun()
                    if c2.button("❌ رفض الطلب بالكامل", key=f"reject_{u['id']}"):
                        acc.reject_user(u["id"])
                        st.rerun()

    # ---------- كل الحسابات ----------
    with tabs[1]:
        role_filter = st.selectbox("تصفية حسب الدور", ["الكل", "student", "teacher", "supervisor", "admin"],
                                   format_func=lambda r: "الكل" if r == "الكل" else acc.ROLE_AR[r])
        users = acc.list_users(role=None if role_filter == "الكل" else role_filter)
        users = [u for u in users if u["status"] != "pending"]
        for u in users:
            with st.expander(f"{'🟢' if u['status']=='active' else '🔴'} {u['name']} — "
                             f"{acc.ROLE_AR.get(u['role'])} — {u['phone']} ({u['status']})"):
                st.write(f"📧 {u.get('email') or '—'}  |  📅 الاشتراك حتى: {u.get('subscription_end') or '—'}")
                if u["role"] in ("teacher", "supervisor"):
                    scope = acc.teacher_scope(u["id"])
                    st.write("المباحث/الصفوف المعتمدة: " +
                            (", ".join(f"{s['subject']} (ص{s['grade']}" +
                                       (f" {tname(s['track_id'])}" if s.get("track_id") else "") + ")"
                                       for s in scope) or "لا يوجد"))
                    if u["role"] == "teacher":
                        trial_now = st.checkbox("🧪 حساب تجريبي", value=bool(u.get("is_trial")), key=f"trialflag_{u['id']}")
                        if trial_now != bool(u.get("is_trial")):
                            acc.set_trial(u["id"], trial_now)
                            st.rerun()
                elif u["role"] == "student" and u.get("track_id"):
                    st.write(f"🎓 الصف {u.get('grade')} — {tname(u['track_id'])}")

                new_end = st.date_input("تعديل تاريخ انتهاء الاشتراك", key=f"end_{u['id']}")
                if st.button("💾 حفظ تاريخ الاشتراك", key=f"save_end_{u['id']}"):
                    acc.set_subscription(u["id"], new_end.isoformat())
                    st.rerun()

                c1, c2, c3 = st.columns(3)
                if u["status"] == "active":
                    if c1.button("⏸️ إيقاف الحساب", key=f"susp_{u['id']}"):
                        acc.suspend_user(u["id"], True)
                        st.rerun()
                else:
                    if c1.button("▶️ إعادة تفعيل", key=f"unsusp_{u['id']}"):
                        acc.suspend_user(u["id"], False)
                        st.rerun()
                if u["role"] == "teacher" and c2.button("⬆️ تحويل إلى مشرف", key=f"tosup_{u['id']}"):
                    acc.set_role(u["id"], "supervisor")
                    st.rerun()
                elif u["role"] == "supervisor" and c2.button("⬇️ تحويل إلى معلم", key=f"toteach_{u['id']}"):
                    acc.set_role(u["id"], "teacher")
                    st.rerun()
                if u["id"] != current_user["id"] and c3.button("🗑️ حذف الحساب نهائيًا", key=f"del_{u['id']}"):
                    acc.delete_user(u["id"])
                    st.rerun()

    # ---------- صلاحيات المشرفين ----------
    with tabs[2]:
        supervisors = acc.list_users(role="supervisor")
        supervisors = [u for u in supervisors if u["status"] == "active"]
        if not supervisors:
            st.info("لا يوجد مشرفون حاليًا. حوّل معلمًا إلى مشرف من تبويب «كل الحسابات» أولًا.")
        for u in supervisors:
            st.markdown(f"**{u['name']}**")
            current = set(acc.supervisor_subjects(u["id"]))
            chosen = st.multiselect(f"مباحث إشراف {u['name']}", _all_subjects(), default=list(current),
                                    key=f"supsub_{u['id']}")
            if st.button("💾 حفظ", key=f"savesup_{u['id']}"):
                chosen_set = set(chosen)
                for s in chosen_set - current:
                    acc.add_supervisor_subject(u["id"], s)
                for s in current - chosen_set:
                    acc.remove_supervisor_subject(u["id"], s)
                st.success("تم الحفظ.")
            st.divider()

    # ---------- الحدود اليومية ----------
    with tabs[3]:
        for role in ("student", "teacher", "trial", "supervisor"):
            cur = acc.get_limit(role)
            new_val = st.number_input(f"الحد اليومي لـ {acc.ROLE_AR[role]}", min_value=1, max_value=200,
                                      value=cur, key=f"limit_{role}")
            if new_val != cur and st.button(f"💾 حفظ حد {acc.ROLE_AR[role]}", key=f"savelimit_{role}"):
                acc.set_limit(role, new_val)
                st.rerun()

    # ---------- التقويم الدراسي والعطل ----------
    with tabs[4]:
        st.markdown("#### 📅 التقويم الدراسي")
        st.caption("يُستخدم لتحديد تلقائيًا أي الأشهر/الأيام ضمن الفصل الأول أو الثاني في دفتر الحضور والغياب، "
                  "وتظليل أي يوم خارج الفصلين (كالعطلة بينهما) تلقائيًا.")
        cal = acc.get_academic_calendar()
        import datetime as _dt
        d = lambda s, default: _dt.date.fromisoformat(s) if s else default
        year1 = st.number_input("السنة الدراسية (السنة الأولى، مثال 2026 لعام 2026/2027)",
                                min_value=2020, max_value=2100, value=cal["year1"] if cal else 2026)
        c1, c2 = st.columns(2)
        sem1_start = c1.date_input("بداية الفصل الأول", value=d(cal and cal["sem1_start"], _dt.date(2026, 8, 1)))
        sem1_end = c2.date_input("نهاية الفصل الأول", value=d(cal and cal["sem1_end"], _dt.date(2027, 1, 15)))
        sem2_start = c1.date_input("بداية الفصل الثاني", value=d(cal and cal["sem2_start"], _dt.date(2027, 2, 1)))
        sem2_end = c2.date_input("نهاية الفصل الثاني", value=d(cal and cal["sem2_end"], _dt.date(2027, 6, 30)))
        auto_hijri = hijri_school_year(sem1_start, sem2_end)
        hijri_in = st.text_input("العام الدراسي الهجري", value=(cal or {}).get("hijri_label") or "",
                                 placeholder=auto_hijri,
                                 help="اتركه فارغًا ليحسبه النظام تلقائيًا من تاريخي بداية الفصل الأول ونهاية الفصل الثاني، "
                                      "أو اكتبه بنفسك (مثال: 1448/1449). يُستخدم في أغلفة دفتر العلامات.")
        st.caption(f"العام الهجري الذي سيُستخدم: **{hijri_in.strip() or auto_hijri}هـ** — "
                   f"الميلادي: **{year1}/{year1 + 1}م**")
        if st.button("💾 حفظ التقويم الدراسي", type="primary"):
            if sem1_start >= sem1_end or sem2_start >= sem2_end or sem1_end >= sem2_start:
                st.error("تأكد من أن تواريخ كل فصل متسلسلة، وأن الفصل الأول ينتهي قبل بداية الفصل الثاني.")
            else:
                acc.set_academic_calendar(year1, sem1_start.isoformat(), sem1_end.isoformat(),
                                         sem2_start.isoformat(), sem2_end.isoformat(), hijri_in)
                st.success("تم حفظ التقويم الدراسي.")
                st.rerun()
        if not cal:
            st.warning("⚠️ لم يُحدَّد التقويم الدراسي بعد — دفتر الحضور والغياب لن يعمل حتى يُحفظ هنا.")

        st.markdown("---")
        st.markdown("#### 🗓️ الأعياد والعطل الرسمية")
        with st.form("add_holiday"):
            hc1, hc2 = st.columns(2)
            h_date = hc1.date_input("تاريخ العطلة")
            h_name = hc2.text_input("اسم العطلة (اختياري)", placeholder="مثال: عيد الفطر")
            if st.form_submit_button("➕ إضافة"):
                acc.add_holiday(h_date.isoformat(), h_name)
                st.rerun()
        for h in acc.list_holidays():
            c1, c2 = st.columns([5, 1])
            c1.write(f"📅 {h['holiday_date']} — {h.get('name') or 'بلا اسم'}")
            if c2.button("🗑️", key=f"delhol_{h['id']}"):
                acc.remove_holiday(h["id"])
                st.rerun()

    # ---------- التخصصات ----------
    with tabs[5]:
        st.markdown("#### 🎓 تخصصات الصفوف العاشر والحادي عشر والثاني عشر")
        st.caption("أضف التخصصات المتاحة لكل صف (هندسي، زراعي، علمي، أدبي...). «الشعبة» (أ، ب...) لا تُضاف هنا؛ "
                  "يكتبها المعلم في نماذجه. بعد إضافة التخصص اربطه بالكتب من صفحة «إدارة الكتب»: "
                  "كتاب بلا تخصصات = مشترك لكل تخصصات الصف (مثل المهارات الرقمية).")
        with st.form("add_track", clear_on_submit=True):
            tc1, tc2 = st.columns(2)
            t_grade = tc1.selectbox("الصف", list(catalog.TRACK_GRADES), format_func=lambda g: f"الصف {g}")
            t_name = tc2.text_input("اسم التخصص", placeholder="مثال: هندسي")
            if st.form_submit_button("➕ إضافة التخصص", type="primary"):
                try:
                    catalog.add_track(t_grade, t_name)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        for g in catalog.TRACK_GRADES:
            g_tracks = [t for t in tracks if t["grade"] == g]
            st.markdown(f"**الصف {g}**" + ("" if g_tracks else " — لا توجد تخصصات بعد (يعمل الصف كالمعتاد بلا تخصص)"))
            for t in g_tracks:
                c1, c2, c3 = st.columns([4, 2, 2])
                c1.write(("🟢 " if t["active"] else "⚪ ") + t["name"] + ("" if t["active"] else " (موقوف)"))
                if c2.button("⏸️ إيقاف" if t["active"] else "▶️ تفعيل", key=f"trk_act_{t['id']}"):
                    catalog.set_track_active(t["id"], not t["active"])
                    st.rerun()
                if c3.button("🗑️ حذف", key=f"trk_del_{t['id']}"):
                    try:
                        catalog.delete_track(t["id"])
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    # ---------- الحساب التجريبي ----------
    with tabs[6]:
        st.markdown("#### 🧪 ما يحصل عليه المعلم التجريبي")
        st.caption("خطة الدرس والخطة الفصلية: الرقم = عدد **الدروس** المسموحة طوال عمر الحساب (1 = درس واحد فقط، "
                  "والخطة الفصلية تُنتَج لهذا الدرس وليس للمنهاج كاملًا). بقية الخدمات: 0 = مقفلة، وأي رقم أكبر من 0 = مفتوحة. "
                  "الحد اليومي لطلبات الذكاء الاصطناعي للتجريبي يُضبط من تبويب «الحدود اليومية».")
        limits = acc.trial_limits()
        for f, label in acc.TRIAL_FEATURES.items():
            new_v = st.number_input(label, min_value=0, max_value=50, value=int(limits[f]), key=f"trial_lim_{f}")
            if new_v != limits[f] and st.button(f"💾 حفظ «{label}»", key=f"trial_save_{f}"):
                acc.set_trial_limit(f, new_v)
                st.rerun()
