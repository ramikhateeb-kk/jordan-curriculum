import React, { useState } from 'react';
import {
  Search,
  Sparkles,
  BookOpen,
  Volume2,
  Copy,
  Check,
  Printer,
  AlertTriangle,
  Lightbulb,
  AlignLeft,
  AlignRight,
  ArrowRight,
  HelpCircle,
  FileCheck2,
  Bookmark,
  Share2,
  RotateCcw
} from 'lucide-react';
import { GradeInfo, SubjectInfo, cleanCurriculumText } from '../data/jordanCurriculum';

interface ExplainTabProps {
  grades: GradeInfo[];
  selectedGrade: GradeInfo;
  setSelectedGrade: (g: GradeInfo) => void;
  selectedSubject: SubjectInfo;
  setSelectedSubject: (s: SubjectInfo) => void;
}

export const ExplainTab: React.FC<ExplainTabProps> = ({
  grades,
  selectedGrade,
  setSelectedGrade,
  selectedSubject,
  setSelectedSubject,
}) => {
  const [bookType, setBookType] = useState<'activity_book' | 'students_book'>('activity_book');
  const [semester, setSemester] = useState<'1' | '2'>('1');
  const [unitNumber, setUnitNumber] = useState<string>('');
  const [query, setQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [searchLoading, setSearchLoading] = useState<boolean>(false);

  // Results state
  const [explanation, setExplanation] = useState<string>('');
  const [isOffTopic, setIsOffTopic] = useState<boolean>(false);
  const [offTopicMessage, setOffTopicMessage] = useState<string>('');
  const [matchedExercises, setMatchedExercises] = useState<any[]>([]);
  const [activitySearchResults, setActivitySearchResults] = useState<any[]>([]);
  const [hasSearchedActivity, setHasSearchedActivity] = useState<boolean>(false);

  // Directionality state (Auto-detected, but user can override)
  const [forceDirection, setForceDirection] = useState<'auto' | 'ltr' | 'rtl'>('auto');
  const [isEnglishDetected, setIsEnglishDetected] = useState<boolean>(selectedSubject.isEnglish);
  const [copied, setCopied] = useState<boolean>(false);
  const [speaking, setSpeaking] = useState<boolean>(false);

  // Quick suggestions based on active subject
  const suggestions = selectedSubject.isEnglish
    ? [
        'حل تمرين رقم 2 في صفحة 7 في كتاب الأنشطة (Activity Book)',
        'Explain Exercise 3 on Page 8 in Activity Book',
        'حل أسئلة صفحة 10 في كتاب التمارين Action Pack 12',
        'شرح قاعدة Causative (have something done) مع أمثلة',
        'معاني كلمات الوحدة الأولى والمشتقات في كتاب الطالب'
      ]
    : selectedSubject.id.includes('math')
    ? [
        'حل سؤال رقم 4 صفحة 16 في كتاب التمارين والأنشطة',
        'حل نظام معادلات خطية وتربيعية صفحة 11',
        'شرح فكرة التقريب وحل تمارين كتاب الطالب ص 14'
      ]
    : selectedSubject.id.includes('history')
    ? [
        'حل أسئلة درس إعلان استقلال المملكة الأردنية الهاشمية ص 22',
        'أهمية مسلة ميشع في تاريخ الأردن القديم',
        'حل سؤال 3 صفحة 18 في كتاب تاريخ الأردن'
      ]
    : [
        'حل السؤال الثاني صفحة 18 في كتاب التمارين',
        'شرح الدرس الأول وأهم نتاجات التعلم',
        'حل تدريبات مهارات القواعد والأنشطة'
      ];

  // Auto-detect direction
  const effectiveDirection =
    forceDirection === 'auto'
      ? isEnglishDetected || selectedSubject.isEnglish
        ? 'ltr'
        : 'rtl'
      : forceDirection;

  // Search Activity Book without blank lines
  const handleSearchActivityBook = async (customQuery?: string) => {
    const q = (customQuery || query).trim();
    if (!q) return;

    setSearchLoading(true);
    setHasSearchedActivity(true);
    try {
      const res = await fetch('/api/curriculum/search-activity-book', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gradeId: selectedGrade.id,
          subjectId: selectedSubject.id,
          query: q,
          unitNumber: unitNumber ? parseInt(unitNumber, 10) : undefined,
        }),
      });
      const data = await res.json();
      if (data.success) {
        // Strip out excessive blank lines from questions, answers, explanations
        const cleaned = (data.results || []).map((r: any) => ({
          ...r,
          question: cleanCurriculumText(r.question),
          answer: cleanCurriculumText(r.answer),
          explanation: cleanCurriculumText(r.explanation),
        }));
        setActivitySearchResults(cleaned);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSearchLoading(false);
    }
  };

  // Main Submit: Ask / Explain
  const handleExplain = async (customQuery?: string) => {
    const q = (customQuery || query).trim();
    if (!q) return;

    setLoading(true);
    setIsOffTopic(false);
    setOffTopicMessage('');
    setExplanation('');
    setMatchedExercises([]);

    // Also update activity book results if relevant
    handleSearchActivityBook(q);

    try {
      const res = await fetch('/api/curriculum/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gradeId: selectedGrade.id,
          subjectId: selectedSubject.id,
          bookType,
          semester,
          unitNumber: unitNumber ? parseInt(unitNumber, 10) : undefined,
          query: q,
        }),
      });

      const data = await res.json();

      if (data.isOffTopic) {
        setIsOffTopic(true);
        setOffTopicMessage(data.message);
      } else if (data.success) {
        setExplanation(cleanCurriculumText(data.explanation));
        setIsEnglishDetected(data.isEnglish || selectedSubject.isEnglish);
        if (data.matchingActivityBookExercises) {
          setMatchedExercises(data.matchingActivityBookExercises);
        }
      } else {
        setIsOffTopic(true);
        setOffTopicMessage(data.error || 'حدث خطأ في جلب الإجابة.');
      }
    } catch (err: any) {
      setIsOffTopic(true);
      setOffTopicMessage('تعذر الاتصال بالخادم. يرجى المحاولة مجدداً.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!explanation) return;
    navigator.clipboard.writeText(explanation);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSpeech = () => {
    if (!('speechSynthesis' in window)) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(explanation);
    utterance.lang = effectiveDirection === 'ltr' ? 'en-US' : 'ar-SA';
    utterance.rate = 0.95;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="space-y-6">
      {/* Configuration Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 no-print">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-emerald-600" />
              <span>تبويب "اشرح لي" وحل أسئلة المنهاج</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              حل أسئلة كتاب الأنشطة والتمارين وكتاب الطالب مع شرح تفصيلي وتنسيق متوافق للغة الإنجليزية
            </p>
          </div>

          {/* Book Type Toggle */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl text-xs font-medium">
            <button
              onClick={() => setBookType('activity_book')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                bookType === 'activity_book'
                  ? 'bg-emerald-600 text-white font-bold shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <span>📝 كتاب الأنشطة والتمارين (Activity Book)</span>
            </button>
            <button
              onClick={() => setBookType('students_book')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                bookType === 'students_book'
                  ? 'bg-emerald-600 text-white font-bold shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <span>📘 كتاب الطالب (Student's Book)</span>
            </button>
          </div>
        </div>

        {/* Selectors Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mt-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">الصف الدراسي:</label>
            <select
              value={selectedGrade.id}
              onChange={(e) => {
                const g = grades.find((item) => item.id === e.target.value);
                if (g) {
                  setSelectedGrade(g);
                  setSelectedSubject(g.subjects[0]);
                  setIsEnglishDetected(g.subjects[0].isEnglish);
                }
              }}
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500"
            >
              {grades.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} ({g.nameEn})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">المادة الدراسية:</label>
            <select
              value={selectedSubject.id}
              onChange={(e) => {
                const s = selectedGrade.subjects.find((item) => item.id === e.target.value);
                if (s) {
                  setSelectedSubject(s);
                  setIsEnglishDetected(s.isEnglish);
                }
              }}
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500 font-medium"
            >
              {selectedGrade.subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} {s.isEnglish ? '🇬🇧' : '🇯🇴'}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">الفصل الدراسي:</label>
            <div className="flex bg-slate-50 border border-slate-200 rounded-xl p-1">
              <button
                onClick={() => setSemester('1')}
                className={`flex-1 text-xs py-1.5 rounded-lg font-medium transition-all ${
                  semester === '1' ? 'bg-emerald-600 text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                الفصل الأول
              </button>
              <button
                onClick={() => setSemester('2')}
                className={`flex-1 text-xs py-1.5 rounded-lg font-medium transition-all ${
                  semester === '2' ? 'bg-emerald-600 text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                الفصل الثاني
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">الوحدة الدراسية (اختياري):</label>
            <select
              value={unitNumber}
              onChange={(e) => setUnitNumber(e.target.value)}
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500"
            >
              <option value="">جميع وحدات الكتاب</option>
              {selectedSubject.units.map((u) => (
                <option key={u.number} value={u.number}>
                  الوحدة {u.number}: {u.title}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Input & Search Box */}
        <div className="mt-5">
          <label className="block text-xs font-semibold text-slate-700 mb-1.5">
            اكتب رقم السؤال والصفحة أو الموضوع الذي تريد شرحه:
          </label>
          <div className="relative flex items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleExplain();
              }}
              placeholder={
                selectedSubject.isEnglish
                  ? 'مثال: حل سؤال 2 صفحة 7 في كتاب الأنشطة أو explain exercise 3 on page 8'
                  : 'مثال: حل سؤال رقم 4 في صفحة 22 في كتاب الأنشطة أو شرح درس...'
              }
              className="w-full text-sm md:text-base bg-slate-50 border border-slate-300 rounded-2xl pr-4 pl-36 py-3.5 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 shadow-inner"
            />
            <div className="absolute left-2 flex items-center gap-1.5">
              <button
                onClick={() => handleSearchActivityBook()}
                disabled={searchLoading}
                title="بحث مخصص في نصوص كتاب الأنشطة بدون فراغات"
                className="hidden sm:flex items-center gap-1 px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 text-xs font-medium rounded-xl transition-all"
              >
                <Search className="w-3.5 h-3.5" />
                <span>بحث بالأنشطة</span>
              </button>
              <button
                onClick={() => handleExplain()}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs md:text-sm font-bold rounded-xl shadow-md transition-all active:scale-95 disabled:opacity-60"
              >
                {loading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>جاري الشرح...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 text-amber-300" />
                    <span>اشرح وحل السؤال</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Quick suggestions pills */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold text-slate-400">اقتراحات سريعة:</span>
          {suggestions.map((s, idx) => (
            <button
              key={idx}
              onClick={() => {
                setQuery(s);
                handleExplain(s);
              }}
              className="text-xs bg-slate-100 hover:bg-emerald-50 hover:text-emerald-700 text-slate-600 px-2.5 py-1 rounded-lg border border-slate-200/80 transition-all text-right"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Activity Book Compact Clean Search Results (Zero extra blank lines!) */}
      {hasSearchedActivity && (
        <div className="bg-slate-50 border border-slate-200/90 rounded-2xl p-4.5 no-print">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-emerald-700" />
              <h3 className="text-sm font-bold text-slate-800">
                نتائج مطابقة موضوع السؤال في كتاب الأنشطة والتمارين (بدون أسطر فارغة)
              </h3>
            </div>
            <span className="text-xs bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full font-medium">
              {activitySearchResults.length} نتائج
            </span>
          </div>

          {searchLoading ? (
            <div className="py-4 text-center text-xs text-slate-500">جاري مسح نصوص وتمارين كتاب الأنشطة...</div>
          ) : activitySearchResults.length === 0 ? (
            <div className="text-xs text-slate-500 py-2">
              لا توجد نصوص مطابقة حرفياً، سيتم استخدام الذكاء الاصطناعي لتوليد الحل والشرح الشامل للسؤال.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-72 overflow-y-auto pr-1">
              {activitySearchResults.map((res, i) => (
                <div
                  key={i}
                  className="bg-white border border-slate-200 rounded-xl p-3 hover:border-emerald-400 transition-all shadow-2xs flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between text-[11px] font-semibold text-emerald-700 mb-1.5">
                      <span className="bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                        {res.unitTitle}
                      </span>
                      <span className="bg-amber-50 text-amber-800 px-2 py-0.5 rounded-md border border-amber-200">
                        صفحة {res.page} • تمرين {res.exerciseNum}
                      </span>
                    </div>
                    {/* Cleaned question text without multiple newlines */}
                    <p className={`text-xs text-slate-800 font-medium whitespace-pre-line leading-relaxed ${selectedSubject.isEnglish ? 'font-english text-left' : ''}`} dir={selectedSubject.isEnglish ? 'ltr' : 'rtl'}>
                      {res.question}
                    </p>
                    {res.answer && (
                      <p className={`text-[11px] text-slate-600 mt-2 bg-slate-50 p-2 rounded-lg border border-slate-100 whitespace-pre-line ${selectedSubject.isEnglish ? 'font-english text-left' : ''}`} dir={selectedSubject.isEnglish ? 'ltr' : 'rtl'}>
                        <span className="font-bold text-emerald-700">الحل: </span>
                        {res.answer}
                      </p>
                    )}
                  </div>

                  <button
                    onClick={() => {
                      const exQuery = `حل تمرين ${res.exerciseNum} صفحة ${res.page} في كتاب الأنشطة: ${res.question}`;
                      setQuery(exQuery);
                      handleExplain(exQuery);
                    }}
                    className="mt-2.5 w-full text-center text-xs font-bold text-emerald-700 hover:text-emerald-900 bg-emerald-50 hover:bg-emerald-100 py-1.5 rounded-lg border border-emerald-200/80 transition-colors flex items-center justify-center gap-1"
                  >
                    <span>عرض الحل والشرح المفصل لهذا التمرين</span>
                    <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Off-Topic Rejection Alert (ONLY for questions truly outside the selected curriculum!) */}
      {isOffTopic && (
        <div className="bg-amber-50 border-2 border-amber-300 rounded-2xl p-5 text-amber-900 flex items-start gap-3.5 shadow-sm">
          <div className="p-2 bg-amber-200 text-amber-800 rounded-xl shrink-0 mt-0.5">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h4 className="font-bold text-base text-amber-950">السؤال خارج نطاق المادة المقررة</h4>
            <p className="text-sm leading-relaxed text-amber-800">
              {offTopicMessage || `تعذر تقديم الإجابة: هذا السؤال لا يتعلق بمنهاج مادة (${selectedSubject.name}) المحددة.`}
            </p>
            <p className="text-xs text-amber-700/90 pt-1">
              نصيحة: إذا كان سؤالك يخص مادة أخرى (مثل العلوم أو الجغرافيا أو الرياضيات)، يرجى تبديل المادة من القائمة أعلاه للحصول على الإجابة الدقيقة من منهاجها المقرر.
            </p>
          </div>
        </div>
      )}

      {/* Main Explanation Area */}
      {explanation && !isOffTopic && (
        <div className="bg-white rounded-2xl shadow-md border border-slate-200 overflow-hidden print-area">
          {/* Top Bar for Explanation View: Title + Direction Switcher + Actions */}
          <div className="bg-gradient-to-r from-slate-800 to-slate-900 text-white px-5 py-3.5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center border border-emerald-500/30">
                <FileCheck2 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold">
                  شرح وحل السؤال وفق المنهاج الأردني
                </h3>
                <span className="text-[11px] text-slate-300">
                  {selectedSubject.name} • {selectedGrade.name} • {bookType === 'activity_book' ? 'كتاب الأنشطة والتمارين' : 'كتاب الطالب'}
                </span>
              </div>
            </div>

            {/* Direction & Action Controls */}
            <div className="flex items-center gap-2 text-xs no-print">
              {/* Directionality Switcher for English and Bilingual Content */}
              <div className="flex items-center bg-slate-700/80 p-0.5 rounded-lg border border-slate-600">
                <button
                  onClick={() => setForceDirection('rtl')}
                  title="تنسيق واتجاه عربي (من اليمين لليسار)"
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-all ${
                    effectiveDirection === 'rtl'
                      ? 'bg-emerald-600 text-white font-bold'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  <AlignRight className="w-3.5 h-3.5" />
                  <span>RTL عربي</span>
                </button>
                <button
                  onClick={() => setForceDirection('ltr')}
                  title="تنسيق واتجاه إنجليزي (من اليسار لليمين - مناسب لمادة اللغة الإنجليزية)"
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-all ${
                    effectiveDirection === 'ltr'
                      ? 'bg-amber-400 text-slate-950 font-bold'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  <AlignLeft className="w-3.5 h-3.5" />
                  <span>LTR English</span>
                </button>
              </div>

              {/* Speech Button for English Audio Pronunciation */}
              <button
                onClick={handleSpeech}
                title="استمع إلى قراءة الشرح بالصوت"
                className={`p-2 rounded-lg border transition-all ${
                  speaking
                    ? 'bg-red-600 border-red-500 text-white animate-pulse'
                    : 'bg-slate-700/80 hover:bg-slate-600 border-slate-600 text-slate-200'
                }`}
              >
                <Volume2 className="w-4 h-4" />
              </button>

              {/* Copy Button */}
              <button
                onClick={handleCopy}
                title="نسخ الشرح"
                className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-700/80 hover:bg-slate-600 border border-slate-600 rounded-lg text-slate-200 transition-all"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span className="hidden sm:inline">{copied ? 'تم النسخ' : 'نسخ'}</span>
              </button>

              {/* Print Button */}
              <button
                onClick={handlePrint}
                title="طباعة أو تصدير PDF"
                className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-700/80 hover:bg-slate-600 border border-slate-600 rounded-lg text-slate-200 transition-all"
              >
                <Printer className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">طباعة</span>
              </button>
            </div>
          </div>

          {/* Explanation Content Box */}
          <div
            className={`p-6 md:p-8 space-y-4 text-slate-800 transition-all leading-relaxed ${
              effectiveDirection === 'ltr'
                ? 'font-english text-left text-[15px]'
                : 'text-right text-[15px]'
            }`}
            dir={effectiveDirection}
          >
            {/* Context Header pill */}
            <div className="bg-emerald-50/70 border border-emerald-100 rounded-xl p-3 flex items-center justify-between text-xs text-emerald-900">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <span className="font-semibold">الموضوع المطلوب:</span>
                <span className="font-bold text-emerald-950">"{query}"</span>
              </div>
              <span className="text-[11px] bg-white px-2 py-0.5 rounded border border-emerald-200 font-medium">
                تم التحقق والمطابقة مع مناهج المملكة الأردنية الهاشمية
              </span>
            </div>

            {/* Formatted Text Content */}
            <div className="prose max-w-none text-slate-800">
              {explanation.split('\n\n').map((paragraph, pIdx) => {
                const pClean = paragraph.trim();
                if (!pClean) return null;

                // Grammar Rule or Formula Box
                const isRule =
                  pClean.includes('القاعدة') ||
                  pClean.includes('Rule:') ||
                  pClean.includes('Form:') ||
                  pClean.includes('Grammar Box') ||
                  pClean.includes('قاعدة الدرس:');

                // Solution/Answer Box
                const isAnswer =
                  pClean.includes('الحل النهائي') ||
                  pClean.includes('Model Answer') ||
                  pClean.includes('Direct Answer') ||
                  pClean.includes('الإجابة النموذجية');

                // Warning or Exam Tip
                const isTip =
                  pClean.includes('إضاءة') ||
                  pClean.includes('تنبيه') ||
                  pClean.includes('Tip:') ||
                  pClean.includes('ملاحظة هامة');

                if (isRule) {
                  return (
                    <div
                      key={pIdx}
                      className="my-4 bg-indigo-50/80 border-l-4 rtl:border-l-0 rtl:border-r-4 border-indigo-600 rounded-xl p-4 text-indigo-950 shadow-2xs"
                    >
                      <div className="flex items-center gap-2 text-xs font-bold text-indigo-800 mb-1.5">
                        <Lightbulb className="w-4 h-4 text-indigo-600" />
                        <span>قاعدة الدرس والمفهوم الأساسي (Key Rule & Pattern):</span>
                      </div>
                      <p className="whitespace-pre-line text-sm md:text-base font-semibold leading-relaxed">
                        {pClean}
                      </p>
                    </div>
                  );
                }

                if (isAnswer) {
                  return (
                    <div
                      key={pIdx}
                      className="my-4 bg-emerald-50 border-l-4 rtl:border-l-0 rtl:border-r-4 border-emerald-600 rounded-xl p-4 text-emerald-950 shadow-2xs"
                    >
                      <div className="flex items-center gap-2 text-xs font-bold text-emerald-800 mb-1.5">
                        <FileCheck2 className="w-4 h-4 text-emerald-600" />
                        <span>الحل المباشر والنموذجي (Direct Answer):</span>
                      </div>
                      <p className="whitespace-pre-line text-sm md:text-base font-bold leading-relaxed">
                        {pClean}
                      </p>
                    </div>
                  );
                }

                if (isTip) {
                  return (
                    <div
                      key={pIdx}
                      className="my-3 bg-amber-50/80 border border-amber-200 rounded-xl p-3.5 text-amber-950 text-xs md:text-sm"
                    >
                      <span className="font-bold text-amber-900 block mb-1">💡 إضاءة امتحانية للطلبة:</span>
                      <p className="whitespace-pre-line leading-relaxed">{pClean}</p>
                    </div>
                  );
                }

                // Standard paragraph
                return (
                  <p
                    key={pIdx}
                    className="whitespace-pre-line text-sm md:text-base leading-relaxed text-slate-800 my-2.5 font-normal"
                  >
                    {pClean}
                  </p>
                );
              })}
            </div>

            {/* English Action Pack Special Helpers (Vocabulary & Pronunciation tools) */}
            {selectedSubject.isEnglish && (
              <div className="mt-6 pt-5 border-t border-slate-200 bg-slate-50/80 rounded-xl p-4 text-left font-english" dir="ltr">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                    <span>🇬🇧 Action Pack English Study Tools</span>
                  </h4>
                  <span className="text-[11px] text-slate-500">Ministry of Education Standard</span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Tip: Keep sentence punctuation clear and adhere to subject-verb agreement. In Action Pack exams, pay close attention to tense keywords (since, for, yesterday, already, while, usually).
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Intro empty state when no query yet */}
      {!explanation && !isOffTopic && !loading && (
        <div className="bg-gradient-to-br from-white to-slate-50 border border-slate-200 rounded-2xl p-8 text-center space-y-4">
          <div className="w-16 h-16 bg-emerald-100 text-emerald-700 rounded-2xl flex items-center justify-center mx-auto shadow-inner">
            <BookOpen className="w-8 h-8" />
          </div>
          <div className="max-w-lg mx-auto space-y-2">
            <h3 className="text-base font-bold text-slate-800">
              مرحباً بك في المساعد الذكي للمناهج الأردنية
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              اختر المادة والصف الدراسي، ثم اكتب رقم السؤال أو الصفحة المطلوبة (مثل: "حل سؤال 3 صفحة 15 في كتاب الأنشطة") ليقوم النظام بتقديم الشرح والحل النموذجي الدقيق المعتمد في المدارس الأردنية.
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-4 text-xs font-medium text-slate-600 pt-2">
            <span className="flex items-center gap-1 text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
              ✓ تنسيق مخصص للغة الإنجليزية LTR
            </span>
            <span className="flex items-center gap-1 text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
              ✓ نصوص كتاب الأنشطة بدون أسطر فارغة
            </span>
            <span className="flex items-center gap-1 text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
              ✓ حل بالذكاء الاصطناعي لجميع الأسئلة والصفحات
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
