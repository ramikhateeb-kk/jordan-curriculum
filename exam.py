"""
ميزة (إنشاء اختبار) للمعلم:
1) يختار المعلم درسًا أو أكثر وعدد كل نوع من الأسئلة وعلامته.
2) يقترح النظام أسئلة أكثر من المطلوب بقليل (من بنك الأسئلة أولًا، ثم يولّد جديدًا عند الحاجة فقط —
   بنفس آلية "قيّمني" والتحقق الحرفي من الأسماء والمصطلحات)، ليختار المعلم منها.
3) يُصدَّر اختبار Word بترويسة مدرسية رسمية، بالكامل من اليمين إلى اليسار.
"""
import io
import random
from datetime import date

import streamlit as st
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

import qbank
from quiz import _generate, correct_text

TYPE_LABELS = {"mcq": "اختيار من متعدد", "tf": "صح أو خطأ", "fill": "أكمل الفراغ", "short": "سؤال قصير"}
EXAM_KINDS = ["الأول", "الثاني", "النهائي"]
ORDINALS = ["الأول", "الثاني", "الثالث", "الرابع"]
SECTION_INSTRUCTIONS = {
    "mcq": "ضع دائرة حول رمز الإجابة الصحيحة في كل مما يلي:",
    "tf": "ضع إشارة (✓) أمام العبارة الصحيحة، وإشارة (✗) أمام العبارة الخاطئة فيما يلي:",
    "fill": "أكمل الفراغات التالية بما يناسبها من المعلومات الصحيحة:",
    "short": "أجب عن الأسئلة التالية إجابة وافية:",
}
ARABIC_FONT = "Arial"


# ---------------------------------------------------------------- جمع الأسئلة المرشَّحة (بلا تغيير)
def _collect_candidates(client, idx, slug, lessons, qtype, need, used_ids, used_texts):
    """يجمع (need + 2) سؤال مرشَّح: من البنك أولًا، ثم يولّد الباقي بالذكاء الاصطناعي عند الحاجة فقط."""
    target = need + 2
    out, pool = [], []
    for lesson in lessons:
        bank = qbank.list_questions(slug, lesson["start"], lesson["end"], qtype)
        pool += [(lesson, qid, data) for qid, data in bank
                if qid not in used_ids and data.get("question") not in used_texts]
    random.shuffle(pool)
    for lesson, qid, data in pool:
        if len(out) >= target:
            break
        q = dict(data)
        q["_lesson"] = lesson["title"]
        out.append(q)
        used_ids.add(qid)
        used_texts.append(q["question"])
    tries = 0
    while len(out) < target and tries < target * 2:
        tries += 1
        lesson = random.choice(lessons)
        q, new_id = _generate(client, idx, slug, lesson, qtype, used_texts)
        if not q:
            continue
        q["_lesson"] = lesson["title"]
        out.append(q)
        used_texts.append(q["question"])
        if new_id is not None:
            used_ids.add(new_id)
    return out


# ---------------------------------------------------------------- أدوات Word: اتجاه من اليمين إلى اليسار
# ملاحظة مهمة: اتجاه الصفحة (w:bidi في sectPr) واتجاه الفقرة (w:bidi في pPr) وحدهما لا يكفيان في
# Word لعرض الأقواس والنقاط والأرقام بترتيبها الصحيح — يجب أيضًا وسم كل "تشغيلة نص" (run) نفسها
# بخاصية rtl صراحة (Font.rtl)، وإلا تُحلَّل الرموز الضعيفة (الأقواس، النقاط) وفق قواعد اتجاه خاطئة
# فتظهر معكوسة، وهذا بالضبط ما كان ناقصًا سابقًا.
CONTENT_WIDTH = Cm(18)

def _set_pPr_element(p, tag, value):
    """إضافة/تحديث عنصر داخل خصائص الفقرة."""
    p_pr = p._p.get_or_add_pPr()
    el = p_pr.find(qn(tag))
    if el is None:
        el = OxmlElement(tag)
        p_pr.append(el)
    el.set(qn("w:val"), value)
    return el


def _rtl_section(section):
    """جعل اتجاه القسم في Word من اليمين إلى اليسار."""
    sect_pr = section._sectPr
    if sect_pr.find(qn("w:bidi")) is None:
        sect_pr.append(OxmlElement("w:bidi"))


