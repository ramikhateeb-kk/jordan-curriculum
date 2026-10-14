import hmac

import pandas as pd
import streamlit as st

import catalog
import ingest
from config import GRADES

st.set_page_config(page_title="إدارة الكتب", page_icon="🛠️", layout="wide")
st.markdown("""
<style>
html, body, .stApp, [data-testid="stMarkdownContainer"] { direction: rtl; text-align: right; }
[data-testid="stSelectbox"] div, textarea, input { direction: rtl; text-align: right; }
</style>
""", unsafe_allow_html=True)
st.title("🛠️ إدارة الكتب")

# ---------------------------------------------------------------- كلمة المرور
admin_pw = catalog.secret("ADMIN_PASSWORD")
if not admin_pw:
    st.error("لم تُضبط كلمة مرور المشرف. أضف ADMIN_PASSWORD في Secrets ثم أعد تحميل الصفحة.")
    st.stop()
if not st.session_state.get("admin_ok"):
    entered = st.text_input("كلمة مرور المشرف", type="password")
    if st.button("دخول"):
        if hmac.compare_digest(entered.encode(), str(admin_pw).encode()):
            st.session_state["admin_ok"] = True
            st.rerun()
        else:
            st.error("كلمة المرور غير صحيحة.")
    st.stop()

if catalog.backend_name() == "local":
    st.warning("التخزين الحالي مؤقت (ملف على الخادم) وقد يضيع عند إعادة تشغيل الموقع. "
               "اربط Supabase (الخطوات في الشرح) لحفظ دائم، أو نزّل نسخة احتياطية من الأسفل.")
else:
    st.success("التخزين: Supabase (دائم)")

GRADE_LABELS = [f"الصف {g}" for g in GRADES]
COLS = ["النوع", "العنوان", "الصفحة"]

try:
    books = catalog.list_books()
    tracks = catalog.list_tracks(include_inactive=True)
except Exception as e:  # noqa: BLE001
    st.error(f"تعذّر قراءة الجدول: {e}")
    st.stop()

# ---------------------------------------------------------------- الكتب المسجلة
st.subheader("الكتب المسجلة")
if books:
    st.dataframe(
        [{"الصف": GRADE_LABELS[b["grade"] - 1], "الفصل": b["semester"], "المادة": b["subject"],
          "التخصصات": ("مشترك" if catalog.is_common(b) else "، ".join(catalog.track_name(tracks, t) for t in b["track_ids"]))
                       if b["grade"] in catalog.TRACK_GRADES else "—",
          "اللغة": "English" if b["lang"] == "en" else "العربية",
          "مرافق": "نعم" if b.get("parent_slug") else "",
          "الوحدات": len(b["units"]), "الدروس": sum(len(u["lessons"]) for u in b["units"]),
          "الرابط": "✅" if b["pdf_url"].startswith("http") else "❌"} for b in books],
        hide_index=True, use_container_width=True)
else:
    st.info("لا توجد كتب مسجلة بعد.")

# ---------------------------------------------------------------- إضافة / تعديل
st.subheader("إضافة كتاب أو تعديله")
def _book_label(b):
    tr = "" if catalog.is_common(b) or b["grade"] not in catalog.TRACK_GRADES else \
        " [" + "، ".join(catalog.track_name(tracks, t) for t in b["track_ids"]) + "]"
    return f"{GRADE_LABELS[b['grade'] - 1]} - الفصل {b['semester']} - {b['subject']}{tr}"


labels = ["➕ كتاب جديد"] + [_book_label(b) for b in books]
choice = st.selectbox("اختر", labels)
existing = None if choice == labels[0] else books[labels.index(choice) - 1]
editing = existing is not None
ekey = existing["slug"] + str(existing["grade"]) + str(existing["semester"]) if editing else "new"

c1, c2, c3 = st.columns(3)
grade_label = c1.selectbox("الصف", GRADE_LABELS, index=(existing["grade"] - 1) if editing else 11,
                           disabled=editing, key=f"g_{ekey}")
sem = c2.selectbox("الفصل", [1, 2], index=(existing["semester"] - 1) if editing else 0,
                   format_func=lambda s: "الأول" if s == 1 else "الثاني", disabled=editing, key=f"s_{ekey}")
subject = c3.text_input("اسم المادة", value=existing["subject"] if editing else "",
                        disabled=editing, key=f"n_{ekey}")
grade = GRADE_LABELS.index(grade_label) + 1

