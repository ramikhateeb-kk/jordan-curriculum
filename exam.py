"""
exam.py - إعداد وتوليد الامتحانات المدرسية والوزارية وجداول المواصفات
"""

from typing import Dict, List

def generate_exam_paper(grade: str, subject: str, term: str = "النهائي", max_score: int = 40) -> Dict:
    """
    إنشاء نموذج امتحان مدرسي متوافق مع معايير وزارة التربية والتعليم
    """
    is_eng = "english" in subject.lower() or "action pack" in subject.lower()
    
    if is_eng:
        return {
            "title": f"The Hashemite Kingdom of Jordan - Ministry of Education\n{grade} - English Language (Action Pack) - {term} Exam",
            "direction": "ltr",
            "time_allowed": "One Hour and a Half",
            "total_marks": max_score,
            "sections": [
                {
                    "title": "Section One: Reading Comprehension (12 Marks)",
                    "text": "Read the text carefully and answer the questions below...",
                    "questions": [
                        "1. What is the main idea of the first paragraph? (3 Marks)",
                        "2. Find a word in the text which means 'historic monument'. (2 Marks)",
                        "3. Quote the sentence showing the importance of tourism. (3 Marks)"
                    ]
                },
                {
                    "title": "Section Two: Structure and Grammar (14 Marks)",
                    "questions": [
                        "Complete with the correct form of the verbs in brackets:",
                        "1. She (study) _______ English when the phone rang.",
                        "2. If they hurry, they (catch) _______ the morning bus."
                    ]
                },
                {
                    "title": "Section Three: Vocabulary & Writing (14 Marks)",
                    "questions": [
                        "Write a short paragraph of 50-60 words about your favourite historical site in Jordan."
                    ]
                }
            ]
        }
    else:
        return {
            "title": f"المملكة الأردنية الهاشمية - وزارة التربية والتعليم\nامتحان مادة {subject} - {grade} - {term}",
            "direction": "rtl",
            "time_allowed": "ساعة ونصف",
            "total_marks": max_score,
            "sections": [
                {
                    "title": "السؤال الأول: اختر رمز الإجابة الصحيحة (10 علامات)",
                    "questions": [
                        "1. المفهوم الأساسي الوارد في الوحدة يشير إلى: (أ) الخيار الأول (ب) الخيار الثاني",
                        "2. من أبرز الإنجازات الوطنية في تلك الفترة: (أ) الإنجاز أ (ب) الإنجاز ب"
                    ]
                },
                {
                    "title": "السؤال الثاني: أجب عن الأسئلة المقالية التالية (15 علامة)",
                    "questions": [
                        "علل ما يلي تعليلاً علمياً / تاريخياً دقيقاً وفق المنهاج المقرر.",
                        "قارن بين المفاهيم في جدول موضحاً وجه الشبه والاختلاف."
                    ]
                },
                {
                    "title": "السؤال الثالث: حل المسألة / التطبيق العملي (15 علامة)",
                    "questions": [
                        "احسب المطلوب مع بيان خطوات الحل والقوانين المستخدمة بالتفصيل."
                    ]
                }
            ]
        }
