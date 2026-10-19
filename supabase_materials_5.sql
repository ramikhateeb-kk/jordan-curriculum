-- supabase_materials_5.sql: قواعد التحقق المنهجي لمنع الأسئلة الخارجة عن المنهاج
CREATE TABLE IF NOT EXISTS jordan_curriculum_scope_rules (
    id SERIAL PRIMARY KEY,
    subject_id TEXT NOT NULL,
    banned_keywords TEXT[] NOT NULL,
    guidance_message TEXT NOT NULL,
    redirect_subject_id TEXT
);
