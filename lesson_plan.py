"""
ميزة (خطة درس) للمعلم: لكل درس مختار، يُنتج ملف Word بنموذج خطة الدرس الرسمي (صفحة واحدة أفقية لكل
درس)، تملأ فيه بيانات المبحث والوحدة والدرس تلقائيًا، ويملأ الذكاء الاصطناعي التعلم القبلي والنتاجات
التعليمية ودور المعلم/المتعلم في كل مرحلة، اعتمادًا على نص الدرس نفسه فقط.
"""
import io
import json
import re

import streamlit as st
from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from google.genai import types

import accounts as acc
import auth_ui
import english_docs as en
import plan_cache
import profile_ctx
from config import GEMINI_MODEL
from rag import get_client, select_context
from word_rtl import center as _center, doc_table as _doc_table
from word_rtl import no_borders as _no_borders
from word_rtl import rtl_p as _rtl_p, rtl_section as _rtl_section
from word_rtl import rtl_table as _rtl_table, run as _run
from word_rtl import vertical_cell as _vertical_cell

STAGES = ["1- التهيئة واستكشاف", "2- الشرح والتفسير", "3- التوسع والدعم", "4- التقييم"]

SYSTEM = (
    "أنت مشرف تربوي خبير يساعد معلمي المنهاج الأردني على إعداد خطط الدروس. اعتمد في المحتوى على "
    "نص الدرس المرفق فقط، ولا تخرج عن موضوعه. اكتب بالعربية الفصحى الواضحة والعملية وبشكل مركز "
    "(بحيث لا يتجاوز النص في كل خلية 2 إلى 3 أسطر كحد أقصى)، بصيغة أفعال إجرائية مثل: يعرض، يطرح، يناقش... "
    "شرط أساسي: عدم التطويل لكي تتسع الخطة بشكل متناسق في صفحة واحدة. أعد JSON فقط بلا أي نص آخر."
)
SCHEMA = '''{
  "prior_learning": "جملة واحدة مركزة عن التعلم القبلي",
  "outcomes": ["نتاج 1 مركز", "نتاج 2 مركز", "نتاج 3 مركز"],
  "stages": [
    {"teacher_role": "دور المعلم (سطران إلى ثلاثة)", "student_role": "دور المتعلم (سطران إلى ثلاثة)"},
    {"teacher_role": "دور المعلم (سطران إلى ثلاثة)", "student_role": "دور المتعلم (سطران إلى ثلاثة)"},
    {"teacher_role": "دور المعلم (سطران إلى ثلاثة)", "student_role": "دور المتعلم (سطران إلى ثلاثة)"},
    {"teacher_role": "دور المعلم (سطران إلى ثلاثة)", "student_role": "دور المتعلم (سطران إلى ثلاثة)"}
  ]
}'''


def _valid(data):
    try:
        return (isinstance(data.get("prior_learning"), str) and data["prior_learning"].strip()
                and isinstance(data.get("outcomes"), list) and 1 <= len(data["outcomes"]) <= 6
                and isinstance(data.get("stages"), list) and len(data["stages"]) == 4
                and all(isinstance(s.get("teacher_role"), str) and s["teacher_role"].strip()
                       and isinstance(s.get("student_role"), str) and s["student_role"].strip()
                       for s in data["stages"]))
    except Exception:  # noqa: BLE001
        return False


def _generate_plan(idx, lesson, lang="ar"):
    """يستخرج محتوى الخطة من الذكاء الاصطناعي اعتمادًا على نص الدرس فقط (بالعربية أو الإنجليزية)."""
    client = get_client()
    ctx_pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=30000)
    if not ctx_pages:
        return None
    if lang == "en":
        ctx = "\n\n".join(f"=== Page {p['page']} ===\n{p['text']}" for p in ctx_pages)
        system, prompt = en.SYSTEM_LESSON, (
            f"Lesson: {lesson['title']}\n\nLesson text:\n{ctx}\n\n"
            f"Return the lesson plan in exactly this format, 2-3 lines per cell:\n{en.SCHEMA_LESSON}")
    else:
        ctx = "\n\n".join(f"=== صفحة {p['page']} ===\n{p['text']}" for p in ctx_pages)
        system, prompt = SYSTEM, (f"الدرس: {lesson['title']}\n\nنص الدرس:\n{ctx}\n\n"
                                  f"أعد خطة الدرس بهذا الشكل بالضبط وفي حدود 2-3 أسطر لكل خلية:\n{SCHEMA}")
    for _ in range(3):
        try:
            r = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0.3,
                                                    response_mime_type="application/json"))
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", r.text.strip()).strip())
        except Exception as e:  # noqa: BLE001
            print("خطأ في توليد خطة الدرس:", e)
            continue
        if _valid(data):
            return data
    return None


