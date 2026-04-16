import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { MdCameraAlt, MdHistory, MdCheckCircle, MdChat, MdInfoOutline, MdDeleteOutline } from 'react-icons/md';
import { useAuth } from '@/context/AuthContext';
import { useNavigate } from 'react-router-dom';

const REGIONS = [
  "서울", "인천", "대전", "대구", "광주", "부산", "울산", "세종",
  "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"
];

const CROPS = [
  "감자", "고추", "참깨", "파", "배추", "콩", "양배추", "오이", "옥수수", "팥", "토마토", "벼"
];

const PESTS = [
  "해충없음", "벼룩잎벌레", "비단노린재", "이십팔점박이무당벌레", "참외덩굴무늬벌레",
  "배추흰나비", "먹노린재", "배추좀나방", "톱다리개미허리노린재", "파밤나방",
  "담배가루이", "담배거세미나방", "복숭아혹진딧물", "무잎벌", "목화바둑명나방",
  "꽃노랑총채벌레", "검거세미밤나방", "도둑나방"
];

const API_BASE = 'http://localhost:8000/api/v1/diagnosis';

const TIPS = [
  "작물의 잎 이면까지 꼼꼼히 촬영하면 더 정확한 해충 진단이 가능합니다.",
  "해충 발견 즉시 사진을 찍어 진단하면 피해를 최소화할 수 있습니다.",
  "바람이 부는 날에는 농약 살포를 피하는 것이 좋습니다.",
  "서로 다른 약제를 혼용할 때는 반드시 제품 라벨의 혼용 가이드를 확인하세요.",
  "비가 온 직후에는 병해가 확산될 수 있으니 작물을 꼼꼼히 살피세요.",
  "농약은 권장 희석 배수를 정확히 지켜야 작물 약해를 예방할 수 있습니다.",
  "해충 방제는 예찰을 통한 초기 대응이 가장 효과적입니다.",
  "수확을 앞둔 작물은 잔류 농약 안전 기준을 위해 사용 가능 시기를 꼭 확인하세요.",
  "노린재류는 주로 아침, 저녁 시간에 잎 뒷면에 숨어 활동합니다.",
  "시설 하우스에서는 주기적인 환기로 습도를 낮춰 곰팡이병을 예방하세요.",
  "NCPMS 방제 지침은 국가 공인 데이터를 기반으로 작성됩니다.",
  "기상청 데이터 연동을 통해 현재 날씨에 맞는 최적의 살포 시기를 추천합니다."
];

