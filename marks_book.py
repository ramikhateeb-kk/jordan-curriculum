"""
marks_book.py
دفتر العلامات: يختار المعلم عدة تركيبات (صف/مبحث/شعبة)، يُدخل أسماء طلاب كل تركيبة، ويولّد النظام
ملف "دفتر العلامات" الرسمي من القالب المخزَّن في المستودع، بتعبئة اسم كل طالب في الجدول المناسب
(حتى 25 طالبًا لكل جدول)، تاركًا خلايا العلامات فارغة ليعبئها المعلم لاحقًا بنفسه.

بنية القالب (مستخرجة من فحص مباشر لملف القالب الفعلي "دفتر_العلامات.xlsx"، وليست تقديرًا):
- ثلاث أوراق بنفس الترتيب: "دفتر العلامات" (sheet1.xml)، "الغلاف الداخلي" (sheet2.xml)،
  "الغلاف الازرق" (sheet3.xml).
- ورقة "دفتر العلامات" تحتوي 50 جدول علامات متطابقة الشكل (TABLE_STARTS أدناه، أرقام صفوف حقيقية
  وليست محسوبة بالتقريب). كل جدول: عمود B = اسم الطالب لـ 25 صفًا تبدأ بعد صف الترويسة بثلاثة صفوف،
  وتذييل يحمل "الصف :"، "الشعبة ( )"، "المادة الدراسية" قبل ترويسة الجدول التالي. أعمدة العلامات
  (D..I وL..T) فارغة أصلًا في القالب (تمثّل تقويمَي الفصلين)، ولا توجد صيغ (formulas) في أعمدة
  الرقم المتسلسل أو الاسم، فلا خطر من الكتابة فوقها.
- ورقتا الغلاف تحتويان صناديق نصوص مسمّاة (مديرية/بلدة/مدرسة/صفوف/مادة/معلم/تاريخ) بنفس الأسلوب الذي
  تبيّن أنه هشّ جدًا (عطّل الملف الناتج مرتين في وحدة الحضور والغياب عند تحرير XML الرسم مباشرة).
  لذلك **لا تُعبَّأ ورقتا الغلاف تلقائيًا في هذه النسخة** — انظر القيود في نهاية الملف.

أسلوب الحفظ: نفس الأسلوب الآمن المُثبَت في attendance.py بعد فشل تحرير الرسومات مرتين: الملف النهائي
يُبنى من نسخة القالب الأصلية بالكامل كما هي (تضمن سلامته)، ونستبدل فيها فقط الأجزاء التي تغيّرت فعلًا
(خلايا ورقة "دفتر العلامات" وتنسيقاتها)، تاركين كل شيء آخر (الأغلفة، الرسومات، الصور، العلاقات) دون أي
لمس — هذا يتجنّب تمامًا مشكلة فقدان openpyxl لعناصر الرسم التي لا يفهمها عند الحفظ الكامل.
"""
import io
import copy
import xml.etree.ElementTree as ET

import openpyxl
import pandas as pd
import streamlit as st

import accounts as acc
import catalog

TEMPLATE_PATH = "templates/دفتر_العلامات.xlsx"
SHEET_NAME = "دفتر العلامات"

# بدايات الجداول على ورقة "دفتر العلامات" (صفوف حقيقية من فحص القالب). الجدول الأول في الملف (يبدأ
# بالصف 3، وبياناته عند B6) مُستبعَد عمدًا من المجموعة بناءً على طلب صريح: أول صف يُستخدم فعليًا هو
# B39 (الجدول الذي يبدأ بالصف 36) فما بعده.
TABLE_STARTS = [36, 68, 100, 132, 164, 196, 228, 260, 292, 324, 356, 388, 420, 452, 484, 516, 548,
               580, 612, 644, 676, 708, 740, 772, 804, 836, 868, 900, 932, 964, 996, 1028, 1060, 1092,
               1124, 1156, 1188, 1220, 1252, 1284, 1316, 1348, 1380, 1412, 1444, 1476, 1508, 1540, 1572]
SHEET_LAST_ROW = 1601   # آخر صف فعلي في الورقة (لحساب تذييل آخر جدول)
STUDENTS_PER_TABLE = 25
NAME_COL = "B"
# بيانات الصف/الشعبة/المادة موجودة في الصفين السابقين لبداية كل جدول: الأعمدة D وI وL.
# أول مجموعة في الصف 34 والجدول الأول المستخدم يبدأ في الصف 36.
FOOTER_GRADE_COL, FOOTER_SECTION_COL, FOOTER_SUBJECT_COL = "D", "I", "L"

