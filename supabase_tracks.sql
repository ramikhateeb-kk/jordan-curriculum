-- supabase_tracks.sql: مسارات الثانوية العامة والتوجيهي في الأردن
CREATE TABLE IF NOT EXISTS jordan_academic_tracks (
    id TEXT PRIMARY KEY,
    name_ar TEXT NOT NULL,
    description TEXT,
    mandatory_subjects TEXT[],
    elective_subjects TEXT[]
);

INSERT INTO jordan_academic_tracks (id, name_ar, mandatory_subjects) VALUES
('scientific', 'الفرع العلمي', ARRAY['الرياضيات العلمي', 'الفيزياء', 'الكيمياء', 'العلوم الحياتية', 'اللغة الإنجليزية', 'اللغة العربية']),
('literary', 'الفرع الأدبي', ARRAY['تاريخ الأردن', 'اللغة العربية تخصص', 'الجغرافيا', 'اللغة الإنجليزية', 'الرياضيات الأدبي']);
