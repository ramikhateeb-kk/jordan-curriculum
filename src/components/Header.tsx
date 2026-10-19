import React from 'react';
import { BookOpen, Sparkles, HelpCircle, FileText, BarChart3, GraduationCap } from 'lucide-react';

interface HeaderProps {
  activeTab: 'explain' | 'qbank' | 'books' | 'plans' | 'analysis';
  setActiveTab: (tab: 'explain' | 'qbank' | 'books' | 'plans' | 'analysis') => void;
  selectedGradeName: string;
  selectedSubjectName: string;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  selectedGradeName,
  selectedSubjectName,
}) => {
  return (
    <header className="bg-gradient-to-r from-emerald-900 via-emerald-800 to-teal-900 text-white shadow-lg sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between py-3.5 border-b border-emerald-700/60">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-amber-400 to-amber-500 flex items-center justify-center text-emerald-950 font-black shadow-md border border-amber-300">
              <GraduationCap className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight">المساعد الذكي للمناهج الأردنية</h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-700/80 text-emerald-200 border border-emerald-600 font-medium">
                  وزارة التربية والتعليم 🇯🇴
                </span>
              </div>
              <p className="text-xs text-emerald-200/90 mt-0.5">
                شرح الدروس وحل أسئلة الكتب وبنك الأسئلة وإعداد الخطط الدراسية
              </p>
            </div>
          </div>

          <div className="hidden md:flex items-center gap-2 text-xs bg-emerald-950/40 px-3.5 py-1.5 rounded-lg border border-emerald-700/50">
            <span className="text-emerald-300">المادة النشطة:</span>
            <span className="font-semibold text-amber-300">{selectedSubjectName}</span>
            <span className="text-emerald-500">•</span>
            <span className="text-emerald-200">{selectedGradeName}</span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 sm:gap-2 overflow-x-auto py-2.5 text-sm scrollbar-none">
          <button
            onClick={() => setActiveTab('explain')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all shrink-0 ${
              activeTab === 'explain'
                ? 'bg-amber-400 text-emerald-950 shadow-md font-bold'
                : 'text-emerald-100 hover:bg-emerald-800/80 hover:text-white'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>اشرح لي</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${activeTab === 'explain' ? 'bg-emerald-900 text-amber-300' : 'bg-emerald-700 text-emerald-200'}`}>
              محدّث
            </span>
          </button>

          <button
            onClick={() => setActiveTab('qbank')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all shrink-0 ${
              activeTab === 'qbank'
                ? 'bg-amber-400 text-emerald-950 shadow-md font-bold'
                : 'text-emerald-100 hover:bg-emerald-800/80 hover:text-white'
            }`}
          >
            <HelpCircle className="w-4 h-4" />
            <span>بنك الأسئلة والاختبارات</span>
          </button>

          <button
            onClick={() => setActiveTab('books')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all shrink-0 ${
              activeTab === 'books'
                ? 'bg-amber-400 text-emerald-950 shadow-md font-bold'
                : 'text-emerald-100 hover:bg-emerald-800/80 hover:text-white'
            }`}
          >
            <BookOpen className="w-4 h-4" />
            <span>الكتب والمناهج</span>
          </button>

          <button
            onClick={() => setActiveTab('plans')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all shrink-0 ${
              activeTab === 'plans'
                ? 'bg-amber-400 text-emerald-950 shadow-md font-bold'
                : 'text-emerald-100 hover:bg-emerald-800/80 hover:text-white'
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>خطط الدروس</span>
          </button>

          <button
            onClick={() => setActiveTab('analysis')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all shrink-0 ${
              activeTab === 'analysis'
                ? 'bg-amber-400 text-emerald-950 shadow-md font-bold'
                : 'text-emerald-100 hover:bg-emerald-800/80 hover:text-white'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>تحليل المحتوى</span>
          </button>
        </nav>
      </div>
    </header>
  );
};
