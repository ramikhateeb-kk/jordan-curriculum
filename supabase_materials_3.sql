-- supabase_materials_3.sql: فهرس نصوص وتضمينات البحث الدلالي لكتاب الأنشطة
CREATE TABLE IF NOT EXISTS jordan_activity_exercises (
    id SERIAL PRIMARY KEY,
    unit_id INTEGER REFERENCES jordan_units(id),
    page_number INTEGER NOT NULL,
    exercise_number TEXT NOT NULL,
    title TEXT,
    prompt TEXT NOT NULL,
    solution TEXT NOT NULL,
    direction TEXT DEFAULT 'rtl'
);