def _rtl_table(table):
    """
    نترك الجدول نفسه باتجاه LTR كما يفعل Word عند الضغط على
    «اتجاه النص من اليسار إلى اليمين» يدويًا.

    هذا مهم جدًا هنا: المحتوى عربي، لكن اتجاه الجدول/الفقرات
    يكون LTR، ثم نحدد محاذاة كل فقرة صراحةً (يمين/وسط/يسار).
    بهذه الطريقة يتصرف ملف DOCX مثل الجدول الذي يتم إصلاحه يدويًا
    داخل Word.
    """
    tbl_pr = table._tbl.tblPr

    # إزالة أي bidiVisual سابق
    bidi_visual = tbl_pr.find(qn("w:bidiVisual"))
    if bidi_visual is not None:
        tbl_pr.remove(bidi_visual)

    # إجبار اتجاه الجدول إلى LTR
    tbl_dir = tbl_pr.find(qn("w:tblDir"))
    if tbl_dir is None:
        tbl_dir = OxmlElement("w:tblDir")
        tbl_pr.append(tbl_dir)
    tbl_dir.set(qn("w:val"), "ltr")

    return table


def _no_borders(table):
    """إخفاء حدود الجدول."""
    tbl_pr = table._tbl.tblPr
    old = tbl_pr.find(qn("w:tblBorders"))
    if old is not None:
        tbl_pr.remove(old)

    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tbl_pr.append(borders)


def _rtl_p(p, align=WD_ALIGN_PARAGRAPH.RIGHT):
    """
    ضبط المحاذاة مع إبقاء اتجاه الفقرة LTR، وهو نفس الإصلاح
    الذي يحدث عند تحديد الجدول في Word ثم اختيار «اتجاه النص
    من اليسار إلى اليمين».

    لا نضيف w:bidi هنا؛ لأن وجوده كان سببًا رئيسيًا في اختلاف
    النتيجة بين الملف المنشأ برمجيًا والجدول بعد إصلاحه يدويًا.
    """
    p_pr = p._p.get_or_add_pPr()

    # إزالة w:bidi إن كان موجودًا من Normal style أو من إنشاء سابق
    bidi = p_pr.find(qn("w:bidi"))
    if bidi is not None:
        p_pr.remove(bidi)

    # محاذاة صريحة
    jc = p_pr.find(qn("w:jc"))
    if jc is None:
        jc = OxmlElement("w:jc")
        p_pr.append(jc)

    if align == WD_ALIGN_PARAGRAPH.CENTER:
        jc.set(qn("w:val"), "center")
    elif align == WD_ALIGN_PARAGRAPH.LEFT:
        jc.set(qn("w:val"), "left")
    else:
        jc.set(qn("w:val"), "right")

    # إزالة أي إزاحة موروثة
    ind = p_pr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        p_pr.append(ind)
    ind.set(qn("w:left"), "0")
    ind.set(qn("w:right"), "0")
    ind.set(qn("w:firstLine"), "0")
    ind.set(qn("w:hanging"), "0")

    pf = p.paragraph_format
    pf.left_indent = Cm(0)
    pf.right_indent = Cm(0)
    pf.first_line_indent = Cm(0)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)

    return p


def _run(p, text, size=12, bold=False, underline=False):
    """إضافة نص عربي مع إجبار Word على التعامل معه كسياق RTL."""
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.underline = underline
    r.font.name = ARABIC_FONT
    r.font.rtl = True
    r.font.complex_script = True

    r_pr = r._element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)

    r_fonts.set(qn("w:ascii"), ARABIC_FONT)
    r_fonts.set(qn("w:hAnsi"), ARABIC_FONT)
    r_fonts.set(qn("w:cs"), ARABIC_FONT)

    return r


def _center(doc, text, size=13, bold=True):
    p = doc.add_paragraph()
    _rtl_p(p, WD_ALIGN_PARAGRAPH.CENTER)
    _run(p, text, size, bold)
    return p


def _right(doc, text, size=12, bold=False):
    """
    إنشاء سطر بعرض الصفحة كاملًا ثم محاذاة النص إلى أقصى اليمين.

    استخدام خلية واحدة بعرض منطقة الكتابة يجعل Word لا يستطيع
    تقليص عرض الفقرة إلى عرض سابق أو وراثته من جدول آخر.
    """
    t = _doc_table(
        doc,
        1,
        1,
        [CONTENT_WIDTH]
    )
    cell = t.rows[0].cells[0]
    p = _rtl_p(
        cell.paragraphs[0],
        WD_ALIGN_PARAGRAPH.RIGHT
    )
    _run(p, text, size, bold)
    return p


