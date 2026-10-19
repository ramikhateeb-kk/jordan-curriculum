-- supabase_materials.sql: جداول المواد والكتب المدرسية الأردنية
CREATE TABLE IF NOT EXISTS jordan_grades (
    id TEXT PRIMARY KEY,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    stage TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jordan_subjects (
    id TEXT PRIMARY KEY,
    grade_id TEXT REFERENCES jordan_grades(id),
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    is_english BOOLEAN DEFAULT FALSE,
    has_activity_book BOOLEAN DEFAULT TRUE
);