def get_or_generate_plan(idx, slug, lesson, user=None, lang="ar"):
    """من قاعدة البيانات أولًا، وإلا يولّد ويحفظ للمرة القادمة. اللغة تابعة للكتاب نفسه (slug)،
    فلا حاجة لمفتاح لغة في الجدول. الحصة اليومية تُخصم فقط عند الاستدعاء الفعلي لجيمناي."""
    cached = plan_cache.get_plan(slug, lesson["start"], lesson["end"])
    if cached:
        return cached, True
    if user is not None:
        auth_ui.require_quota_or_stop(user)
    data = _generate_plan(idx, lesson, lang)
    if data:
        try:
            plan_cache.save_plan(slug, lesson["start"], lesson["end"], data)
        except Exception as e:  # noqa: BLE001
            print("تعذّر حفظ خطة الدرس في قاعدة البيانات:", e)
    return data, False


def _set_row_height(row, height):
    """ضبط الحد الأدنى لارتفاع الصف لاستغلال المساحة الرأسية بمرونة."""
    trPr = row._tr.get_or_add_trPr()
    trHeight = OxmlElement('w:trHeight')
    trHeight.set(qn('w:val'), str(int(height.twips)))
    trHeight.set(qn('w:hRule'), 'atLeast')
    trPr.append(trHeight)


