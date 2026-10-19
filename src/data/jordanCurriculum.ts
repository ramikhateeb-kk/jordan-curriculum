export interface SubjectInfo {
  id: string;
  name: string;
  nameEn: string;
  isEnglish: boolean;
  books: {
    id: string;
    name: string;
    nameEn: string;
    type: 'students_book' | 'activity_book' | 'teachers_guide';
  }[];
  units: {
    number: number;
    title: string;
    titleEn?: string;
    topics: string[];
    sampleExercises: {
      page: number;
      exerciseNum: number;
      bookType: 'students_book' | 'activity_book';
      question: string;
      answer: string;
      explanation: string;
    }[];
  }[];
}

export interface GradeInfo {
  id: string;
  name: string;
  nameEn: string;
  stage: 'primary' | 'middle' | 'secondary' | 'tawjihi';
  subjects: SubjectInfo[];
}

// Clean text by stripping consecutive empty lines and trailing spaces
export function cleanCurriculumText(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map(line => line.trim())
    // Allow at most one empty line between content
    .filter((line, idx, arr) => {
      if (line !== '') return true;
      return idx > 0 && arr[idx - 1] !== '';
    })
    .join('\n')
    .trim();
}

export const JORDAN_GRADES: GradeInfo[] = [
  {
    id: 'grade-1',
    name: 'الصف الأول الأساسي',
    nameEn: 'Grade 1',
    stage: 'primary',
    subjects: [
      {
        id: 'english-1',
        name: 'اللغة الإنجليزية (Action Pack 1)',
        nameEn: 'English (Action Pack 1)',
        isEnglish: true,
        books: [
          { id: 'sb-1', name: 'كتاب الطالب (Pupil\'s Book)', nameEn: "Pupil's Book", type: 'students_book' },
          { id: 'ab-1', name: 'كتاب الأنشطة والتمارين (Activity Book)', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'Hello! (مرحباً)',
            titleEn: 'Hello!',
            topics: ['Greetings (Hello, Goodbye)', 'Names (What is your name? I am...)', 'Letters A, B, C', 'Numbers 1-5'],
            sampleExercises: [
              {
                page: 4,
                exerciseNum: 1,
                bookType: 'activity_book',
                question: 'Trace and match: 1. Hello  2. Goodbye',
                answer: 'Match "Hello" with the boy waving, and "Goodbye" with the girl leaving.',
                explanation: 'We use "Hello" when meeting someone and "Goodbye" when leaving.'
              }
            ]
          }
        ]
      },
      {
        id: 'arabic-1',
        name: 'اللغة العربية (لغتنا العربية)',
        nameEn: 'Arabic',
        isEnglish: false,
        books: [
          { id: 'sb-ar-1', name: 'كتاب الطالب والتمارين', nameEn: "Student's Book", type: 'students_book' }
        ],
        units: [
          {
            number: 1,
            title: 'أسرتي ومدرستي',
            topics: ['حرف الباء (ب)', 'حرف الميم (م)', 'الكلمات البصرية: أنا، أمي، أبي'],
            sampleExercises: [
              {
                page: 12,
                exerciseNum: 2,
                bookType: 'students_book',
                question: 'جرّد حرف الباء (ب) من الكلمات التالية: بَاب، حَلِيب، كِتَاب',
                answer: 'بـ (في أول الكلمة)، ـب (في آخر الكلمة منفصل ومتصل).',
                explanation: 'حرف الباء يأتي متصلاً في البداية والوسط ومنفصلاً في النهاية.'
              }
            ]
          }
        ]
      }
    ]
  },
  {
    id: 'grade-4',
    name: 'الصف الرابع الأساسي',
    nameEn: 'Grade 4',
    stage: 'primary',
    subjects: [
      {
        id: 'english-4',
        name: 'اللغة الإنجليزية (Action Pack 4)',
        nameEn: 'English (Action Pack 4)',
        isEnglish: true,
        books: [
          { id: 'sb-4', name: 'كتاب الطالب (Pupil\'s Book)', nameEn: "Pupil's Book", type: 'students_book' },
          { id: 'ab-4', name: 'كتاب الأنشطة والتمارين (Activity Book)', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'We are going to visit a museum (سنزور متحفاً)',
            titleEn: 'We are going to visit a museum',
            topics: ['Future with (be going to)', 'Museum rules', 'Vocabulary: mosaic, model, guide, skeleton', 'Wh- questions'],
            sampleExercises: [
              {
                page: 6,
                exerciseNum: 2,
                bookType: 'activity_book',
                question: 'Complete the sentences with (is going to / are going to): 1. Ali _____ (see) the old coins. 2. The pupils _____ (visit) the museum tomorrow.',
                answer: '1. Ali is going to see the old coins.\n2. The pupils are going to visit the museum tomorrow.',
                explanation: 'Use "is going to" with singular subjects (he, she, Ali) and "are going to" with plural subjects (they, the pupils, we).'
              },
              {
                page: 8,
                exerciseNum: 4,
                bookType: 'activity_book',
                question: 'Read and circle the correct word: We must / mustn\'t touch the exhibits in the museum.',
                answer: 'We mustn\'t touch the exhibits in the museum.',
                explanation: 'Mustn\'t expresses prohibition (قواعد المتحف تمنع لمس المعروضات).'
              }
            ]
          },
          {
            number: 3,
            title: 'At the Science Museum',
            titleEn: 'At the Science Museum',
            topics: ['Past simple regular verbs (-ed)', 'Inventions', 'Time expressions: yesterday, last week'],
            sampleExercises: [
              {
                page: 14,
                exerciseNum: 1,
                bookType: 'activity_book',
                question: 'Write the past tense of these verbs: visit, invent, live, look',
                answer: 'visited, invented, lived, looked',
                explanation: 'Add -ed to regular verbs. If verb ends in -e (live), just add -d (lived).'
              }
            ]
          }
        ]
      },
      {
        id: 'math-4',
        name: 'الرياضيات (منهاج كولينز)',
        nameEn: 'Mathematics',
        isEnglish: false,
        books: [
          { id: 'sb-m-4', name: 'كتاب الطالب', nameEn: "Student's Book", type: 'students_book' },
          { id: 'ab-m-4', name: 'كتاب التمارين والأنشطة', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'الأعداد الكلية والعمليات عليها',
            topics: ['القيمة المنزلية ضمن مئات الألوف', 'مقارنة الأعداد وترتيبها', 'التقريب', 'الجمع والطرح الذهني والكتابي'],
            sampleExercises: [
              {
                page: 11,
                exerciseNum: 3,
                bookType: 'activity_book',
                question: 'قرب العدد 745,289 إلى أقرب عشرة آلاف.',
                answer: '750,000',
                explanation: 'الرقم في منزلة عشرات الآلاف هو 4 والرقم الذي على يمينه هو 5 (كريم)، فيزداد الـ 4 ليصبح 5 ونستبدل المنازل على يمينه بأصفار.'
              }
            ]
          }
        ]
      },
      {
        id: 'science-4',
        name: 'العلوم العامة',
        nameEn: 'Science',
        isEnglish: false,
        books: [
          { id: 'sb-sc-4', name: 'كتاب الطالب', nameEn: "Student's Book", type: 'students_book' },
          { id: 'ab-sc-4', name: 'كتاب التمارين والأنشطة', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'تصنيف الكائنات الحية والبيئات',
            topics: ['مفهوم التصنيف', 'تصنيف النباتات والحيوانات', 'مجموعات الحيوانات (الثدييات، الطيور، الزواحف، البرمائيات، الأسماك)'],
            sampleExercises: [
              {
                page: 9,
                exerciseNum: 1,
                bookType: 'activity_book',
                question: 'صنف الحيوانات التالية حسب طريقة تكاثرها: الدلفين، السلحفاة، الحمامة، الخفاش.',
                answer: 'تتكاثر بالولادة (ثدييات): الدلفين، الخفاش.\nتتكاثر بالبيض: السلحفاة (زواحف)، الحمامة (طيور).',
                explanation: 'الدلفين والخفاش من الثدييات التي تلد وترضع صغارها رغم أن أحدهما يسبح والآخر يطير.'
              }
            ]
          }
        ]
      }
    ]
  },
  {
    id: 'grade-7',
    name: 'الصف السابع الأساسي',
    nameEn: 'Grade 7',
    stage: 'middle',
    subjects: [
      {
        id: 'english-7',
        name: 'اللغة الإنجليزية (Action Pack 7)',
        nameEn: 'English (Action Pack 7)',
        isEnglish: true,
        books: [
          { id: 'sb-7', name: 'كتاب الطالب (Student\'s Book)', nameEn: "Student's Book", type: 'students_book' },
          { id: 'ab-7', name: 'كتاب الأنشطة والتمارين (Activity Book)', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'Are you a good friend? (هل أنت صديق مخلص؟)',
            titleEn: 'Are you a good friend?',
            topics: ['Present Simple vs Present Continuous', 'Personality Adjectives (honest, loyal, helpful, cheerful)', 'Adverbs of frequency', 'Writing personal descriptions'],
            sampleExercises: [
              {
                page: 6,
                exerciseNum: 3,
                bookType: 'activity_book',
                question: 'Correct the verbs in brackets: 1. Listen! The birds (sing) in the garden. 2. Ahmad usually (walk) to school, but today he (take) the bus.',
                answer: '1. are singing\n2. walks, is taking',
                explanation: '"Listen!" indicates an action happening right now (Present Continuous). "Usually" indicates a habit (Present Simple), while "today" with a change of routine indicates Present Continuous.'
              },
              {
                page: 9,
                exerciseNum: 2,
                bookType: 'activity_book',
                question: 'Match words to definitions: 1. loyal  2. cheerful  3. honest',
                answer: '1. loyal: always supports and stays with friends.\n2. cheerful: happy and optimistic.\n3. honest: always tells the truth.',
                explanation: 'Key personality adjectives from Action Pack 7 Module 1.'
              }
            ]
          },
          {
            number: 3,
            title: 'The natural world (عالم الطبيعة)',
            titleEn: 'The natural world',
            topics: ['Past Continuous and Past Simple with (when/while)', 'Wildlife conservation in Jordan (Shaumari, Dana)', 'Environmental vocabulary'],
            sampleExercises: [
              {
                page: 22,
                exerciseNum: 4,
                bookType: 'activity_book',
                question: 'Join the sentences using (while): I was watching the documentary. The lights went out.',
                answer: 'While I was watching the documentary, the lights went out.',
                explanation: 'Use Past Continuous after "while" for the long ongoing action, and Past Simple for the interrupting short action.'
              }
            ]
          }
        ]
      },
      {
        id: 'arabic-7',
        name: 'اللغة العربية (مهارات الاتصال والقواعد)',
        nameEn: 'Arabic',
        isEnglish: false,
        books: [
          { id: 'sb-ar-7', name: 'كتاب الطالب', nameEn: "Student's Book", type: 'students_book' }
        ],
        units: [
          {
            number: 1,
            title: 'أعلام من بلادي والضمار المتصلة',
            topics: ['الفعل اللازم والمتعدي', 'الضمائر المتصلة (تاء الفاعل، نا الفاعلين، كاف الخطاب، هاء الغائب)', 'همزة الوصل والقطع'],
            sampleExercises: [
              {
                page: 18,
                exerciseNum: 2,
                bookType: 'students_book',
                question: 'ميز الفعل اللازم من المتعدي في الجمل التالية: 1. جلسَ الطالبُ بهدوء. 2. كتبَ الشاعرُ قصيدةً جميلة.',
                answer: '1. جلسَ: فعل لازم (اكتفى بفاعله ولم يحتج إلى مفعول به).\n2. كتبَ: فعل متعدٍ (نصب مفعولاً به وهو "قصيدة").',
                explanation: 'الفعل المتعدي يقبل علامة "الهاء" (كتبه)، بينما اللازم لا يقبلها في المعنى السليم (لا يقال: جلسه).'
              }
            ]
          }
        ]
      },
      {
        id: 'history-7',
        name: 'تاريخ الأردن والدراسات الاجتماعية',
        nameEn: 'Jordan History',
        isEnglish: false,
        books: [
          { id: 'sb-hist-7', name: 'كتاب تاريخ الأردن', nameEn: "Jordan History Book", type: 'students_book' }
        ],
        units: [
          {
            number: 1,
            title: 'حضارات بلاد الشام القديمة على أرض الأردن',
            topics: ['المملكة المؤابية ومسلة ميشع', 'المملكة العمونية في ربة عمون', 'المملكة الإدومية في جنوب الأردن', 'البترا ومملكة الأنباط'],
            sampleExercises: [
              {
                page: 14,
                exerciseNum: 1,
                bookType: 'students_book',
                question: 'ما هي أهمية مسلة ميشع التاريخية؟ وأين عُثر عليها؟',
                answer: 'أهميتها: تُعد أهم وثيقة تاريخية مكتوبة بالخط الفينيقي المؤابي تؤرخ لانتصارات الملك ميشع على بني إسرائيل وتحرير المدن المؤابية. عُثر عليها في بلدة ذيبان بمحافظة مأدبا عام 1868م.',
                explanation: 'مسلة ميشع المحفوظة في متحف اللوفر هي الشاهد التاريخي الأول على الحضارة المؤابية.'
              }
            ]
          }
        ]
      }
    ]
  },
  {
    id: 'grade-10',
    name: 'الصف العاشر الأساسي',
    nameEn: 'Grade 10',
    stage: 'middle',
    subjects: [
      {
        id: 'english-10',
        name: 'اللغة الإنجليزية (Action Pack 10)',
        nameEn: 'English (Action Pack 10)',
        isEnglish: true,
        books: [
          { id: 'sb-10', name: 'كتاب الطالب (Student\'s Book)', nameEn: "Student's Book", type: 'students_book' },
          { id: 'ab-10', name: 'كتاب الأنشطة والتمارين (Activity Book)', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'Starting Out / The power of ideas',
            titleEn: 'Starting Out / The power of ideas',
            topics: ['Present Simple, Continuous and Perfect', 'Stative verbs vs Dynamic verbs', 'Reading: Ibn Battuta and travelers', 'Writing an essay'],
            sampleExercises: [
              {
                page: 8,
                exerciseNum: 3,
                bookType: 'activity_book',
                question: 'Complete the dialogue with Present Perfect Simple or Continuous: 1. How long (you / study) English? 2. I (read) three books this month.',
                answer: '1. How long have you been studying English?\n2. I have read three books this month.',
                explanation: '"How long" emphasizes the duration of an ongoing action (Present Perfect Continuous). Stating the quantity ("three books") requires Present Perfect Simple.'
              },
              {
                page: 12,
                exerciseNum: 5,
                bookType: 'activity_book',
                question: 'Choose the correct form: I (think / am thinking) of visiting Petra this weekend. / I (think / am thinking) it is a good idea.',
                answer: 'am thinking (mental action/consideration), think (opinion/stative verb).',
                explanation: 'Stative verbs like "think" meaning "believe" are not used in continuous forms, but when expressing a mental process of planning, continuous is allowed.'
              }
            ]
          },
          {
            number: 4,
            title: 'Science and Technology',
            titleEn: 'Science and Technology',
            topics: ['Passive Voice (Present and Past)', 'Relative Clauses (defining and non-defining)', 'Medical breakthroughs'],
            sampleExercises: [
              {
                page: 30,
                exerciseNum: 2,
                bookType: 'activity_book',
                question: 'Rewrite in the passive voice: "Alexander Fleming discovered penicillin in 1928."',
                answer: 'Penicillin was discovered by Alexander Fleming in 1928.',
                explanation: 'Object (Penicillin) + was/were + past participle (discovered) + agent (by ...).'
              }
            ]
          }
        ]
      },
      {
        id: 'math-10',
        name: 'الرياضيات (الصف العاشر)',
        nameEn: 'Mathematics',
        isEnglish: false,
        books: [
          { id: 'sb-m-10', name: 'كتاب الطالب', nameEn: "Student's Book", type: 'students_book' },
          { id: 'ab-m-10', name: 'كتاب التمارين والأنشطة', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'الأسس والمعادلات والمتباينات',
            topics: ['حل نظام مكون من معادلة خطية وتربيعية', 'حل نظام مكون من معادلتين تربيعيتين', 'المعادلات الأسية'],
            sampleExercises: [
              {
                page: 16,
                exerciseNum: 4,
                bookType: 'activity_book',
                question: 'حل نظام المعادلات التالي: y = x^2 - 2x + 1 ، y = x + 1',
                answer: 'مجموعة الحل: (0, 1) و (3, 4)',
                explanation: 'بمساواة المعادلتين: x^2 - 2x + 1 = x + 1 => x^2 - 3x = 0 => x(x - 3) = 0. إما x = 0 ومنها y = 1، أو x = 3 ومنها y = 4.'
              }
            ]
          }
        ]
      },
      {
        id: 'physics-10',
        name: 'الفيزياء',
        nameEn: 'Physics',
        isEnglish: false,
        books: [
          { id: 'sb-ph-10', name: 'كتاب الفيزياء', nameEn: "Physics Book", type: 'students_book' }
        ],
        units: [
          {
            number: 1,
            title: 'المتجهات والحركة بتسارع ثابت',
            topics: ['تحليل المتجهات (المركبة السينية والصادية)', 'معادلات الحركة في خط مستقيم', 'حركة المقذوفات'],
            sampleExercises: [
              {
                page: 24,
                exerciseNum: 2,
                bookType: 'students_book',
                question: 'انطلقت سيارة من السكون بتسارع ثابت مقداره 2 m/s²، احسب سرعتها بعد 5 ثوانٍ، والمسافة التي قطعتها.',
                answer: 'السرعة النهائية: v2 = v1 + a*t = 0 + (2)(5) = 10 m/s.\nالمسافة: Δx = v1*t + 0.5*a*t² = 0 + 0.5*(2)*(25) = 25 m.',
                explanation: 'نطبق معادلتي الحركة بتسارع ثابت مع التعويض بـ v1 = 0 لانطلاق السيارة من السكون.'
              }
            ]
          }
        ]
      }
    ]
  },
  {
    id: 'grade-12',
    name: 'الثاني الثانوي - التوجيهي',
    nameEn: 'Tawjihi (Grade 12)',
    stage: 'tawjihi',
    subjects: [
      {
        id: 'english-12',
        name: 'اللغة الإنجليزية المشتركة (Action Pack 12)',
        nameEn: 'English Action Pack 12',
        isEnglish: true,
        books: [
          { id: 'sb-12', name: 'كتاب الطالب (Student\'s Book)', nameEn: "Student's Book", type: 'students_book' },
          { id: 'ab-12', name: 'كتاب الأنشطة والتمارين (Activity Book)', nameEn: 'Activity Book', type: 'activity_book' }
        ],
        units: [
          {
            number: 1,
            title: 'Information Technology (تكنولوجيا المعلومات)',
            titleEn: 'Information Technology',
            topics: [
              'Tenses Revision (Present, Past, Future, Continuous, Perfect)',
              'Reported Speech',
              'Passive Voice in various tenses',
              'Causative Verbs (have/get something done)',
              'Vocabulary: smartphone, calculation, floppy disk, privacy settings, whiteboards',
              'Collocations & Phrasal Verbs'
            ],
            sampleExercises: [
              {
                page: 7,
                exerciseNum: 2,
                bookType: 'activity_book',
                question: 'Complete the sentences using the Causative form: 1. I didn\'t repair my computer myself; I _____ (it / repair) by a technician.',
                answer: 'had it repaired',
                explanation: 'Form: Subject + had + object + V3 (past participle). Because the original sentence is in the past ("didn\'t repair"), we use "had it repaired".'
              },
              {
                page: 10,
                exerciseNum: 4,
                bookType: 'activity_book',
                question: 'Report the following sentence: "We have tested all the medical equipment," said the doctor.',
                answer: 'The doctor said that they had tested all the medical equipment.',
                explanation: 'In reported speech, Present Perfect ("have tested") shifts one tense back to Past Perfect ("had tested"), and pronoun "we" shifts to "they".'
              },
              {
                page: 14,
                exerciseNum: 1,
                bookType: 'activity_book',
                question: 'Derivation: Complete with the correct word form: "The company made a great _____ in solar technology." (invent / invention / inventive)',
                answer: 'invention',
                explanation: 'After the adjective "great", a noun is required. The noun form of "invent" is "invention".'
              }
            ]
          },
          {
            number: 2,
            title: 'An active life / Complementary Medicine',
            titleEn: 'An active life / Complementary Medicine',
            topics: [
              'Used to vs Be used to',
              'Past Perfect Continuous',
              'Health and Medicine vocabulary: acupuncture, homeopathy, ailment, immunisation'
            ],
            sampleExercises: [
              {
                page: 18,
                exerciseNum: 3,
                bookType: 'activity_book',
                question: 'Choose the correct option: When I was a child, I (used to / am used to) ride a bike every afternoon.',
                answer: 'used to',
                explanation: '"used to + infinitive" describes past repeated habits that no longer happen. "be used to + V-ing/noun" means accustomed to something in the present.'
              }
            ]
          },
          {
            number: 6,
            title: 'Education Today (التعليم اليوم)',
            titleEn: 'Education Today',
            topics: [
              'Comparative and Superlative (more than, as... as, less than)',
              'Indirect Questions (Could you tell me..., Do you know...)',
              'Higher Education vocabulary: degree, undergraduate, postgraduate, PhD'
            ],
            sampleExercises: [
              {
                page: 38,
                exerciseNum: 2,
                bookType: 'activity_book',
                question: 'Rewrite as an Indirect Question: "Where is the nearest library?" -> Could you tell me _____?',
                answer: 'Could you tell me where the nearest library is?',
                explanation: 'In indirect questions, the word order returns to statement order (subject before auxiliary verb): where + the nearest library + is.'
              }
            ]
          }
        ]
      },
      {
        id: 'history-12',
        name: 'تاريخ الأردن (توجيهي مشترك)',
        nameEn: 'Jordan History (Tawjihi)',
        isEnglish: false,
        books: [
          { id: 'sb-hist-12', name: 'كتاب تاريخ الأردن المقرر', nameEn: "Jordan History Textbook", type: 'students_book' }
        ],
        units: [
          {
            number: 1,
            title: 'استقلال المملكة الأردنية الهاشمية وتطور الدستور',
            topics: ['إمارة شرق الأردن 1921', 'المعاهدة الأردنية البريطانية 1928', 'إعلان الاستقلال في 25 أيار 1946', 'الدساتير الأردنية (1928، 1946، 1952)'],
            sampleExercises: [
              {
                page: 22,
                exerciseNum: 1,
                bookType: 'students_book',
                question: 'بين القرارات التاريخية التي اتخذها المجلس التشريعي الأردني في 25 أيار 1946م.',
                answer: '1. إعلان بلاد الأردن دولة مستقلة استقلالاً تاماً ذات سيادة.\n2. البيعة لسمو الأمير عبد الله بن الحسين ملكاً دستورياً على البلاد.\n3. تعديل القانون الأساسي (الدستور) بما يتوافق مع الوضع الجديد للمملكة.',
                explanation: 'يعتبر يوم 25 أيار 1946 يوماً مفصلياً أعلن فيه الاستقلال وتحولت الإمارة إلى المملكة الأردنية الهاشمية.'
              }
            ]
          }
        ]
      },
      {
        id: 'islamic-12',
        name: 'التربية الإسلامية (توجيهي مشترك)',
        nameEn: 'Islamic Education',
        isEnglish: false,
        books: [
          { id: 'sb-is-12', name: 'كتاب التربية الإسلامية', nameEn: "Islamic Education Textbook", type: 'students_book' }
        ],
        units: [
          {
            number: 1,
            title: 'العقيدة الإسلامية والتشريع',
            topics: ['الوقف في الإسلام', 'التطرف الفكري وخطره', 'حقوق الإنسان في الإسلام'],
            sampleExercises: [
              {
                page: 15,
                exerciseNum: 3,
                bookType: 'students_book',
                question: 'عرف الوقف في الشريعة الإسلامية، واذكر نوعيه الرئيسين.',
                answer: 'الوقف: حبس الأصل وتسبيل المنفعة لعمل الخير تقرباً إلى الله تعالى.\nنوعاه: 1. الوقف الخيري (العام)  2. الوقف الذري (الأهلي الخاص بالأبناء والأقارب).',
                explanation: 'الوقف من الصدقات الجارية المستمرة بعد وفاة الإنسان.'
              }
            ]
          }
        ]
      }
    ]
  }
];

