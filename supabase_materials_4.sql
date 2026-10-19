-- supabase_materials_4.sql: بنك الأسئلة ومفاتيح الحلول الرسمية
CREATE TABLE IF NOT EXISTS jordan_question_bank (
    id SERIAL PRIMARY KEY,
    subject_id TEXT REFERENCES jordan_subjects(id),
    grade_id TEXT REFERENCES jordan_grades(id),
    page_number INTEGER,
    question_number TEXT,
    question_text TEXT NOT NULL,
    model_answer TEXT NOT NULL,
    detailed_explanation TEXT,
    is_english BOOLEAN DEFAULT FALSE
);