def _set_cell_borders(cell, top=True, bottom=True, left=True, right=True):
    """تطبيق حدود مخصصة للخلية لاستبعاد حدود العمود الفاصل."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    
    borders = {'top': top, 'bottom': bottom, 'left': left, 'right': right}
    for border_name, is_visible in borders.items():
        node = OxmlElement(f'w:{border_name}')
        if is_visible:
            node.set(qn('w:val'), 'single')
            node.set(qn('w:sz'), '4')
            node.set(qn('w:space'), '0')
            node.set(qn('w:color'), 'auto')
        else:
            node.set(qn('w:val'), 'none')
        tcBorders.append(node)
    tcPr.append(tcBorders)


def _set_table_grid(table, col_widths):
    """تحديد شبكة الأعمدة الهيكلية (tblGrid) لفرض العرض بدقة."""
    tblPr = table._tbl.tblPr
    for child in list(table._tbl):
        if child.tag.endswith('tblGrid'):
            table._tbl.remove(child)
            
    tblGrid = OxmlElement('w:tblGrid')
    for w in col_widths:
        gridCol = OxmlElement('w:gridCol')
        gridCol.set(qn('w:w'), str(int(w.twips)))
        tblGrid.append(gridCol)
    tblPr.addnext(tblGrid)


# ---------------------------------------------------------------- بناء صفحة خطة الدرس
CONTENT_WIDTH = Cm(25.0)


def _add_plan_page(doc, first_page, header, plan):
    section = doc.sections[0] if first_page else doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    if section.page_width < section.page_height:
        section.page_width, section.page_height = section.page_height, section.page_width
    
    section.top_margin = section.bottom_margin = Cm(0.8)
    section.left_margin = section.right_margin = Cm(2.35)
    _rtl_section(section)

    # إضافة رمز النموذج في التذييل الرسمي للصفحة (Footer) ومحاذاته لأقصى اليمين
    footer = section.footer
    footer_p = footer.paragraphs[0]
    footer_p.paragraph_format.space_before = Pt(0)
    footer_p.paragraph_format.space_after = Pt(0)
    _run(_rtl_p(footer_p, WD_ALIGN_PARAGRAPH.RIGHT), "FORM #QF71-1-47 rev.b", 9, False)

    _center(doc, "خطة الدرس", 15, True)

    # 1. الترويسة في جدول واحد من 5 أعمدة (تم رفع حجم الخط إلى 13)
    top_header = _doc_table(doc, 1, 5, [Cm(2.5), Cm(6.0), Cm(5.0), Cm(6.0), Cm(5.5)])
    row_cells = top_header.rows[0].cells
    
    header_items = [
        f"عدد الحصص: {header['periods']}",
        f"التعلم القبلي: {plan['prior_learning']}",
        f"موضوع الدرس: {header['lesson']}",
        f"عنوان الوحدة: {header['unit']}",
        f"المبحث: {header['subject']}"
    ]

    for i, item in enumerate(header_items):
        align = WD_ALIGN_PARAGRAPH.LEFT if i == 0 else (WD_ALIGN_PARAGRAPH.RIGHT if i == 4 else WD_ALIGN_PARAGRAPH.CENTER)
        p = row_cells[i].paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        _run(_rtl_p(p, align), item, 13, True if i in (2, 3, 4) else False)

    # 2. جدول النتاجات التعليمية (حجم الخط 13)
    out_t = _doc_table(doc, 2, 1, [CONTENT_WIDTH], borders=True)
    _set_row_height(out_t.rows[0], Cm(0.5))
    _set_row_height(out_t.rows[1], Cm(1.3))
    
    p_title = out_t.rows[0].cells[0].paragraphs[0]
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(0)
    _run(_rtl_p(p_title), "النتاجات التعليمية:", 13.5, True)
    oc = out_t.rows[1].cells[0]
    for i, item in enumerate(plan["outcomes"]):
        p = oc.paragraphs[0] if i == 0 else oc.add_paragraph()
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        _run(_rtl_p(p), f"- {item}", 13)

    # 3. جدول المراحل ودور المعلم والمتعلم والزمن (حجم الخط 13 في كل الخلايا)
    main = _doc_table(doc, 5, 4, [Cm(1.8), Cm(10.6), Cm(10.6), Cm(2.0)], borders=True)
    head = main.rows[0].cells
    for cell, val in zip(head, ["الزمن", "دور المُتعلم", "دور المُعلم", "المراحل"]):
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.CENTER), val, 13, True)

    for i, (stage_label, stage) in enumerate(zip(STAGES, plan["stages"]), start=1):
        row = main.rows[i]
        _set_row_height(row, Cm(1.1))
        
        cells = row.cells
        cells[0].paragraphs[0].text = ""
        
        p1 = cells[1].paragraphs[0]
        p1.paragraph_format.space_before = Pt(0)
        p1.paragraph_format.space_after = Pt(0)
        _run(_rtl_p(p1, WD_ALIGN_PARAGRAPH.RIGHT), stage["student_role"], 13)
        
        p2 = cells[2].paragraphs[0]
        p2.paragraph_format.space_before = Pt(0)
        p2.paragraph_format.space_after = Pt(0)
        _run(_rtl_p(p2, WD_ALIGN_PARAGRAPH.RIGHT), stage["teacher_role"], 13)
        
        p3 = cells[3].paragraphs[0]
        p3.paragraph_format.space_before = Pt(0)
        p3.paragraph_format.space_after = Pt(0)
        _run(_rtl_p(p3, WD_ALIGN_PARAGRAPH.CENTER), stage_label, 13, True)
        _vertical_cell(cells[3])

    # فاصل طفيف
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(2)
    spacer.paragraph_format.space_after = Pt(2)

    # 4. الجزء السفلي: خلية التأمل الذاتي والجدول الإداري (حجم الخط 13)
    col_widths = [Cm(1.0)] * 7 + [Cm(3.5), Cm(0.5), Cm(14.0)]
    
    bottom_grid = doc.add_table(rows=4, cols=10)
    bottom_grid.autofit = False
    _rtl_table(bottom_grid)
    _set_table_grid(bottom_grid, col_widths)

    for row in bottom_grid.rows:
        _set_row_height(row, Cm(0.65))
        for cell, w in zip(row.cells, col_widths):
            cell.width = w

    # إعداد الحدود
    for row in bottom_grid.rows:
        for c_idx, cell in enumerate(row.cells):
            if c_idx == 8:  # الفاصل الشفاف
                _set_cell_borders(cell, top=False, bottom=False, left=False, right=False)
            else:
                _set_cell_borders(cell, top=True, bottom=True, left=True, right=True)

    # عناوين الجدول الإداري
    admin_labels = [
        "الصف/الشعبة",
        "عدد الغياب/العدد الكلي",
        "ترتيب الحصة",
        "اليوم والتاريخ"
    ]
    for i, label in enumerate(admin_labels):
        p = bottom_grid.rows[i].cells[7].paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.CENTER), label, 12, True)

    # خلية التأمل الذاتي (حجم الخط 13)
    reflect_cell = bottom_grid.rows[0].cells[9]
    for r_idx in range(1, 4):
        reflect_cell = reflect_cell.merge(bottom_grid.rows[r_idx].cells[9])
    
    _set_cell_borders(reflect_cell, top=True, bottom=True, left=True, right=True)
    
    rp = reflect_cell.paragraphs[0]
    rp.paragraph_format.space_before = Pt(0)
    rp.paragraph_format.space_after = Pt(0)
    _run(_rtl_p(rp, WD_ALIGN_PARAGRAPH.RIGHT), "*التأمل الذاتي : حول عمليتي التعلم والتعليم", 13, True)

    # 5. سطر فارغ فوق سطر التواقيع ليفصله بوضوح عن الجداول
    empty_p = doc.add_paragraph()
    empty_p.paragraph_format.space_before = Pt(8)
    empty_p.paragraph_format.space_after = Pt(0)
    empty_p1 = doc.add_paragraph()
    empty_p1.paragraph_format.space_before = Pt(8)
    empty_p1.paragraph_format.space_after = Pt(0)


    # 6. سطر التواقيع والأسماء (حجم الخط 13)
    sig = _doc_table(doc, 1, 4, [Cm(5.5), Cm(5.5), Cm(6.0), Cm(8.0)])
    _no_borders(sig)
    sig_vals = [
        "مستشار التطوير المدرسي:",
        "مدير المدرسة:",
        "اختصاصي المبحث:",
        f"الاسم والتوقيع: المعلم: {header['teacher']}" if header["teacher"] else "الاسم والتوقيع: المعلم:"
    ]
    for cell, val in zip(sig.rows[0].cells, sig_vals):
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.RIGHT), val, 13)


def build_docx(header, plans, lang="ar"):
    """header: بيانات عامة (subject, teacher). plans: [(بيانات الدرس، محتوى الخطة)]."""
    if lang == "en":
        return en.build_lesson_plan_docx(header, plans)
    doc = Document()
    for i, (lesson_header, plan) in enumerate(plans):
        _add_plan_page(doc, i == 0, {**header, **lesson_header}, plan)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- الواجهة
def render_lesson_plan_builder(idx, slug, subject, flat_lessons, user=None, ctx=None, lang="ar"):
    st.subheader("خطة الدرس" if lang != "en" else "خطة الدرس (Lesson Plan — English, LTR)")
    if not flat_lessons:
        st.info("لم تُدخل دروس هذا الكتاب بعد.")
        return
    ctx = ctx or {}
    if lang == "en":
        st.caption("🇬🇧 هذا كتاب لغة إنجليزية: ستُنتَج الخطة بالإنجليزية واتجاه الصفحة من اليسار إلى اليمين.")

    # الحساب التجريبي: عدد محدود من الدروس طوال عمر الحساب
    remaining = acc.trial_remaining(user, "lesson_plan") if user is not None else None
    if remaining is not None:
        st.info(f"🧪 حساب تجريبي: يمكنك إنشاء خطة لعدد {remaining} درس/دروس فقط ضمن حصتك المتبقية.")

    labels = [l["label"] for l in flat_lessons]
    sel_labels = st.multiselect("اختر درسًا أو أكثر (لكل درس صفحة مستقلة)", labels, default=labels[:1],
                                max_selections=remaining)
    lessons = [l for l in flat_lessons if l["label"] in sel_labels]

    periods = st.number_input("عدد الحصص لكل درس", min_value=1, value=1, step=1)
    # اسم المعلم معروف من حسابه؛ لا يُسأل عنه إلا إن كان فارغًا
    teacher = profile_ctx.known_input("اسم المعلم (يظهر في التوقيع)", ctx.get("teacher"), "lp_teacher")
    profile_ctx.known_summary([("المعلم", ctx.get("teacher")), ("المبحث", subject)])

    if st.button("🗒️ إنشاء خطة الدرس", type="primary", disabled=not lessons):
        plans = []
        with st.spinner("جارٍ إعداد الخطة..."):
            for lesson in lessons:
                data, from_cache = get_or_generate_plan(idx, slug, lesson, user=user, lang=lang)
                if not data:
                    st.error(f"تعذّر إعداد خطة الدرس «{lesson['title']}». حاول مرة أخرى.")
                    continue
                lesson_header = {"unit": lesson.get("unit_title", ""), "lesson": lesson["title"],
                                 "periods": periods}
                plans.append(({**lesson_header}, data))
                if from_cache:
                    st.caption(f"✓ استُرجعت خطة «{lesson['title']}» من خطط محفوظة سابقًا (دون طلب جديد).")
        if plans:
            if user is not None:
                acc.trial_consume(user, "lesson_plan", len(plans))
            data = build_docx({"subject": subject, "teacher": teacher.strip()}, plans, lang)
            st.download_button("⬇️ تنزيل خطة الدرس", data=data, file_name=f"خطة_درس_{subject}.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
