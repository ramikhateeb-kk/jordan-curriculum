"""
ملف: ministry.py (النسخة المصححة والمطورة لنظام المنهاج الأردني)
الإصلاح: ضمان حل واستخراج كافة الأسئلة الرئيسية وكافة الأسئلة الفرعية دون استثناء
مع سلم توزيع العلامات الوزاري المعتمد لوزارة التربية والتعليم الأردنية.
"""

import json
import os
from typing import List, Dict, Any
from google import genai
from google.genai import types

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("يرجى ضبط مفتاح GEMINI_API_KEY في متغيرات البيئة")
    return genai.Client(api_key=api_key)

def extract_and_solve_ministerial_exam(exam_text: str, subject: str = "الرياضيات", branch: str = "العلمي") -> Dict[str, Any]:
    """
    يقوم باستخراج جميع الأسئلة الرئيسية والفرعية، ويولد الإجابة النموذجية
    لكل فرع من كل سؤال رئيسي بالتفصيل مع سلم العلامات.
    """
    client = get_gemini_client()

    system_instruction = """
    أنت خبير المناهج ورئيس لجان تصحيح الامتحانات الوزارية في وزارة التربية والتعليم الأردنية (شهادة التوجيهي).
    قاعدة حاسمة وإلزامية:
    1. استخرج كل الأسئلة الرئيسية الواردة في الامتحان (السؤال الأول، الثاني، الثالث...).
    2. لكل سؤال رئيسي، استخرج كافة الفروع (أ، ب، ج، د...) أو الفقرات (1، 2، 3...).
    3. أجب عن كل فرع من كل سؤال رئيسي بلا استثناء بحل نموذجي وزاري مفصل مع خطوات الحل وتوزيع العلامات.
    تحذير: إياك أن تتوقف عند الفرع الأول أو السؤال الأول فقط! يجب أن يتضمن الناتج إجابات شاملة لكافة الفروع لجميع الأسئلة.
    """

    prompt = f"""
    المبحث: {subject}
    الفرع: {branch}
    
    نص ورقة الامتحان الوزاري:
    {exam_text}
    
    المطلوب استخراجه وتحليله بتنسيق JSON:
    - عنوان الامتحان ومجموع العلامات.
    - قائمة questions: كل عنصر يمثل سؤالاً رئيسياً (id, number, title, total_marks).
    - داخل كل سؤال رئيسي، قائمة sub_questions: كل عنصر يمثل فرعاً (id, sub_label, text, marks, answer).
    - داخل answer لكل فرع: final_answer, steps (قائمة الخطوات), rubric (قائمة توزيع العلامات), examiner_notes.
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json"
        )
    )

    try:
        exam_data = json.loads(response.text)
        return exam_data
    except Exception as e:
        print(f"خطأ في معالجة JSON: {e}")
        return {"error": str(e), "raw_text": response.text}

def solve_sub_questions_iterative(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    دالة لحل الفروع واحداً تلو الآخر في حال كانت معالجة الأسئلة تتم عبر حلقات تكرارية (Iterative Loop).
    هنا كان الخطأ السابق بوجود return داخل الحلقة الأولى!
    هذا هو الحل المضمون 100%:
    """
    client = get_gemini_client()
    solved_questions = []

    # 1. التكرار عبر كل سؤال رئيسي
    for q_idx, main_q in enumerate(questions):
        print(f"جارٍ معالجة السؤال الرئيسي {q_idx + 1}: {main_q.get('title')}")
        solved_subs = []
        
        # 2. التكرار عبر كافة الفروع للسؤال الرئيسي
        sub_list = main_q.get('sub_questions', [])
        for s_idx, sub_q in enumerate(sub_list):
            print(f"  -> جارٍ حل الفرع {s_idx + 1}: {sub_q.get('sub_label')}")
            
            # توليد الإجابة للفرع
            sub_prompt = f"""
            أجب إجابة نموذجية وزارية معتمدة على هذا السؤال الفرعي:
            السؤال الرئيسي: {main_q.get('title')}
            الفرع: {sub_q.get('sub_label')}
            نص الفرع: {sub_q.get('text')}
            العلامة: {sub_q.get('marks')}
            المطلوب:
            1. الجواب النهائي
            2. خطوات الحل التفصيلية
            3. سلم توزيع العلامات لكل خطوة
            """
            
            res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=sub_prompt
            )
            
            # تخزين الإجابة في الفرع نفسه
            sub_q_copy = dict(sub_q)
            sub_q_copy['model_answer'] = res.text
            solved_subs.append(sub_q_copy)
            # انتبه: لا نضع return هنا أبداً!
        
        main_q_copy = dict(main_q)
        main_q_copy['sub_questions'] = solved_subs
        solved_questions.append(main_q_copy)
        # انتبه: ولا نضع return هنا أيضاً!

    # الإرجاع فقط بعد الانتهاء من جميع الأسئلة وجميع الفروع بالكامل:
    return solved_questions
