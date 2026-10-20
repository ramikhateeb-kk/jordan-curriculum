-- =====================================================================
-- supabase_materials_4.sql — أكثر من نص في الدرس الواحد (كل نص بعنوانه ومفتاحه)
-- شغّله بعد supabase_materials_3.sql. آمن عند إعادة التشغيل.
-- =====================================================================
alter table reading_texts add column if not exists text_key text;
alter table reading_texts add column if not exists position  integer not null default 0;
update reading_texts set text_key = 't1' where text_key is null;
alter table reading_texts alter column text_key set not null;

-- المفتاح القديم كان (book_slug, lesson_title) = نص واحد للدرس؛ يصبح (book_slug, lesson_title, text_key)
alter table reading_texts drop constraint if exists reading_texts_book_slug_lesson_title_key;
create unique index if not exists reading_texts_uniq on reading_texts (book_slug, lesson_title, text_key);
-- ملاحظة: تمارين الدرس تُحفظ في صف خاص بمفتاح "_ex" في الجدول نفسه.
