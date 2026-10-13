"""
profile_ctx.py
«ما يعرفه النظام أصلًا» عن المستخدم الحالي وسياقه (الصف، التخصص، المبحث، الفصل، العام الدراسي ميلاديًا وهجريًا،
اسم المعلم، المدرسة، المديرية، اللواء). النماذج تستخدم known_input() فلا تسأل المعلم إلا عمّا لا يعرفه النظام.
"""
import streamlit as st

import accounts as acc


@st.cache_data(ttl=300, show_spinner=False)
def _calendar():
    try:
        return acc.get_academic_calendar()
    except Exception:  # noqa: BLE001
        return None


def build(user, grade, track, subject, sem):
    """track: اسم التخصص أو ''. يعيد قاموسًا بكل المعلومات المعروفة (قيمة فارغة = غير معروفة)."""
    cal = _calendar()
    years = acc.year_labels(cal) or {}
    is_staff = user["role"] in ("teacher", "supervisor", "admin")
    return {
        "teacher": user["name"] if is_staff else "",
        "school": user.get("school_name") or "",
        "directorate": user.get("directorate") or "",
        "division": user.get("division") or "",
        "grade": grade, "track": track, "subject": subject, "sem": sem,
        "sem_name": "الأول" if sem == 1 else "الثاني",
        "sem_name_en": "First" if sem == 1 else "Second",
        "class_label": acc.class_label(grade, track),
        "greg_year": years.get("greg", ""), "hijri_year": years.get("hijri", ""),
    }


def known_input(label, known, key, placeholder="", **kw):
    """إن كانت القيمة معروفة تُعاد مباشرة دون سؤال، وإلا يظهر حقل إدخال للمعلم."""
    known = (known or "").strip() if isinstance(known, str) else known
    if known:
        return known
    return st.text_input(label, key=key, placeholder=placeholder, **kw)


def known_summary(pairs):
    """سطر مختصر بما سيُعبَّأ تلقائيًا، كي يرى المعلم ما يعرفه النظام دون أن يُسأل عنه."""
    shown = [f"{k}: **{v}**" for k, v in pairs if v]
    if shown:
        st.caption("✅ تُعبَّأ تلقائيًا من حسابك: " + " — ".join(shown))
