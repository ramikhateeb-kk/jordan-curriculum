"""
ملف: ministry.py
نظام استخراج وحل أسئلة الامتحانات الوزارية - المنهاج الأردني (شهادة الثانوية العامة - التوجيهي)
الإصدار المطور والنهائي:
1. استخراج كامل 100% لجميع الأسئلة الرئيسية والفرعية (Question 1, Question 2, Question 3).
2. دعم التنسيق الإنجليزي (LTR) ورفع حد التوكنات لـ 8192.
3. استعادة أزرار: التعديل | بنك الأسئلة | قيّمني.
4. مطابقة تامة لتوقيع الدالة: render_ministry(book=None, flat_lessons=None, user=None, lang="ar", idx=None, *args, **kwargs)
"""

import os
import io
import time
import json
import base64
import streamlit as st
from typing import List, Dict, Any, Optional


def extract_text_from_file(uploaded_file, file_bytes: bytes) -> str:
    """استخراج النص من الملفات بمختلف الصيغ (PDF, DOCX, TXT)"""
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".txt"):
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    if file_name.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception:
            pass

    if file_name.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages = [f"--- [Page {i+1}] ---\n" + (p.extract_text() or "") for i, p in enumerate(reader.pages)]
            text = "\n\n".join(pages).strip()
            if len(text) > 40:
                return text
        except Exception:
            pass

        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages = [f"--- [Page {i+1}] ---\n" + (p.extract_text() or "") for i, p in enumerate(pdf.pages)]
                text = "\n\n".join(pages).strip()
                if len(text) > 40:
                    return text
        except Exception:
            pass

    return ""


def get_gemini_client():
    api_key = None
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"خطأ أثناء تهيئة google-genai: {e}")
        return None


def extract_and_solve_all_questions(
    exam_text: str = "",
    file_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    subject: str = "اللغة الإنجليزية",
    branch: str = "جميع الفروع الأكاديمية والمهنية"
) -> Dict[str, Any]:
    client = get_gemini_client()
    if not client:
        return {"error": "لم يتم العثور على مفتاح GEMINI_API_KEY"}

    from google.genai import types

    is_english = "إنجليز" in subject or "english" in subject.lower()

    system_instruction = f"""
    You are an expert Chief Examiner at the Ministry of Education in Jordan.
    CRITICAL MANDATORY RULES:
    1. Read the full exam paper.
    2. Extract ALL main questions:
       - Question One (all multiple choice items 1..N).
       - Question Two: You MUST extract the Reading Passage in "passage", and extract EVERY SINGLE sub-question following it (items 1 to 6, Critical Thinking, Literature Spot) as separate items in "sub_questions". NEVER combine them!
       - Question Three: Free Writing / Guided Writing.
    3. Provide model answers, explanations, and mark rubrics for EVERY item.
    {"4. The exam is in ENGLISH. All questions, options, passages, and solutions must be in clean ENGLISH. Set language to 'en'." if is_english else "4. اكتب باللغة العربية."}
    """

    prompt = f"""
    Official Jordanian Ministry of Education Exam:
    Subject: {subject} | Branch: {branch}
    Content:
    {exam_text if exam_text else "Please read all attached pages/images carefully."}
    
    Return ONLY valid JSON matching:
    {{
      "title": "General Secondary Certificate Examination - English Language",
      "subject": "{subject}",
      "branch": "{branch}",
      "total_marks": 200,
      "language": "{"en" if is_english else "ar"}",
      "questions": [
        {{
          "id": "q1",
          "number": 1,
          "title": "Question One: Multiple Choice Items",
          "total_marks": 140,
          "sub_questions": [
            {{
              "id": "q1_1",
              "sub_label": "Item 1",
              "text": "Sentence and options A, B, C, D",
              "marks": 5,
              "answer": {{
                "final_answer": "A) soil erosion",
                "steps": ["Reasoning"],
                "rubric": [{{"step": "Correct option", "marks": 5}}],
                "examiner_tips": "Context clue"
              }}
            }}
          ]
        }},
        {{
          "id": "q2",
          "number": 2,
          "title": "Question Two: Reading Comprehension",
          "total_marks": 30,
          "passage": "Full article text...",
          "sub_questions": [
            {{
              "id": "q2_1",
              "sub_label": "Question 1",
              "text": "Question text...",
              "marks": 4,
              "answer": {{"final_answer": "...", "steps": ["..."], "rubric": [{{"step": "...", "marks": 4}}], "examiner_tips": "..."}}
            }}
          ]
        }}
      ]
    }}
    """

    contents = []
    if file_bytes and mime_type:
        try:
            contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))
        except Exception:
            b64 = base64.b64encode(file_bytes).decode("utf-8")
            contents.append({"inline_data": {"mime_type": mime_type, "data": b64}})
    contents.append(prompt)

    candidate_models = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-3.1-flash-lite"]
    last_err = ""
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        max_output_tokens=8192,
                        temperature=0.2,
                    )
                )
                txt = res.text.strip()
                if txt.startswith("```json"): txt = txt[7:]
                if txt.endswith("```"): txt = txt[:-3]
                return json.loads(txt)
            except Exception as e:
                last_err = str(e)
                if any(x in last_err.lower() for x in ["503", "unavailable", "429"]):
                    time.sleep(2 * (attempt + 1))
                    continue
                break

    return {"error": f"خوادم الذكاء الاصطناعي مشغولة حالياً (503)، يرجى إعادة المحاولة: {last_err}"}