export default function DiagnosisPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [selectedRegion, setSelectedRegion] = useState("");
  const [selectedCrop, setSelectedCrop] = useState("");
  const [testPest, setTestPest] = useState(PESTS[1]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStep, setAnalysisStep] = useState(0);
  const [randomTip, setRandomTip] = useState(TIPS[0]);
  const [history, setHistory] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_BASE}/history`, { credentials: 'include' });
      if (!response.ok) throw new Error('Failed to fetch');
      const data = await response.json();
      setHistory(data);
    } catch (error) {
      console.error("Failed to fetch history:", error);
    }
  };

  useEffect(() => {
    if (user) {
      const displayRegion = user.location_category || "서울";
      setSelectedRegion(displayRegion);
      setSelectedCrop(user.main_crop || "배추");
      fetchHistory();
    }
  }, [user]);

  const toggleSelect = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === history.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(history.map(h => h.id));
    }
  };

  const deleteSelected = async () => {
    if (selectedIds.length === 0) return;
    
    try {
      await Promise.all(
        selectedIds.map(id => 
          fetch(`${API_BASE}/history/${id}`, {
            method: 'DELETE',
            credentials: 'include',
          })
        )
      );
      setHistory(prev => prev.filter(h => !selectedIds.includes(h.id)));
      setSelectedIds([]);
    } catch (error) {
      console.error("Delete failed:", error);
    }
  };

  const deleteOne = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      const response = await fetch(`${API_BASE}/history/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Delete failed');
      setHistory(prev => prev.filter(h => h.id !== id));
      setSelectedIds(prev => prev.filter(i => i !== id));
    } catch (error) {
      console.error("Delete failed:", error);
    }
  };

  const startDiagnosis = (isTest = false) => {
    setIsAnalyzing(true);
    setAnalysisStep(0);
    setRandomTip(TIPS[Math.floor(Math.random() * TIPS.length)]);

    const steps = [
      "이미지 특징점 추출 중...",
      "해충 데이터베이스 매칭 중...",
      "AI 모델 분석 결과 생성 중...",
      "작물 및 기상 데이터 결합 중..."
    ];

    let currentStep = 0;
    // API 실제 호출 시간에 맞춰 로딩 표기를 순환 (최소한 1번씩은 보여주도록)
    const interval = setInterval(() => {
      currentStep = (currentStep + 1);
      if (currentStep < steps.length - 1) {
        setAnalysisStep(currentStep);
      }
    }, 2000);

    const payload = {
      pest: isTest ? testPest : "벼룩잎벌레",
      crop: selectedCrop || "배추",
      region: selectedRegion || "서울"
    };

    // 실시간으로 API 호출 연동, 딜레이 없이 바로 요청
    fetch(`${API_BASE}/history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload)
    })
    .then(async (res) => {
      clearInterval(interval);
      setAnalysisStep(steps.length - 1); // 마지막 단계 도달
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Save failed');
      }
      const savedData = await res.json();
      await fetchHistory();
      navigate('/diagnosis/chat', { state: { diagnosisContext: savedData } });
    })
    .catch(err => {
      console.error("Save error:", err);
      clearInterval(interval);
      navigate('/diagnosis/chat', { state: { diagnosisContext: payload } });
    });
  };

  const onDrop = useCallback(() => {
    startDiagnosis(false);
  }, [selectedCrop, selectedRegion]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpg', '.jpeg', '.png'] },
    maxFiles: 1,
  });

  const isAutoFilled = user?.location && user?.main_crop;

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-20">
      <div className="card bg-white border border-gray-100 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
            <MdInfoOutline className="text-primary" />
            진단 환경 설정
          </h2>
          {isAutoFilled && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-green-50 text-green-600 text-xs font-bold rounded-full border border-green-100">
              <MdCheckCircle className="text-sm" />
              내 농장 정보 적용됨
            </span>
          )}
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-gray-400 ml-1">지역 (기상청 연동)</label>
            <select 
              value={selectedRegion} 
              onChange={(e) => setSelectedRegion(e.target.value)}
              className="w-full p-3 rounded-xl border border-gray-200 bg-gray-50 focus:bg-white focus:ring-2 focus:ring-primary/20 transition-all outline-none cursor-pointer"
            >
              <option value="" disabled>지역 선택</option>
              {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-gray-400 ml-1">작물 (농약 안전정보 연동)</label>
            <select 
              value={selectedCrop} 
              onChange={(e) => setSelectedCrop(e.target.value)}
              className="w-full p-3 rounded-xl border border-gray-200 bg-gray-50 focus:bg-white focus:ring-2 focus:ring-primary/20 transition-all outline-none cursor-pointer"
            >
              <option value="" disabled>작물 선택</option>
              {CROPS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>
      </div>

      <div
        {...getRootProps()}
        className={`card border-2 border-dashed cursor-pointer transition-all text-center py-16 ${
          isDragActive ? 'border-primary bg-primary/5' : 'border-gray-200 hover:border-primary/40 hover:bg-gray-50/50'
        }`}
      >
        <input {...getInputProps()} />
        <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
          <MdCameraAlt className="text-4xl text-primary" />
        </div>
        <p className="text-xl font-bold text-gray-800">
          {isDragActive ? '여기에 사진을 놓으세요!' : '해충 사진을 업로드하세요'}
        </p>
        <p className="text-sm text-gray-400 mt-2 max-w-xs mx-auto">
          작물의 특징이나 해충이 잘 보이도록 근접 촬영한 사진일수록 정확합니다
        </p>
        <div className="flex justify-center">
          <button className="btn-primary mt-6 !px-8">
            사진 선택하기
          </button>
        </div>
      </div>

      <div className="card bg-amber-50/50 border border-amber-100 border-dashed">
        <div className="flex items-center gap-2 mb-4 text-amber-700 font-bold text-sm">
          <span className="px-2 py-0.5 bg-amber-200 rounded-md text-[10px]">FIXED</span>
          임시 VLM 진단 테스트 (해충 강제 지정)
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <select 
            value={testPest} 
            onChange={(e) => setTestPest(e.target.value)}
            className="flex-1 p-3 rounded-xl border border-amber-200 bg-white focus:ring-2 focus:ring-amber-200 outline-none cursor-pointer"
          >
            {PESTS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <button 
            onClick={() => startDiagnosis(true)}
            className="bg-amber-500 hover:bg-amber-600 text-white font-bold py-3 px-6 rounded-xl transition-all shadow-sm shadow-amber-200 flex items-center justify-center gap-2 cursor-pointer"
          >
            <MdChat /> 테스트 진단 시작
          </button>
        </div>
      </div>

      <div className="card border border-gray-100">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-gray-100 rounded-lg">
              <MdHistory className="text-xl text-gray-600" />
            </div>
            <h3 className="text-lg font-bold text-gray-800">최근 진단 기록</h3>
          </div>
          
          {history.length > 0 && (
            <div className="flex items-center gap-3">
              <button 
                onClick={toggleSelectAll}
                className="text-xs font-bold text-gray-400 hover:text-primary transition-colors cursor-pointer"
              >
                {selectedIds.length === history.length ? "전체 해제" : "전체 선택"}
              </button>
              {selectedIds.length > 0 && (
                <button 
                  onClick={deleteSelected}
                  className="px-3 py-1.5 bg-red-50 text-red-600 text-xs font-bold rounded-lg border border-red-100 hover:bg-red-100 transition-all flex items-center gap-1"
                >
                  <MdDeleteOutline className="text-sm" />
                  {selectedIds.length}개 삭제
                </button>
              )}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3">
          {history.length === 0 ? (
            <div className="py-20 text-center bg-gray-50/50 rounded-2xl border border-dashed border-gray-200">
              <p className="text-gray-400 text-sm">최근 진단 내역이 없습니다.</p>
            </div>
          ) : history.map(record => (
            <div
              key={record.id}
              className={`group relative w-full text-left p-4 rounded-2xl border transition-all cursor-default flex items-center justify-between shadow-sm
                ${selectedIds.includes(record.id) 
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/20' 
                  : 'border-primary/20 bg-white'
                }`}
            >
              <div className="flex items-center gap-4 flex-1">
                <div 
                  onClick={(e) => toggleSelect(e, record.id)}
                  className={`w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-all flex-shrink-0 cursor-pointer
                    ${selectedIds.includes(record.id) 
                      ? 'bg-primary border-primary text-white scale-110' 
                      : 'bg-white border-primary/40'
                    }`}
                >
                  {selectedIds.includes(record.id) && <MdCheckCircle className="text-lg" />}
                </div>

                <div 
                  className="flex-1 space-y-1 cursor-pointer group/content"
                  onClick={() => navigate('/diagnosis/chat', { 
                    state: { 
                      diagnosisContext: record,
                      fromHistory: true 
                    } 
                  })}
                >
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-primary text-white transition-colors">
                      {record.crop}
                    </span>
                    <span className="font-bold text-primary transition-colors">
                      {record.pest}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400">
                    {record.region} · {record.date ? record.date : new Date(record.created_at).toLocaleDateString()} 
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button 
                  onClick={(e) => deleteOne(e, record.id)}
                  className="w-9 h-9 rounded-xl flex items-center justify-center text-red-500 bg-red-50 border border-red-100 transition-all cursor-pointer hover:border-red-500"
                  title="기록 삭제"
                >
                  <MdDeleteOutline className="text-xl" />
                </button>
                
                <div 
                  className="flex items-center justify-center w-10 h-10 rounded-full transition-all shadow-sm bg-green-50 text-primary cursor-pointer border border-green-100 hover:border-primary"
                  onClick={() => navigate('/diagnosis/chat', { 
                    state: { 
                      diagnosisContext: record,
                      fromHistory: true 
                    } 
                  })}
                  title="진단 상세 채팅"
                >
                  <MdChat className="text-xl" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <AnimatePresence>
        {isAnalyzing && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-white/90 backdrop-blur-sm"
          >
            <div className="text-center space-y-8 max-w-sm px-6">
              <div className="relative w-32 h-32 mx-auto">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 2, ease: 'linear' }}
                  className="absolute inset-0 border-4 border-primary/10 border-t-primary rounded-full"
                />
                <motion.div
                  animate={{ rotate: -360 }}
                  transition={{ repeat: Infinity, duration: 3, ease: 'linear' }}
                  className="absolute inset-4 border-4 border-primary-light/10 border-b-primary-light rounded-full"
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-4xl animate-bounce">🌱</span>
                </div>
              </div>

              <div className="space-y-3">
                <h2 className="text-2xl font-bold text-gray-800">AI 분석 진행 중</h2>
                <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-primary"
                    initial={{ width: '0%' }}
                    animate={{ width: '100%' }}
                    transition={{ duration: 6 }}
                  />
                </div>
                <p className="text-primary font-medium animate-pulse">
                  { [
                    '이미지 특징점 추출 중...',
                    '해충 데이터베이스 매칭 중...',
                    'AI 모델 분석 결과 생성 중...',
                    '작물 및 기상 데이터 결합 중...'
                  ][analysisStep] }
                </p>
              </div>

              <div className="p-4 bg-primary/5 rounded-2xl border border-primary/10">
                <p className="text-xs text-gray-500 leading-relaxed">
                  <span className="font-bold text-primary block mb-1">💡 알고 계셨나요?</span>
                  {randomTip}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