# ---- التخصصات (للصفوف 10-12 فقط) واللغة
sel_track_ids = []
if grade in catalog.TRACK_GRADES:
    g_tracks = [t for t in tracks if t["grade"] == grade]
    if g_tracks:
        opts = {t["name"] + ("" if t["active"] else " (موقوف)"): t["id"] for t in g_tracks}
        default = [k for k, v in opts.items() if editing and v in existing["track_ids"]]
        picked = st.multiselect(
            "التخصصات التي يُدرَّس فيها هذا الكتاب", list(opts), default=default, key=f"tr_{ekey}_{grade}",
            help="اتركها فارغة إن كان الكتاب مشتركًا لكل تخصصات الصف (مثل المهارات الرقمية). "
                 "اختر تخصصًا أو أكثر إن كان الكتاب خاصًا بها فقط.")
        sel_track_ids = [opts[k] for k in picked]
        st.caption("✅ كتاب مشترك لكل تخصصات الصف." if not sel_track_ids else
                   "🎯 كتاب خاص بالتخصصات المختارة فقط.")
    else:
        st.caption("لا توجد تخصصات معرّفة لهذا الصف بعد (أضفها من لوحة المدير ← «التخصصات»). يُحفظ الكتاب كمشترك.")
lang_default = (existing["lang"] if editing else catalog.guess_lang(subject))
lang_label = st.radio("لغة الكتاب", ["العربية", "English"], index=1 if lang_default == "en" else 0,
                      horizontal=True, key=f"lang_{ekey}_{lang_default}",
                      help="كتب English تُنتَج لها خطة الدرس والخطة الفصلية وتحليل المحتوى بالإنجليزية واتجاه الصفحة من اليسار إلى اليمين.")

# ---- كتاب مرافق (مثل كتاب الأنشطة): يرتبط بكتاب رئيسي ويُخفى من قوائم المواد
_parents = {"— كتاب رئيسي (ليس مرافقًا) —": None}
for _b in books:
    if not _b.get("parent_slug") and not (editing and _b["slug"] == existing["slug"]):
        _parents[_book_label(_b)] = _b["slug"]
_cur_parent = existing.get("parent_slug") if editing else None
_pl = list(_parents)
_idx = next((i for i, k in enumerate(_pl) if _parents[k] == _cur_parent), 0)
parent_label = st.selectbox("هل هذا الكتاب مرافق لكتاب آخر؟", _pl, index=_idx, key=f"par_{ekey}",
                            help="اختر الكتاب الرئيسي إن كان هذا كتاب أنشطة/تمارين له. يُربط درس كل كتاب بنظيره "
                                 "تلقائيًا بالوحدة ورقم الدرس (Unit 02 / Lesson 3A مع Lesson 3B).")
parent_slug = _parents[parent_label]

pdf_url = st.text_input("رابط الكتاب المباشر (PDF)", value=existing["pdf_url"] if editing else "", key=f"u_{ekey}")
offset = st.number_input(
    "فرق الترقيم = (رقم الصفحة في ملف PDF) − (الرقم المطبوع في الكتاب)",
    value=existing["page_offset"] if editing else 0, step=1, min_value=-5, max_value=60, key=f"o_{ekey}")
st.caption("مثال: إن كانت الصفحة المطبوع عليها الرقم 8 هي الصفحة 11 في قارئ PDF فالفرق 3.")

st.markdown("**جدول الوحدات والدروس** — أدخل الصفوف بترتيب قائمة المحتويات: سطر لكل وحدة ثم سطر لكل درس "
            "(و«مراجعة الوحدة» تُدخل كدرس)، وأرقام الصفحات هي المطبوعة في الكتاب.")
# ---- رفع ملف الوحدات والدروس (CSV / Excel / JSON) بدل الإدخال اليدوي
vkey = f"uver_{ekey}"
rkey = f"urows_{ekey}"
st.session_state.setdefault(vkey, 0)
with st.expander("📤 رفع ملف الوحدات والدروس (CSV أو Excel أو JSON)"):
    st.caption("الأعمدة: النوع (وحدة/درس) — العنوان — الصفحة المطبوعة. يملأ الملف الجدول أدناه ويمكنك تعديله قبل الحفظ.")
    st.download_button("⬇️ تنزيل قالب CSV", data=catalog.units_template_csv(), file_name="units_template.csv",
                       mime="text/csv", key=f"tpl_{ekey}")
    up_units = st.file_uploader("اختر الملف", type=["csv", "tsv", "txt", "xlsx", "json"], key=f"upu_{ekey}_{st.session_state[vkey]}")
    if up_units is not None:
        up_rows, up_errs = catalog.parse_units_file(up_units.getvalue(), up_units.name)
        _, cfg_errs = catalog.rows_to_cfg(up_rows) if up_rows else ([], [])
        for e in up_errs + cfg_errs:
            st.error(e)
        if up_rows and not (up_errs or cfg_errs):
            st.session_state[rkey] = up_rows
            st.session_state[vkey] += 1
            st.rerun()
        elif up_rows:
            st.warning("لم يُستبدل الجدول بسبب الأخطاء أعلاه. صحّح الملف وأعد رفعه.")