// Helper to check subject topic relevance
export function evaluateCurriculumRelevance(
  subjectId: string,
  query: string
): { isRelevant: boolean; reason?: string } {
  const q = query.trim().toLowerCase();

  // If asking for a page or exercise solution, it's ALWAYS relevant to curriculum!
  const hasPageOrExPattern = /(صفحة|صفحه|ص\s*\d+|تمرين|سؤال|question|ex|exercise|page|p\.\s*\d+)/i.test(q);
  if (hasPageOrExPattern) {
    return { isRelevant: true };
  }

  // Cross-discipline check (e.g. asking biology in history)
  if (subjectId.includes('history') || subjectId.includes('تاريخ')) {
    const scienceKeywords = ['دورة الماء', 'التمثيل الضوئي', 'خلية', 'نيوتن', 'تسارع', 'تفاعل كيميائي', 'photosynthesis', 'water cycle', 'dna', 'الذرة', 'الجدول الدوري'];
    for (const kw of scienceKeywords) {
      if (q.includes(kw)) {
        return {
          isRelevant: false,
          reason: `هذا السؤال عن (${kw}) يتعلق بمادة العلوم / الكيمياء / الفيزياء، ولا علاقة له بمنهاج تاريخ الأردن.`
        };
      }
    }
  }

  if (subjectId.includes('islamic') || subjectId.includes('إسلامية')) {
    const scienceOrMath = ['تكامل', 'تفاضل', 'قوانين نيوتن', 'لوغاريتم', 'الاحتمالات المشروطة'];
    for (const kw of scienceOrMath) {
      if (q.includes(kw)) {
        return {
          isRelevant: false,
          reason: `هذا السؤال عن (${kw}) يتعلق بمادة الرياضيات أو العلوم، ولا يقع ضمن مباحث مادة التربية الإسلامية.`
        };
      }
    }
  }

  if (subjectId.includes('math') || subjectId.includes('رياضيات')) {
    const histKeywords = ['معركة حطين', 'مسلة ميشع', 'الاستقلال 1946', 'الشريف الحسين بن علي'];
    for (const kw of histKeywords) {
      if (q.includes(kw)) {
        return {
          isRelevant: false,
          reason: `هذا السؤال عن (${kw}) تاريخي، ولا صلة له بمنهاج الرياضيات المقررة.`
        };
      }
    }
  }

  // Otherwise, default to relevant so AI can provide educational help
  return { isRelevant: true };
}
