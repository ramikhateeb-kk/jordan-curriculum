-- supabase_reading_texts.sql: نصوص القراءة ومفردات Action Pack
CREATE TABLE IF NOT EXISTS jordan_reading_passages (
    id SERIAL PRIMARY KEY,
    subject_id TEXT NOT NULL,
    unit_number INTEGER NOT NULL,
    passage_title TEXT NOT NULL,
    passage_text TEXT NOT NULL,
    vocabulary_glossary JSONB,
    direction TEXT DEFAULT 'ltr'
);