init_rows = st.session_state.get(rkey) or (
    catalog.cfg_to_rows(existing["units"]) if editing and existing["units"] else
    [{"النوع": "وحدة", "العنوان": "", "الصفحة": None}])
df0 = pd.DataFrame(init_rows, columns=COLS).astype({"الصفحة": "float64"})
edited = st.data_editor(
    df0, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"t_{ekey}_{st.session_state[vkey]}",
    column_config={
        "النوع": st.column_config.SelectboxColumn("النوع", options=["وحدة", "درس"], required=True, width="small"),
        "العنوان": st.column_config.TextColumn("العنوان", width="large"),
        "الصفحة": st.column_config.NumberColumn("الصفحة المطبوعة", min_value=1, step=1, format="%d", width="small"),
    })
cfg, errors = catalog.rows_to_cfg(edited.to_dict("records"))

b1, b2, b3 = st.columns(3)
book = None
if subject.strip():
    slug = existing["slug"] if editing else catalog.make_slug(grade, sem, subject, sel_track_ids)
    book = {"grade": grade, "semester": sem, "subject": subject.strip(), "slug": slug,
            "pdf_url": pdf_url.strip(), "page_offset": int(offset), "units": cfg,
            "track_ids": sel_track_ids, "lang": "en" if lang_label == "English" else "ar",
            "parent_slug": parent_slug}

if b1.button("💾 حفظ", type="primary"):
    if not subject.strip():
        st.error("اكتب اسم المادة.")
    elif not pdf_url.strip().startswith("http"):
        st.error("أدخل رابط الكتاب المباشر (يبدأ بـ http).")
    elif errors:
        for e in errors:
            st.error(e)
    else:
        try:
            catalog.save_book(book)
            st.cache_data.clear()
            st.success("تم الحفظ. ستظهر المادة في الموقع خلال لحظات.")
        except Exception as e:  # noqa: BLE001
            st.error(f"تعذّر الحفظ: {e}")

if b2.button("🔍 معاينة وتحقق من الصفحات"):
    if book is None or not pdf_url.strip().startswith("http"):
        st.error("أدخل اسم المادة ورابط الكتاب أولًا.")
    elif errors:
        for e in errors:
            st.error(e)
    else:
        try:
            with st.spinner("جارٍ تحميل الكتاب وفحص الصفحات..."):
                rows, total = ingest.check_book(book, cfg, int(offset))
            st.caption(f"عدد صفحات الملف: {total}")
            st.dataframe(rows, hide_index=True, use_container_width=True)
            st.caption("✅ يعني أن كلمات العنوان ظهرت في الصفحة المحسوبة. إن ظهر ⚠️ في معظم الصفوف فراجع فرق الترقيم.")
        except RuntimeError as e:
            st.error(str(e))

if editing:
    with b3:
        confirm = st.checkbox("أؤكد حذف هذا الكتاب")
        if st.button("🗑️ حذف") and confirm:
            try:
                catalog.delete_book(existing["grade"], existing["semester"], existing["slug"])
                st.cache_data.clear()
                st.success("تم الحذف.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"تعذّر الحذف: {e}")

# ---------------------------------------------------------------- نسخة احتياطية
with st.expander("نسخة احتياطية واستيراد"):
    st.download_button("⬇️ تنزيل كل الكتب (JSON)", data=catalog.export_json(),
                       file_name="catalog.json", mime="application/json")
    up = st.file_uploader("استيراد من ملف JSON", type="json")
    if up is not None and st.button("استيراد"):
        try:
            n = catalog.import_json(up.getvalue().decode("utf-8"))
            st.cache_data.clear()
            st.success(f"تم استيراد {n} كتاب.")
        except Exception as e:  # noqa: BLE001
            st.error(f"ملف غير صالح: {e}")