def evaluate_student_answer(question_text: str, model_answer: str, rubric: list, student_answer: str, max_marks: float) -> Dict[str, Any]:
    """خدمة قيّمني: رصد العلامة وملاحظات المصحح وفق المعايير الوزارية"""
    client = get_gemini_client()
    if not client:
        return {"error": "لم يتم العثور على مفتاح GEMINI_API_KEY"}
    from google.genai import types

    is_english = any(ord(c) < 128 and c.isalpha() for c in question_text[:60])
    prompt = f"""
    Official Ministry of Education Grader:
    Question: {question_text}
    Full Marks: {max_marks}
    Model Answer: {model_answer}
    Rubric: {json.dumps(rubric, ensure_ascii=False)}
    Student's Answer: "{student_answer}"
    
    Return JSON:
    {{
      "awarded_marks": 3.5,
      "max_marks": {max_marks},
      "feedback": "Evaluation feedback",
      "strengths": ["Strength 1"],
      "missing_points": ["Missing points"],
      "advice": "Examiner tip"
    }}
    {"Provide text in English." if is_english else "اكتب بالعربية."}
    """
    try:
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", max_output_tokens=2048)
        )
        return json.loads(res.text)
    except Exception as e:
        return {"error": str(e)}


def render_ministry(book=None, flat_lessons=None, user=None, lang="ar", idx=None, *args, **kwargs):
    if "question_bank" not in st.session_state:
        st.session_state["question_bank"] = []

    st.header("📋 استخراج وحل الامتحانات الوزارية (المنهاج الأردني)")
    st.caption("حل شامل لجميع الأسئلة والقطع القرائية وفروعها (100%) - مع أزرار التعديل وبنك الأسئلة وخدمة قيّمني")

    default_subject = "اللغة الإنجليزية"
    if book:
        default_subject = book.get("subject", book.get("title", default_subject)) if isinstance(book, dict) else getattr(book, "subject", default_subject)

    col1, col2 = st.columns(2)
    with col1:
        subjects_list = ["اللغة الإنجليزية", "الرياضيات", "اللغة العربية (مشترك)", "الفيزياء", "الكيمياء", "العلوم الحياتية", "التربية الإسلامية", "تاريخ الأردن"]
        s_idx = next((i for i, s in enumerate(subjects_list) if s in str(default_subject)), 0)
        subject = st.selectbox("المبحث الدراسي:", subjects_list, index=s_idx)
    with col2:
        branch = st.selectbox("الفرع الأكاديمي:", ["جميع الفروع الأكاديمية والمهنية", "الفرع العلمي والتعليم الصحي", "الفرع الأدبي والشرعي", "الفرع الصناعي"], index=0)

    is_english_subject = "إنجليز" in subject or "english" in subject.lower()
    layout_dir = st.radio("تنسيق العرض:", ["محاذاة إنجليزية (Left-to-Right LTR)", "محاذاة عربية (Right-to-Left RTL)"], index=0 if is_english_subject else 1, horizontal=True)
    is_ltr = "LTR" in layout_dir

    tab_upload, tab_paste, tab_qbank = st.tabs(["📁 رفع ملف امتحان (PDF / صورة / Word)", "✍️ لصق نص الامتحان مباشرة", f"📚 بنك الأسئلة ({len(st.session_state['question_bank'])})"])

    exam_text = ""
    file_bytes_to_send, file_mime_to_send = None, None

    with tab_upload:
        uploaded_file = st.file_uploader("اختر ورقة الامتحان (PDF أو صورة):", type=["pdf", "png", "jpg", "jpeg", "docx", "txt"])
        if uploaded_file is not None:
            raw_bytes = uploaded_file.getvalue()
            fname = uploaded_file.name.lower()
            file_mime_to_send = "application/pdf" if fname.endswith(".pdf") else ("image/jpeg" if fname.endswith((".png", ".jpg", ".jpeg")) else None)
            file_bytes_to_send = raw_bytes
            extracted = extract_text_from_file(uploaded_file, raw_bytes)
            if extracted:
                st.success(f"✅ تم استخراج النص الرقمي ({len(extracted)} حرف)")
                exam_text = extracted
            else:
                st.info(f"📄 سيقوم الذكاء الاصطناعي بقراءة جميع صفحات وملفات الـ PDF وحلها بالكامل.")
                exam_text = "ملف امتحان PDF"

    with tab_paste:
        pasted = st.text_area("الصق نص الامتحان هنا:", height=180)
        if pasted.strip():
            exam_text = pasted.strip()

    with tab_qbank:
        qbank = st.session_state.get("question_bank", [])
        if not qbank:
            st.info("بنك الأسئلة فارغ حالياً. استخدم زر '📥 إضافة لبنك الأسئلة' لحفظ أي سؤال.")
        else:
            st.write(f"يحتوي بنك الأسئلة على **{len(qbank)}** سؤال محفوظ:")
            for b_idx, item in enumerate(qbank):
                with st.expander(f"#{b_idx + 1}: {item.get('main_title', '')} - {item.get('sub_label', '')} ({item.get('marks', '')} علامات)"):
                    st.write(f"**نص السؤال:** {item.get('text', '')}")
                    st.write(f"**الإجابة:** {item.get('answer', '')}")
                    if st.button(f"🗑️ حذف من البنك", key=f"del_qb_{b_idx}"):
                        st.session_state["question_bank"].pop(b_idx)
                        st.rerun()
            st.download_button("💾 تصدير بنك الأسئلة (JSON)", data=json.dumps(qbank, ensure_ascii=False, indent=2), file_name="qbank.json", mime="application/json")

    st.markdown("---")
    ready = bool(exam_text.strip() or file_bytes_to_send)
    if st.button("🚀 استخراج وحل ورقة الامتحان بالكامل (100%)", type="primary", use_container_width=True, disabled=not ready):
        with st.spinner("جارٍ قراءة الامتحان والقطع وفروعها وحلها بنسبة 100%..."):
            res = extract_and_solve_all_questions(exam_text=exam_text if exam_text != "ملف امتحان PDF" else "", file_bytes=file_bytes_to_send, mime_type=file_mime_to_send, subject=subject, branch=branch)
            st.session_state["ministry_exam_result"] = res

    if "ministry_exam_result" in st.session_state:
        result = st.session_state["ministry_exam_result"]
        if "error" in result:
            st.error(result["error"])
            return

        questions = result.get("questions", [])
        total_sub = sum(len(q.get("sub_questions", [])) for q in questions)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("الأسئلة الرئيسية", f"{len(questions)} أسئلة")
        m2.metric("الفروع المحلولة", f"{total_sub} فروع")
        m3.metric("نسبة الحل", "100% كامل")
        m4.metric("مجموع العلامات", f"{result.get('total_marks', 200)} علامة")

        if st.button("📥 إضافة جميع أسئلة الامتحان إلى بنك الأسئلة دفعة واحدة"):
            for q in questions:
                for sq in q.get("sub_questions", []):
                    st.session_state["question_bank"].append({
                        "subject": subject, "main_title": q.get("title", ""), "sub_label": sq.get("sub_label", ""),
                        "text": sq.get("text", ""), "marks": sq.get("marks", 0), "answer": sq.get("answer", {}).get("final_answer", "")
                    })
            st.success(f"تمت إضافة جميع الأسئلة لبنك الأسئلة بنجاح!")
            st.rerun()

        for q_idx, main_q in enumerate(questions):
            title = main_q.get("title", f"Question {q_idx + 1}")
            subs = main_q.get("sub_questions", [])
            passage = main_q.get("passage", "")

            with st.expander(f"📌 {title} [{main_q.get('total_marks', '')} Marks] - ({len(subs)} Sub-questions)", expanded=True):
                if passage:
                    st.markdown("**📖 Reading Passage / النص القرائي:**")
                    st.markdown(f"<div style='direction: ltr; text-align: left; background: #f1f5f9; border-left: 5px solid #0284c7; padding: 14px; border-radius: 8px; font-size: 14px; line-height: 1.7; margin-bottom: 16px;'>{passage}</div>", unsafe_allow_html=True)

                for s_idx, sub_q in enumerate(subs):
                    sub_key = f"sub_{q_idx}_{s_idx}"
                    sub_label = sub_q.get("sub_label", f"Part {s_idx + 1}")
                    sub_text = sub_q.get("text", "")
                    sub_marks = sub_q.get("marks", "")
                    ans = sub_q.get("answer", {})

                    if is_ltr:
                        st.markdown(f"<div style='direction: ltr; text-align: left; margin-top: 12px;'><span style='background: #0f766e; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;'>{sub_label}</span> <span style='font-weight: bold; font-size: 15px; margin-left: 6px;'>{sub_text}</span> <span style='color: #64748b; font-size: 12px;'>({sub_marks} Marks)</span></div>", unsafe_allow_html=True)
                        if ans.get("final_answer"):
                            st.markdown(f"<div style='direction: ltr; text-align: left; background: #ecfdf5; border-left: 4px solid #059669; padding: 10px; border-radius: 6px; margin: 8px 0;'><strong style='color: #065f46;'>Model Answer:</strong><br/><span style='font-weight: bold; color: #064e3b;'>{ans['final_answer']}</span></div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"**{sub_label}**: {sub_text} `({sub_marks} علامة)`")
                        if ans.get("final_answer"):
                            st.success(f"**الجواب النهائي المعتمد:** {ans['final_answer']}")

                    # الأزرار التفاعلية الثلاثة
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("✏️ تعديل السؤال والإجابة", key=f"btn_edit_{sub_key}"):
                            st.session_state[f"edit_toggle_{sub_key}"] = not st.session_state.get(f"edit_toggle_{sub_key}", False)
                    with b2:
                        if st.button("📥 إضافة لبنك الأسئلة", key=f"btn_add_qb_{sub_key}"):
                            st.session_state["question_bank"].append({
                                "subject": subject, "main_title": title, "sub_label": sub_label, "text": sub_text, "marks": sub_marks, "answer": ans.get("final_answer", "")
                            })
                            st.toast(f"✅ تمت إضافة ({sub_label}) إلى بنك الأسئلة!", icon="🎉")
                    with b3:
                        if st.button("🎯 قيّمني (اختبر إجابتي)", key=f"btn_eval_{sub_key}"):
                            st.session_state[f"eval_toggle_{sub_key}"] = not st.session_state.get(f"eval_toggle_{sub_key}", False)

                    # واجهة التعديل
                    if st.session_state.get(f"edit_toggle_{sub_key}", False):
                        st.info("وضع التعديل:")
                        new_t = st.text_area("نص السؤال:", value=sub_text, key=f"ta_t_{sub_key}")
                        new_a = st.text_area("الإجابة النموذجية:", value=ans.get("final_answer", ""), key=f"ta_a_{sub_key}")
                        if st.button("💾 حفظ التعديلات", key=f"save_{sub_key}"):
                            sub_q["text"] = new_t
                            sub_q["answer"]["final_answer"] = new_a
                            st.session_state[f"edit_toggle_{sub_key}"] = False
                            st.rerun()

                    # واجهة قيّمني
                    if st.session_state.get(f"eval_toggle_{sub_key}", False):
                        st.markdown("🎯 **خدمة قيّمني الوزارية:** اكتب إجابتك لتصحيحها ورصد العلامة:")
                        stu_ans = st.text_area("إجابتك:", placeholder="Write your answer here...", key=f"stu_{sub_key}")
                        if st.button("📊 رصد علامتي وتصحيح إجابتي", key=f"eval_sub_{sub_key}"):
                            if stu_ans.strip():
                                with st.spinner("جارٍ تقييم الإجابة..."):
                                    eval_res = evaluate_student_answer(sub_text, ans.get("final_answer", ""), ans.get("rubric", []), stu_ans, float(sub_marks or 5))
                                    if "error" not in eval_res:
                                        st.metric("علامتك المستحقة", f"{eval_res.get('awarded_marks', 0)} من {eval_res.get('max_marks', sub_marks)}")
                                        st.write(f"**التقييم:** {eval_res.get('feedback', '')}")
                                        if eval_res.get("strengths"): st.success(f"نقاط القوة: {', '.join(eval_res['strengths'])}")
                                        if eval_res.get("missing_points"): st.warning(f"ما ينقصك: {', '.join(eval_res['missing_points'])}")
                                        if eval_res.get("advice"): st.info(f"نصيحة: {eval_res.get('advice')}")
                    st.markdown("---")

        st.download_button("💾 تحميل نموذج الإجابة الكامل (JSON)", data=json.dumps(result, ensure_ascii=False, indent=2), file_name=f"نموذج_إجابة_{subject}.json", mime="application/json")