PARTS_FROM_SAVED = ("xl/worksheets/sheet1.xml", "xl/styles.xml", "xl/sharedStrings.xml")
COVER_DRAWINGS = ("xl/drawings/drawing2.xml", "xl/drawings/drawing3.xml")
COVER_SHAPES = {
    "modeeriah": "directorate", "baldah": "town", "school": "school",
    "classes": "classes", "mawad": "subjects", "teacher": "teacher",
    "hejri": "hijri_date", "melady": "gregorian_date",
}
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
ET.register_namespace("xdr", NS_XDR)
ET.register_namespace("a", NS_A)
ET.register_namespace("a16", "http://schemas.microsoft.com/office/drawing/2014/main")
ET.register_namespace("a14", "http://schemas.microsoft.com/office/drawing/2010/main")
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")


def _patch_pitch(data: bytes) -> bytes:
    """بعض صناديق النصوص في ورقتي الغلاف تحمل pitchFamily="66" (قيمة غير قياسية يرفضها openpyxl
    عند القراءة، سقفه الأقصى 52). نُصلحها فقط من أجل قراءة openpyxl للملف؛ الإخراج النهائي يُبنى من
    البيانات الأصلية غير المعدَّلة (Excel نفسه لا يتأثر بهذه القيمة إطلاقًا)."""
    import re
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data), "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if re.match(r"xl/drawings/drawing\d+\.xml$", item.filename):
                content = content.replace(b'pitchFamily="66"', b'pitchFamily="2"')
            zout.writestr(item, content)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------- مواقع الجداول
def _table_footer_row(table_idx):
    """بيانات الصف/الشعبة/المبحث لأول جدول في الصف 34 ثم 66، 98، ..."""
    return TABLE_STARTS[table_idx] - 2

def _table_data_rows(table_idx):
    start = TABLE_STARTS[table_idx]
    return list(range(start + 3, start + 3 + STUDENTS_PER_TABLE))


# ---------------------------------------------------------------- تخصيص الجداول للتركيبات
def allocate_tables(combos):
    """combos: [{"grade","subject","class_section","students":[...]}, ...] بترتيب الإضافة.
    يعيد [{"combo_index","table_idx","students":[...]}, ...] — كل عنصر يمثل جدولًا واحدًا سيُملأ
    (قد تحتاج تركيبة واحدة أكثر من جدول إن تجاوز عدد طلابها 25). يرفع ValueError إن نفدت الجداول."""
    plan = []
    table_idx = 0
    for ci, combo in enumerate(combos):
        students = combo["students"]
        for i in range(0, len(students), STUDENTS_PER_TABLE):
            if table_idx >= len(TABLE_STARTS):
                raise ValueError(f"القالب يحتوي {len(TABLE_STARTS)} جدولًا فقط، ولا يكفي لكل التركيبات "
                                 f"المضافة (نفدت الجداول عند «{combo['subject']} - {combo['class_section']}»). "
                                 "احذف إحدى التركيبات أو قلّل عدد الطلاب.")
            plan.append({"combo_index": ci, "table_idx": table_idx, "students": students[i:i + STUDENTS_PER_TABLE]})
            table_idx += 1
    return plan