def _left(doc, text, size=12, bold=False):
    """سطر بعرض الصفحة كاملًا ومحاذاة أقصى اليسار."""
    t = _doc_table(
        doc,
        1,
        1,
        [CONTENT_WIDTH]
    )
    cell = t.rows[0].cells[0]
    p = _rtl_p(
        cell.paragraphs[0],
        WD_ALIGN_PARAGRAPH.LEFT
    )
    _run(p, text, size, bold)
    return p


def _get_or_add(parent, tag):
    el = parent.find(qn(tag))
    if el is None:
        el = OxmlElement(tag)
        parent.append(el)
    return el


def _doc_table(doc, rows, cols, col_widths):
    """
    إنشاء جدول بعرض محدد ومحاذاته إلى اليمين.

    مع bidiVisual:
        cell[0] تظهر في أقصى اليمين
        cell[1] في الوسط
        cell[2] في أقصى اليسار
    """
    t = doc.add_table(rows=rows, cols=cols)
    t.autofit = False
    _rtl_table(t)
    _no_borders(t)

    tbl_pr = t._tbl.tblPr

    total_twips = sum(int(w.twips) for w in col_widths)

    tbl_w = _get_or_add(tbl_pr, "w:tblW")
    tbl_w.set(qn("w:w"), str(total_twips))
    tbl_w.set(qn("w:type"), "dxa")

    jc = _get_or_add(tbl_pr, "w:jc")
    jc.set(qn("w:val"), "right")

    tbl_layout = _get_or_add(tbl_pr, "w:tblLayout")
    tbl_layout.set(qn("w:type"), "fixed")

    # ضبط شبكة الأعمدة
    grid = t._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        grid_cols = grid.findall(qn("w:gridCol"))
        for grid_col, width in zip(grid_cols, col_widths):
            grid_col.set(qn("w:w"), str(int(width.twips)))

    # ضبط عرض الخلايا نفسها
    for row in t.rows:
        for cell, width in zip(row.cells, col_widths):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(int(width.twips)))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = width

    return t


def _info_row(doc, right, middle, left):
    t = _doc_table(
        doc,
        1,
        3,
        [Cm(6), Cm(6), Cm(6)]
    )
    for cell, val in zip(t.rows[0].cells, (right, middle, left)):
        _run(
            _rtl_p(
                cell.paragraphs[0],
                WD_ALIGN_PARAGRAPH.RIGHT
            ),
            val,
            12
        )
    return t


