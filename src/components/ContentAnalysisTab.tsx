import React, { useState } from 'react';
import { BarChart3, Sparkles, Printer, Copy, Check } from 'lucide-react';
import { GradeInfo, SubjectInfo } from '../data/jordanCurriculum';

interface ContentAnalysisTabProps {
  selectedGrade: GradeInfo;
  selectedSubject: SubjectInfo;
}

export const ContentAnalysisTab: React.FC<ContentAnalysisTabProps> = ({
  selectedGrade,
  selectedSubject,
}) => {
  const [selectedUnit, setSelectedUnit] = useState<number>(1);
  const [copied, setCopied] = useState<boolean>(false);

  const currentUnit =
    selectedSubject.units.find((u) => u.number === selectedUnit) || selectedSubject.units[0];

  // Derive standard content analysis categories for the Jordanian curriculum
  const isEnglish = selectedSubject.isEnglish;

  return (
    <div className="space-y-6">
      {/* Top Controller */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 no-print">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-emerald-600" />
              <span>جدول تحليل المحتوى الدراسي (Content Analysis Matrix)</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              تحليل محتوى وحدات المنهاج الأردني إلى: المفاهيم، الحقائق، التعميمات، المهارات، والقيم والاتجاهات
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                const text = document.getElementById('analysis-matrix-table')?.innerText || '';
                navigator.clipboard.writeText(text);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition-all"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>نسخ الجدول</span>
            </button>
            <button
              onClick={() => window.print()}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-xl shadow-xs transition-all"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>طباعة المصفوفة</span>
            </button>
          </div>
        </div>

        {/* Unit Selector Pills */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold text-slate-600">اختر الوحدة:</span>
          {selectedSubject.units.map((u) => (
            <button
              key={u.number}
              onClick={() => setSelectedUnit(u.number)}
              className={`text-xs px-3 py-1.5 rounded-xl font-medium transition-all ${
                selectedUnit === u.number
                  ? 'bg-emerald-600 text-white font-bold shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              الوحدة {u.number}: {u.title}
            </button>
          ))}
        </div>
      </div>

      {/* Content Analysis Matrix Table */}
      <div id="analysis-matrix-table" className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden print-area">
        <div className="bg-gradient-to-r from-emerald-800 to-teal-800 text-white p-4 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold">
              مصفوفة تحليل المحتوى - {selectedSubject.name} ({selectedGrade.name})
            </h3>
            <span className="text-xs text-emerald-200">
              الوحدة {currentUnit?.number || 1}: {currentUnit?.title}
            </span>
          </div>
          <span className="text-xs bg-emerald-900/60 border border-emerald-600 px-2.5 py-1 rounded-lg">
            نموذج الإشراف التربوي المعتمد 🇯🇴
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-right border-collapse text-xs md:text-sm">
            <thead>
              <tr className="bg-slate-100 text-slate-700 border-b border-slate-200 font-bold">
                <th className="p-3.5 border-l border-slate-200 w-1/5">1. المفاهيم والمصطلحات (Concepts)</th>
                <th className="p-3.5 border-l border-slate-200 w-1/5">2. الحقائق والمعارف (Facts)</th>
                <th className="p-3.5 border-l border-slate-200 w-1/5">3. التعميمات والقوانين (Generalizations)</th>
                <th className="p-3.5 border-l border-slate-200 w-1/5">4. المهارات والعمليات (Skills)</th>
                <th className="p-3.5 w-1/5">5. القيم والاتجاهات (Values & Attitudes)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              <tr className="align-top">
                {/* Concepts */}
                <td className="p-3.5 border-l border-slate-200 bg-emerald-50/20">
                  <ul className="space-y-2 list-disc list-inside text-slate-800">
                    {currentUnit?.topics.map((top, idx) => (
                      <li key={idx} className="leading-snug">{top}</li>
                    ))}
                    {isEnglish ? (
                      <>
                        <li>Grammar Tenses & Verb Forms</li>
                        <li>Derivations (Nouns, Adjectives, Verbs)</li>
                        <li>Collocations & Phrasal Verbs</li>
                      </>
                    ) : (
                      <>
                        <li>المصطلحات التخصصية الواردة بالدرس</li>
                        <li>المعجم اللغوي والدلالي</li>
                      </>
                    )}
                  </ul>
                </td>

                {/* Facts */}
                <td className="p-3.5 border-l border-slate-200">
                  <ul className="space-y-2 list-disc list-inside text-slate-800">
                    <li>المعلومات والبيانات التاريخية / العلمية الواردة بنص الدرس في الكتاب.</li>
                    <li>الأمثلة التوضيحية لنتاجات التعلم المعتمدة في المنهاج الأردني.</li>
                    <li>المعايير المحددة في دليل المعلم وكتاب الطالب.</li>
                  </ul>
                </td>

                {/* Generalizations */}
                <td className="p-3.5 border-l border-slate-200 bg-slate-50/50">
                  <ul className="space-y-2 list-disc list-inside text-slate-800">
                    {isEnglish ? (
                      <>
                        <li>Subject-verb agreement determines correct auxiliary usage.</li>
                        <li>Time adverbials determine appropriate past/present aspects.</li>
                        <li>Reported speech shifts tenses back one step in time.</li>
                      </>
                    ) : (
                      <>
                        <li>القاعدة العامة التي تحكم الظاهرة أو المسألة الرياضية/اللغوية.</li>
                        <li>العلاقة السببية بين عناصر الدرس.</li>
                      </>
                    )}
                  </ul>
                </td>

                {/* Skills */}
                <td className="p-3.5 border-l border-slate-200">
                  <ul className="space-y-2 list-disc list-inside text-slate-800">
                    <li>مهارة حل التمارين والمسائل في كتاب الأنشطة والتمارين.</li>
                    <li>التفكير الناقد والاستنتاج من النصوص والمعطيات.</li>
                    <li>التطبيق العملي وحل أسئلة نهاية الوحدة بنجاح.</li>
                    {isEnglish && <li>Reading comprehension, writing essays, speaking fluency.</li>}
                  </ul>
                </td>

                {/* Values */}
                <td className="p-3.5 bg-amber-50/20">
                  <ul className="space-y-2 list-disc list-inside text-slate-800">
                    <li>الاعتزاز بالهوية الوطنية الأردنية ومنجزات الوطن.</li>
                    <li>تقدير قيمة العلم والمعرفة ومواكبة التكنولوجيا.</li>
                    <li>الالتزام بأخلاقيات العمل والتعلم التعاوني.</li>
                  </ul>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