# ---------------------------------------------------------------- توليد الملف
def generate_marks_book(combos, teacher=None, cover_data=None):
    """Generate workbook without formulas; first footer is row 34 and first name is B39."""
    plan = allocate_tables(combos)

    with open(TEMPLATE_PATH, "rb") as f:
        original_bytes = f.read()

    wb = openpyxl.load_workbook(
        _patch_pitch(original_bytes),
        data_only=False,
    )
    try:
        if SHEET_NAME not in wb.sheetnames:
            raise ValueError(
                f"لم يتم العثور على ورقة «{SHEET_NAME}» في القالب. "
                f"الأوراق الموجودة: {', '.join(wb.sheetnames)}"
            )

        ws = wb[SHEET_NAME]

        # Clear the name cells in every table that will be reused, including
        # unused rows in a partially filled table. Do not touch marks columns.
        used_table_indices = {item["table_idx"] for item in plan}
        for table_idx in used_table_indices:
            for row in _table_data_rows(table_idx):
                ws[f"{NAME_COL}{row}"] = None

        # Fill student names and the grade/section/subject footer only.
        # No formulas are created and no marks are calculated.
        for item in plan:
            combo = combos[item["combo_index"]]
            table_idx = item["table_idx"]
            footer_row = _table_footer_row(table_idx)

            for row, name in zip(_table_data_rows(table_idx), item["students"]):
                ws[f"{NAME_COL}{row}"] = name

            ws[f"{FOOTER_GRADE_COL}{footer_row}"] = f"الصف : {combo['grade']} {combo.get('track', '')}".rstrip()
            ws[f"{FOOTER_SECTION_COL}{footer_row}"] = (
                f"الشعبة ( {combo['class_section']} )"
            )
            ws[f"{FOOTER_SUBJECT_COL}{footer_row}"] = combo["subject"]

        saved = io.BytesIO()
        wb.save(saved)
    finally:
        wb.close()

    final_bytes = _finalize_with_original(saved.getvalue(), original_bytes, cover_data or {})
    return final_bytes, len(plan)


def _fill_textbox_in_drawing(xml_bytes, values):
    """Update text in existing named textboxes while retaining their formatting and positions."""
    root = ET.fromstring(xml_bytes)
    for shape in root.findall(f".//{{{NS_XDR}}}sp"):
        nv = shape.find(f"{{{NS_XDR}}}nvSpPr/{{{NS_XDR}}}cNvPr")
        if nv is None:
            continue
        field = COVER_SHAPES.get(nv.attrib.get("name", ""))
        if not field:
            continue
        value = str(values.get(field, "") or "").strip()
        tx_body = shape.find(f"{{{NS_XDR}}}txBody")
        if tx_body is None:
            continue
        paragraphs = tx_body.findall(f"{{{NS_A}}}p")
        paragraph = paragraphs[0] if paragraphs else ET.SubElement(tx_body, f"{{{NS_A}}}p")
        for child in list(paragraph):
            if child.tag in (f"{{{NS_A}}}r", f"{{{NS_A}}}fld"):
                paragraph.remove(child)
        if value:
            end_props = paragraph.find(f"{{{NS_A}}}endParaRPr")
            run = ET.Element(f"{{{NS_A}}}r")
            if end_props is not None:
                run_props = copy.deepcopy(end_props)
                run_props.tag = f"{{{NS_A}}}rPr"
                run.append(run_props)
            text_el = ET.SubElement(run, f"{{{NS_A}}}t")
            text_el.text = value
            if value[:1].isspace() or value[-1:].isspace():
                text_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            insert_at = list(paragraph).index(end_props) if end_props is not None else len(paragraph)
            paragraph.insert(insert_at, run)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _finalize_with_original(saved_bytes, original_bytes, cover_data=None):
    """Keep the original package, replace edited worksheet parts, and update only named cover textboxes."""
    import zipfile
    with zipfile.ZipFile(io.BytesIO(saved_bytes)) as zsaved:
        saved_names = set(zsaved.namelist())
        saved_parts = {name: zsaved.read(name) for name in PARTS_FROM_SAVED if name in saved_names}

    cover_data = cover_data or {}
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_bytes)) as zorig, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        written = set()
        for item in zorig.infolist():
            original_part = zorig.read(item.filename)
            if item.filename in COVER_DRAWINGS:
                data = _fill_textbox_in_drawing(original_part, cover_data)
            else:
                data = saved_parts.get(item.filename, original_part)
            zout.writestr(item, data)
            written.add(item.filename)
        for name, data in saved_parts.items():
            if name not in written:
                zout.writestr(name, data)
    out.seek(0)
    return out.getvalue()


# ---------------------------------------------------------------- جدول إدخال أسماء الطلاب (اسم كامل/عمود واحد)
def empty_names_df():
    return pd.DataFrame({"name": [""] * STUDENTS_PER_TABLE})


def build_students_from_df(df):
    """Return non-empty, unique student names in their original order."""
    names, seen = [], set()
    for _, row in df.iterrows():
        value = row.get("name", "")
        if pd.isna(value):
            continue
        name = str(value).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _reset_student_names():
    """Reset the editor when the selected grade, subject, or section changes."""
    st.session_state["mb_names_df"] = empty_names_df()
    st.session_state["mb_names_version"] = (
        st.session_state.get("mb_names_version", 0) + 1
    )
    # A previously generated file may belong to a different selection.
    st.session_state.pop("mb_result", None)