def _set_cell_margins(cell, top=0, start=0, bottom=0, end=0):
    """إزالة الهوامش الداخلية للخلايا حتى تصل الكتابة للحافة."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)

    for side, value in (
        ("top", top),
        ("start", start),
        ("bottom", bottom),
        ("end", end),
    ):
        node = tc_mar.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


# ----------------------------------------------------------------
# بناء ملف Word
# ----------------------------------------------------------------

def build_docx(header, selected_by_type, marks, logo_bytes):
    doc = Document()

    # ============================================================
    # إعداد صفحة A4 وعرض منطقة الكتابة بدقة
    # ============================================================

    section = doc.sections[0]

    section.page_width = Cm(21)
    section.page_height = Cm(29.7)

    section.top_margin = Cm(1.3)
    section.bottom_margin = Cm(1.3)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)

    section.header_distance = Cm(0.5)
    section.footer_distance = Cm(0.5)

    _rtl_section(section)

    # ============================================================
    # الشعار
    # ============================================================

    if logo_bytes:
        p = doc.add_paragraph()
        _rtl_p(p, WD_ALIGN_PARAGRAPH.CENTER)

        try:
            p.add_run().add_picture(
                io.BytesIO(logo_bytes),
                width=Cm(2.6)
            )
        except Exception:  # noqa: BLE001
            pass

    # ============================================================
    # رأس الاختبار
    # ============================================================

    _center(
        doc,
        (
            f"مديرية التربية والتعليم للواء {header['liwa']}"
            if header["liwa"]
            else "مديرية التربية والتعليم"
        )
    )

    _center(
        doc,
        header["school"] or "اسم المدرسة"
    )

    _center(
        doc,
        f"الاختبار {header['kind']} لمبحث {header['subject']}"
    )

    year_txt = (
        f"للعام الدراسي {header['year']}"
        if header["year"]
        else "للعام الدراسي ....... / ......."
    )

    _center(
        doc,
        f"الفصل الدراسي: {header['semester_label']}     {year_txt}",
        12,
        False
    )

    # ============================================================
    # بيانات الطالب
    #
    # A4 = 21 سم
    # الهوامش = 1.5 + 1.5
    # مساحة الكتابة = 18 سم
    #
    # مع bidiVisual:
    # cell[0] = أقصى اليمين
    # cell[1] = الوسط
    # cell[2] = أقصى اليسار
    # ============================================================

    # ترتيب الخلايا الفيزيائي: يسار = مدة الامتحان، وسط = التاريخ، يمين = اسم الطالب.
    t = _doc_table(
        doc,
        1,
        3,
        [Cm(6), Cm(6), Cm(6)]
    )

    duration_cell, date_cell, name_cell = t.rows[0].cells

    _run(
        _rtl_p(duration_cell.paragraphs[0], WD_ALIGN_PARAGRAPH.LEFT),
        f"مدة الامتحان: {header['duration']}",
        12
    )

    _run(
        _rtl_p(date_cell.paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER),
        f"التاريخ: {header['date']}",
        12
    )

    name_p = _rtl_p(name_cell.paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT)
    _run(name_p, "اسم الطالب: ", 12)
    _run(name_p, "\u00a0" * 18, 12, underline=True)

    doc.add_paragraph()

    # ============================================================
    # الأسئلة
    # ============================================================

    ordinal_i = 0

    sections_summary = []

    for qtype in ["mcq", "tf", "fill", "short"]:

        items = selected_by_type.get(qtype) or []

        if not items:
            continue

        ordinal = (
            ORDINALS[ordinal_i]
            if ordinal_i < len(ORDINALS)
            else str(ordinal_i + 1)
        )

        ordinal_i += 1

        mark_txt = (
            f"({marks.get(qtype)} علامة)"
            if marks.get(qtype)
            else ""
        )

        # --------------------------------------------------------
        # عنوان السؤال الرئيسي بعرض 18 سم كاملًا
        # --------------------------------------------------------

        # ترتيب الخلايا الفيزيائي: اليسار = العلامة، اليمين = السؤال الرئيسي.
        t = _doc_table(
            doc,
            1,
            2,
            [Cm(4), Cm(14)]
        )

        mark_cell, question_cell = t.rows[0].cells

        p0 = _rtl_p(
            question_cell.paragraphs[0],
            WD_ALIGN_PARAGRAPH.RIGHT
        )
        _run(
            p0,
            f"السؤال {ordinal} : {SECTION_INSTRUCTIONS[qtype]}",
            13,
            True
        )

        p1 = _rtl_p(
            mark_cell.paragraphs[0],
            WD_ALIGN_PARAGRAPH.LEFT
        )
        _run(p1, mark_txt, 13, True)

        # --------------------------------------------------------
        # الأسئلة الفرعية
        # --------------------------------------------------------

        entries = []

        for local_n, q in enumerate(items, start=1):

            # كل سؤال في خلية بعرض الصفحة كاملًا
            # لضمان وصول النص إلى أقصى اليمين.

            # ----------------------------------------------------
            # نص السؤال الفرعي
            # في صح أو خطأ نضع رمزي الصح والخطأ في نهاية
            # السؤال نفسه، وليس في سطر مستقل.
            # ----------------------------------------------------

            if qtype == "tf":
                # صح أو خطأ: نضع قوسًا فارغًا في نهاية نفس سطر السؤال،
                # ليضع الطالب داخله إشارة (✓) أو (✗) بنفسه.
                # نستخدم LRM حول الأقواس حتى تبقى في نهاية السطر
                # ولا تنتقل إلى بدايته بسبب خوارزمية RTL/LTR في Word.
                t_q = _doc_table(doc, 1, 1, [CONTENT_WIDTH])
                cell_q = t_q.rows[0].cells[0]
                p_q = _rtl_p(
                    cell_q.paragraphs[0],
                    WD_ALIGN_PARAGRAPH.RIGHT
                )
                _run(p_q, f"{local_n}. {q['question']}", 12)

                # فاصل صغير ثم القوس الفارغ في نهاية السؤال
                box_run = p_q.add_run("  \u200e(        )\u200e")
                box_run.font.size = Pt(12)
                box_run.font.name = ARABIC_FONT
                box_run.font.rtl = False
                box_run.font.complex_script = False
            else:
                _right(
                    doc,
                    f"{local_n}. {q['question']}"
                )

            # ----------------------------------------------------
            # الاختيارات
            # ----------------------------------------------------

            if qtype == "mcq":

                for i, opt in enumerate(q["options"]):

                    _right(
                        doc,
                        f"{'أبجد'[i]}) {opt}"
                    )

            # ----------------------------------------------------
            # صح أو خطأ
            # ----------------------------------------------------
            # القوس الفارغ موجود في نفس سطر السؤال أعلاه.
            # لا نضيف أي سطر إضافي.

            elif qtype == "tf":
                pass

            # ----------------------------------------------------
            # سؤال قصير
            # ----------------------------------------------------

            elif qtype == "short":

                for _ in range(2):

                    _right(
                        doc,
                        "." * 75
                    )

            entries.append(
                (
                    local_n,
                    qtype,
                    q
                )
            )

        sections_summary.append(
            (
                ordinal,
                TYPE_LABELS[qtype],
                entries
            )
        )

        doc.add_paragraph()

    # ============================================================
    # نهاية الأسئلة
    # ============================================================

    # صف ختامي غير مرئي، بنفس التنسيق الأصلي:
    # انتهت الأسئلة يسارًا، التمنيات في الوسط، ومعلم المبحث يمينًا.
    # بما أن الجدول LTR، فترتيب الخلايا الفيزيائي هو: يسار، وسط، يمين.
    end_t = _doc_table(
        doc,
        1,
        3,
        [Cm(6), Cm(6), Cm(6)]
    )

    left_cell, center_cell, right_cell = end_t.rows[0].cells

    _run(
        _rtl_p(left_cell.paragraphs[0], WD_ALIGN_PARAGRAPH.LEFT),
        "انتهت الأسئلة",
        12,
        True
    )

    _run(
        _rtl_p(center_cell.paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER),
        "مع أطيب الأمنيات بالنجاح",
        12,
        True
    )

    # اسم المعلم من حقل النموذج مباشرة، وفي خلية اليمين.
    teacher_p = _rtl_p(
        right_cell.paragraphs[0],
        WD_ALIGN_PARAGRAPH.RIGHT
    )
    _run(teacher_p, "معلم المبحث: ", 12, True)

    teacher_name = (header.get("teacher") or "").strip()
    if teacher_name:
        _run(teacher_p, teacher_name, 12, True)
    else:
        _run(teacher_p, "\u00a0" * 14, 12, True, underline=True)

    # ============================================================
    # نموذج الإجابة
    # ============================================================

    doc.add_page_break()

    _right(
        doc,
        "نموذج الإجابة (مرجع المعلم)",
        13,
        True
    )

    for ordinal, label, entries in sections_summary:

        doc.add_paragraph()

        # عنوان القسم
        _right(
            doc,
            f"السؤال {ordinal} ({label}):",
            12,
            True
        )

        for local_n, qtype, q in entries:

            page = (
                f" (صفحة {q['page']})"
                if q.get("page")
                else ""
            )

            _right(
                doc,
                f"{local_n}. {correct_text(q)}{page}"
            )

    # ============================================================
    # حفظ الملف
    # ============================================================

    buf = io.BytesIO()
    doc.save(buf)

    return buf.getvalue()



def render_exam_builder(idx, slug, subject, sem, flat_lessons, ctx=None, user=None):
    import auth_ui
    import profile_ctx
    ctx = ctx or {}
    S = st.session_state
    S.setdefault("exam", None)

    st.subheader("إنشاء اختبار")
    if not flat_lessons:
        st.info("لم تُدخل دروس هذا الكتاب بعد.")
        return

    labels = [l["label"] for l in flat_lessons]
    sel_labels = st.multiselect("اختر درسًا أو أكثر", labels, default=labels[:1])
    lessons = [l for l in flat_lessons if l["label"] in sel_labels]

    st.caption("حدّد عدد كل نوع من الأسئلة وعلامة القسم الكلية (اترك العدد 0 لتجاهل نوع ما):")
    counts, marks = {}, {}
    for qtype in ["mcq", "tf", "fill", "short"]:
        c1, c2 = st.columns([2, 1])
        counts[qtype] = c1.number_input(TYPE_LABELS[qtype], min_value=0, value=0, step=1, key=f"cnt_{qtype}")
        marks[qtype] = c2.number_input("العلامة", min_value=0, value=10, step=1, key=f"mk_{qtype}",
                                       disabled=counts[qtype] == 0)
    total_needed = sum(counts.values())

    if st.button("🔎 اقترح الأسئلة", type="primary", disabled=not (lessons and total_needed)):
        from rag import get_client
        if user is not None:
            auth_ui.require_quota_or_stop(user)   # خصم واحد لكل عملية اقتراح أسئلة
        client = get_client()
        used_ids, used_texts = set(), []
        candidates = {}
        with st.spinner("جارٍ إعداد الأسئلة المقترحة..."):
            for qtype, need in counts.items():
                if need:
                    candidates[qtype] = _collect_candidates(client, idx, slug, lessons, qtype, need,
                                                             used_ids, used_texts)
        S["exam"] = {"lessons": lessons, "counts": counts, "marks": marks, "candidates": candidates,
                    "picks": {qtype: list(range(min(need, len(candidates.get(qtype, [])))))
                              for qtype, need in counts.items()}}
        st.rerun()

    exam = S["exam"]
    if not exam:
        return

    st.divider()
    st.markdown("#### راجع الأسئلة المقترحة واختر ما يناسبك")
    for qtype, items in exam["candidates"].items():
        if not items:
            continue
        st.markdown(f"**{TYPE_LABELS[qtype]}** (المطلوب: {exam['counts'][qtype]})")
        picks = exam["picks"].setdefault(qtype, [])
        for i, q in enumerate(items):
            checked = st.checkbox(
                f"{q['question']}" + (f" — {q['options'][q['correct_index']]}" if qtype == "mcq" else ""),
                value=i in picks, key=f"pick_{qtype}_{i}")
            if checked and i not in picks:
                picks.append(i)
            if not checked and i in picks:
                picks.remove(i)
        chosen_n = len(exam["picks"].get(qtype, []))
        if chosen_n != exam["counts"][qtype]:
            st.caption(f"⚠️ اخترت {chosen_n} من أصل {exam['counts'][qtype]} مطلوبة لهذا النوع.")

    st.divider()
    st.markdown("#### بيانات الترويسة")
    # المعروف من حساب المعلم والتقويم الدراسي لا يُسأل عنه: اللواء، المدرسة، المعلم، العام الدراسي، الفصل
    profile_ctx.known_summary([("اللواء", ctx.get("division")), ("المدرسة", ctx.get("school")),
                               ("المعلم", ctx.get("teacher")), ("العام الدراسي", ctx.get("greg_year")),
                               ("الفصل", ctx.get("sem_name"))])
    c1, c2 = st.columns(2)
    with c1:
        liwa = profile_ctx.known_input("اللواء", ctx.get("division"), "ex_liwa")
    with c2:
        school = profile_ctx.known_input("اسم المدرسة", ctx.get("school"), "ex_school")
    c3, c4 = st.columns(2)
    kind = c3.selectbox("نوع الاختبار", EXAM_KINDS)
    duration = c4.text_input("مدة الاختبار", value="45 دقيقة")
    c5, c6 = st.columns(2)
    this_year = date.today().year
    default_year = f"{this_year}/{this_year+1}" if date.today().month >= 9 else f"{this_year-1}/{this_year}"
    with c5:
        year = ctx.get("greg_year") or st.text_input("العام الدراسي", value=default_year)
    exam_date = c6.date_input("التاريخ", value=date.today())
    c7, c8 = st.columns(2)
    with c7:
        teacher = profile_ctx.known_input("اسم معلم المبحث", ctx.get("teacher"), "ex_teacher")
    logo = c8.file_uploader("شعار المدرسة (اختياري)", type=["png", "jpg", "jpeg"])

    ready = any(exam["picks"].values())
    if st.button("🖨️ إنشاء ملف الاختبار (Word)", type="primary", disabled=not ready):
        selected_by_type = {qtype: [exam["candidates"][qtype][i] for i in sorted(idxs)]
                            for qtype, idxs in exam["picks"].items() if idxs}
        header = {"liwa": liwa.strip(), "school": school.strip(), "subject": subject, "kind": kind,
                  "semester_label": "الأول" if sem == 1 else "الثاني", "duration": duration,
                  "year": year.strip(), "date": exam_date.strftime("%Y/%m/%d"), "teacher": teacher.strip()}
        data = build_docx(header, selected_by_type, {k: v for k, v in exam["marks"].items() if exam["counts"][k]},
                          logo.getvalue() if logo else None)
        st.download_button("⬇️ تنزيل الاختبار", data=data, file_name=f"اختبار_{subject}.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
