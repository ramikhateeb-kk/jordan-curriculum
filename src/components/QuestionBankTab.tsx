import React, { useState } from 'react';
import { HelpCircle, Sparkles, CheckCircle2, XCircle, RefreshCw, Trophy, BookOpen } from 'lucide-react';
import { GradeInfo, SubjectInfo } from '../data/jordanCurriculum';

interface QuestionBankTabProps {
  grades: GradeInfo[];
  selectedGrade: GradeInfo;
  selectedSubject: SubjectInfo;
}

export const QuestionBankTab: React.FC<QuestionBankTabProps> = ({
  selectedGrade,
  selectedSubject,
}) => {
  const [unitNumber, setUnitNumber] = useState<string>('');
  const [questionCount, setQuestionCount] = useState<number>(5);
  const [difficulty, setDifficulty] = useState<string>('medium');
  const [loading, setLoading] = useState<boolean>(false);
  const [questions, setQuestions] = useState<any[]>([]);
  const [userAnswers, setUserAnswers] = useState<Record<number, number>>({});
  const [showResults, setShowResults] = useState<boolean>(false);

  const handleGenerateQuestions = async () => {
    setLoading(true);
    setUserAnswers({});
    setShowResults(false);
    try {
      const res = await fetch('/api/curriculum/quiz-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gradeId: selectedGrade.id,
          subjectId: selectedSubject.id,
          unitNumber: unitNumber ? parseInt(unitNumber, 10) : undefined,
          count: questionCount,
          difficulty,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setQuestions(data.questions || []);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectOption = (questionId: number, optionIdx: number) => {
    if (showResults) return;
    setUserAnswers(prev => ({ ...prev, [questionId]: optionIdx }));
  };

  const calculateScore = () => {
    let score = 0;
    questions.forEach(q => {
      if (userAnswers[q.id] === q.correctIndex) {
        score++;
      }
    });
    return score;
  };

  return (
    <div className="space-y-6">
      {/* Configuration Header */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <HelpCircle className="w-5 h-5 text-emerald-600" />
              <span>بنك الأسئلة والاختبارات التفاعلية</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              توليد أسئلة ونماذج امتحانات متوافقة مع معايير وزارة التربية والتعليم الأردنية
            </p>
          </div>

          <div className="text-xs font-semibold px-3 py-1 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200">
            {selectedSubject.name} • {selectedGrade.name}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 mt-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">الوحدة المحددة:</label>
            <select
              value={unitNumber}
              onChange={(e) => setUnitNumber(e.target.value)}
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            >
              <option value="">جميع الوحدات</option>
              {selectedSubject.units.map(u => (
                <option key={u.number} value={u.number}>الوحدة {u.number}: {u.title}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">عدد الأسئلة:</label>
            <select
              value={questionCount}
              onChange={(e) => setQuestionCount(parseInt(e.target.value, 10))}
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            >
              <option value={3}>3 أسئلة سريعة</option>
              <option value={5}>5 أسئلة (اختبار قصير)</option>
              <option value={10}>10 أسئلة (اختبار شامل)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">مستوى الصعوبة:</label>
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            >
              <option value="easy">سهل (تذكر ومفاهيم أساسية)</option>
              <option value="medium">متوسط (تطبيق وفهم)</option>
              <option value="hard">متقدم (تحليل ونمط التوجيهي)</option>
            </select>
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            onClick={handleGenerateQuestions}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl shadow-md transition-all active:scale-95 disabled:opacity-60"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>جاري إنشاء الأسئلة...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-amber-300" />
                <span>توليد نموذج الأسئلة</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Generated Quiz */}
      {questions.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between bg-white px-5 py-3 rounded-xl border border-slate-200">
            <span className="text-sm font-bold text-slate-700">
              نموذج اختبار {selectedSubject.name} ({questions.length} أسئلة)
            </span>
            {showResults && (
              <div className="flex items-center gap-2 text-sm font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-lg border border-emerald-200">
                <Trophy className="w-4 h-4 text-amber-500" />
                <span>النتيجة: {calculateScore()} من {questions.length}</span>
              </div>
            )}
          </div>

          {questions.map((q, idx) => {
            const isAnswered = userAnswers[q.id] !== undefined;
            const isCorrect = userAnswers[q.id] === q.correctIndex;
            const isEnglish = selectedSubject.isEnglish;

            return (
              <div
                key={q.id || idx}
                className={`bg-white rounded-2xl p-5 border transition-all ${
                  showResults
                    ? isCorrect
                      ? 'border-emerald-300 bg-emerald-50/20'
                      : 'border-red-200 bg-red-50/20'
                    : 'border-slate-200'
                }`}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <span className="w-7 h-7 rounded-lg bg-slate-100 text-slate-700 font-bold flex items-center justify-center text-xs shrink-0 mt-0.5">
                    {idx + 1}
                  </span>
                  <p
                    className={`flex-1 text-sm md:text-base font-bold text-slate-800 ${
                      isEnglish ? 'font-english text-left' : 'text-right'
                    }`}
                    dir={isEnglish ? 'ltr' : 'rtl'}
                  >
                    {q.question}
                  </p>
                </div>

                {/* Options */}
                <div className="space-y-2 mr-10 rtl:mr-10 ltr:ml-10" dir={isEnglish ? 'ltr' : 'rtl'}>
                  {q.options.map((opt: string, optIdx: number) => {
                    const isSelected = userAnswers[q.id] === optIdx;
                    let optStyle = 'border-slate-200 hover:bg-slate-50 text-slate-700';

                    if (showResults) {
                      if (optIdx === q.correctIndex) {
                        optStyle = 'border-emerald-500 bg-emerald-50 text-emerald-950 font-bold';
                      } else if (isSelected) {
                        optStyle = 'border-red-400 bg-red-50 text-red-950';
                      }
                    } else if (isSelected) {
                      optStyle = 'border-emerald-600 bg-emerald-50/80 text-emerald-900 font-semibold';
                    }

                    return (
                      <button
                        key={optIdx}
                        onClick={() => handleSelectOption(q.id, optIdx)}
                        className={`w-full text-right p-3 rounded-xl border text-xs md:text-sm transition-all flex items-center justify-between ${optStyle} ${
                          isEnglish ? 'text-left font-english' : 'text-right'
                        }`}
                      >
                        <span>{opt}</span>
                        {showResults && optIdx === q.correctIndex && (
                          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                        )}
                        {showResults && isSelected && optIdx !== q.correctIndex && (
                          <XCircle className="w-4 h-4 text-red-500 shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>

                {/* Explanation */}
                {showResults && q.explanation && (
                  <div className="mt-3.5 p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 leading-relaxed mr-10 rtl:mr-10 ltr:ml-10">
                    <span className="font-bold text-emerald-700 block mb-0.5">توضيح الإجابة الصحيحة:</span>
                    <p>{q.explanation}</p>
                  </div>
                )}
              </div>
            );
          })}

          <div className="flex items-center justify-between pt-2">
            {!showResults ? (
              <button
                onClick={() => setShowResults(true)}
                disabled={Object.keys(userAnswers).length === 0}
                className="px-6 py-2.5 bg-emerald-700 hover:bg-emerald-800 text-white font-bold text-sm rounded-xl shadow-md transition-all disabled:opacity-50"
              >
                تصحيح الاختبار وعرض النتائج
              </button>
            ) : (
              <button
                onClick={handleGenerateQuestions}
                className="px-6 py-2.5 bg-slate-800 hover:bg-slate-900 text-white font-bold text-sm rounded-xl shadow-md transition-all flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                <span>إعادة الاختبار بأسئلة جديدة</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