# ---------------------------------------------------------------- الواجهة
def _known_cover_data(user, ctx, class_opts, scope):
    """بيانات الأغلفة التي يعرفها النظام أصلًا (الاسم المعروف لا يُسأل عنه). غير المعروف = نص فارغ."""
    ctx = ctx or {}
    subjects = sorted({r["subject"] for r in scope})
    return {
        "directorate": ctx.get("directorate", ""),
        "school": ctx.get("school", ""),
        "teacher": ctx.get("teacher", ""),
        "classes": "، ".join(o["label"] for o in class_opts),
        "subjects": "، ".join(subjects),
        "hijri_date": f"{ctx['hijri_year']}هـ" if ctx.get("hijri_year") else "",
        "gregorian_date": f"{ctx['greg_year']}م" if ctx.get("greg_year") else "",
        "town": "",   # البلدة ليست محفوظة في الحساب (اللواء ≠ البلدة)، فتُسأل دائمًا
    }


COVER_LABELS = {
    "directorate": "مديرية التربية والتعليم", "town": "البلدة", "school": "اسم المدرسة", "teacher": "اسم المعلم",
    "classes": "الصفوف", "subjects": "المباحث", "hijri_date": "التاريخ الهجري (العام الدراسي)",
    "gregorian_date": "التاريخ الميلادي (العام الدراسي)",
}


