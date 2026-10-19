-- supabase_materials_2.sql: الوحدات والدروس لكتب المنهاج الأردني
CREATE TABLE IF NOT EXISTS jordan_units (
    id SERIAL PRIMARY KEY,
    subject_id TEXT REFERENCES jordan_subjects(id),
    unit_number INTEGER NOT NULL,
    title_ar TEXT NOT NULL,
    title_en TEXT,
    student_book_pages TEXT,
    activity_book_pages TEXT
);