def render_marks_book_builder(user, ctx=None):
    st.subheader("📒 دفتر العلامات")
    st.caption(
        "اختر الصف/التخصص والمبحث والشعبة وأدخل أسماء الطلاب. عند تغيير أي اختيار، "
        "يُفرغ نموذج الأسماء. لا تُجرى حسابات ولا تُضاف معادلات للعلامات."
    )

    scope = acc.teacher_scope(user["id"])
    if not scope:
        st.info("لم تُعتمد لك أي مباحث/صفوف بعد. يرجى التواصل مع الإدارة.")
        return

    try:
        tracks = catalog.list_tracks()
    except Exception:  # noqa: BLE001
        tracks = []
    class_opts = acc.class_options(user["id"], tracks, scope)
    if not class_opts:
        st.info("لا توجد صفوف متاحة.")
        return

    combos = st.session_state.setdefault("mb_combos", [])
    st.session_state.setdefault("mb_names_version", 0)
    st.session_state.setdefault("mb_names_df", empty_names_df())

    # ---- بيانات الأغلفة: المعروف يُعبَّأ تلقائيًا، ويُطلب من المعلم غير المعروف فقط
    st.markdown("#### بيانات الأغلفة")
    known = _known_cover_data(user, ctx, class_opts, scope)
    known_keys = [k for k, v in known.items() if v]
    unknown_keys = [k for k, v in known.items() if not v]
    cover = dict(known)
    if known_keys:
        st.caption("✅ تُعبَّأ الأغلفة تلقائيًا بما يعرفه النظام عنك: " +
                   "، ".join(f"{COVER_LABELS[k]}: **{known[k]}**" for k in known_keys))
    for k in unknown_keys:   # الحقول التي لا يعرفها النظام فقط
        cover[k] = st.text_input(COVER_LABELS[k], key=f"mb_cover_{k}")
    if known_keys:
        with st.expander("✏️ تعديل البيانات المعروفة (اختياري)"):
            for k in known_keys:
                cover[k] = st.text_input(COVER_LABELS[k], value=known[k], key=f"mb_cover_edit_{k}")
    st.session_state["mb_cover_data"] = cover

    st.markdown("#### إضافة تركيبة جديدة")

    class_label = st.selectbox(
        "الصف / التخصص",
        [o["label"] for o in class_opts],
        key="mb_class",
        on_change=_reset_student_names,
    )
    opt = next(o for o in class_opts if o["label"] == class_label)
    grade = opt["grade"]

    grade_subjects = sorted(opt["subjects"])
    if not grade_subjects:
        st.info("لا توجد مباحث معتمدة لهذا الصف.")
        return

    # Keep the subject valid if the class has changed.
    if st.session_state.get("mb_subject") not in grade_subjects:
        st.session_state["mb_subject"] = grade_subjects[0]

    subject = st.selectbox(
        "المبحث",
        grade_subjects,
        key="mb_subject",
        on_change=_reset_student_names,
    )

    class_section = st.text_input(
        "الشعبة",
        placeholder="مثال: أ",
        key="mb_section",
        on_change=_reset_student_names,
    )

    st.markdown("#### أسماء الطلاب")
    st.caption(
        "أدخل اسمًا كاملًا في كل سطر. يبدأ أول اسم في ملف Excel من B39. "
        "يمكن إدخال أكثر من 25 طالبًا، وسيستخدم النظام جداول إضافية."
    )

    editor_version = st.session_state["mb_names_version"]
    editor_key = f"mb_names_editor_{editor_version}"

    edited = st.data_editor(
        st.session_state["mb_names_df"],
        column_config={
            "name": st.column_config.TextColumn("اسم الطالب كاملًا")
        },
        num_rows="dynamic",
        hide_index=True,
        key=editor_key,
        use_container_width=True,
    )
    st.session_state["mb_names_df"] = edited

    if st.button("➕ إضافة هذه التركيبة إلى الدفتر", type="primary", key="mb_add_combo"):
        names = build_students_from_df(edited)
        section = class_section.strip()

        if not section:
            st.error("يرجى إدخال الشعبة.")
        elif not names:
            st.error("يرجى إدخال اسم طالب واحد على الأقل.")
        elif any(
            c["grade"] == grade
            and c.get("track_id") == opt["track_id"]
            and c["subject"] == subject
            and c["class_section"] == section
            for c in combos
        ):
            st.error(
                "هذه التركيبة (الصف/المبحث/الشعبة) مضافة مسبقًا. "
                "احذفها أولًا إن أردت تعديلها."
            )
        else:
            combos.append({
                "grade": grade,
                "track_id": opt["track_id"],
                "track": opt["track"],
                "class_label": opt["label"],
                "subject": subject,
                "class_section": section,
                "students": names,
            })
            _reset_student_names()
            st.success(
                f"تمت إضافة «{subject} - {opt['label']} - شعبة {section}» "
                f"({len(names)} طالبًا)."
            )
            st.rerun()

    if combos:
        st.divider()
        st.markdown("#### التركيبات المضافة")

        for i, combo in enumerate(combos):
            col1, col2 = st.columns([5, 1])
            col1.write(
                f"{i + 1}. **{combo['subject']}** — {combo.get('class_label') or 'الصف ' + str(combo['grade'])} — "
                f"شعبة {combo['class_section']} ({len(combo['students'])} طالبًا)"
            )
            if col2.button("🗑️ حذف", key=f"mb_del_{i}"):
                combos.pop(i)
                st.session_state.pop("mb_result", None)
                st.rerun()

        total_students = sum(len(c["students"]) for c in combos)
        total_tables = sum(
            (len(c["students"]) + STUDENTS_PER_TABLE - 1) // STUDENTS_PER_TABLE
            for c in combos
        )
        st.caption(
            f"إجمالي الطلاب: {total_students} — الجداول المطلوبة: "
            f"{total_tables} من أصل {len(TABLE_STARTS)}."
        )

        if st.button("📘 توليد دفتر العلامات الكامل", type="primary", key="mb_generate"):
            try:
                data, n_tables = generate_marks_book(combos, user, st.session_state.get("mb_cover_data", {}))
                st.session_state["mb_result"] = {
                    "data": data,
                    "n_tables": n_tables,
                }
                st.success(f"تم توليد الدفتر باستخدام {n_tables} جدولًا.")
            except ValueError as e:
                st.session_state.pop("mb_result", None)
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.session_state.pop("mb_result", None)
                st.error(f"حدث خطأ أثناء توليد الملف: {e}")

    result = st.session_state.get("mb_result")
    if result:
        st.download_button(
            "📥 تنزيل دفتر العلامات",
            data=result["data"],
            file_name="دفتر_العلامات.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            key="mb_download",
        )


# ---------------------------------------------------------------- ملاحظات مهمة
# - بيانات الصف/الشعبة/المبحث لأول جدول تُكتب في الصف 34، وأول اسم طالب في B39.
# - لا ينشئ هذا الملف معادلات ولا يحسب العلامات.
# - تُحفظ صور ورسومات الأغلفة الأصلية وتُحدّث نصوص صناديق النصوص المسماة فقط.
# - st.data_editor لا يوفّر خيارًا رسميًا لتفعيل أول خلية تلقائيًا؛ يلزم النقر عليها.
