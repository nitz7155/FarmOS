import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useScenario } from '@/context/ScenarioContext';
import { useAuth } from '@/context/AuthContext';
import { useSensorData } from '@/hooks/useSensorData';
import { MdArrowForward, MdWifiOff } from 'react-icons/md';

interface ModuleInfo {
  to: string;
  icon: string;
  label: string;
  color: string;
  summary: string;
  status: { color: string; text: string; textColor: string; bgColor: string };
}

const STATIC_MODULES: ModuleInfo[] = [
  {
    to: '/diagnosis',
    icon: '/images/icons/diagnosis.jpg',
    label: '해충 AI 진단',
    color: 'bg-red-50 text-red-600',
    summary: '진단 기능 준비 완료',
    status: { color: 'bg-green-400', text: '준비', textColor: 'text-green-700', bgColor: 'bg-green-50' },
  },
  {
    to: '/reviews',
    icon: '/images/icons/reviews.jpg',
    label: '리뷰 분석 리포트',
    color: 'bg-purple-50 text-purple-600',
    summary: '리뷰 분석',
    status: { color: 'bg-green-400', text: '준비', textColor: 'text-green-700', bgColor: 'bg-green-50' },
  },
  {
    to: '/documents',
    icon: '/images/icons/documents.jpg',
    label: '행정 서류 자동 생성',
    color: 'bg-amber-50 text-amber-600',
    summary: '서류 자동 생성',
    status: { color: 'bg-blue-400', text: '준비', textColor: 'text-blue-700', bgColor: 'bg-blue-50' },
  },
  {
    to: '/weather',
    icon: '/images/icons/weather.jpg',
    label: '기상 연동 스케줄링',
    color: 'bg-cyan-50 text-cyan-600',
    summary: '기상 정보 연동',
    status: { color: 'bg-green-400', text: '준비', textColor: 'text-green-700', bgColor: 'bg-green-50' },
  },
  {
    to: '/harvest',
    icon: '/images/icons/harvest.jpg',
    label: '수확량 예측',
    color: 'bg-green-50 text-green-600',
    summary: '수확 예측 분석',
    status: { color: 'bg-green-400', text: '준비', textColor: 'text-green-700', bgColor: 'bg-green-50' },
  },
  {
    to: '/journal',
    icon: '/images/icons/journal.jpg',
    label: '영농일지',
    color: 'bg-orange-50 text-orange-600',
    summary: '영농 기록 관리',
    status: { color: 'bg-green-400', text: '준비', textColor: 'text-green-700', bgColor: 'bg-green-50' },
  },
];

function getIoTModule(connected: boolean, hasData: boolean): ModuleInfo {
  if (!connected) {
    return {
      to: '/iot',
      icon: '/images/icons/iot-sensors.jpg',
      label: 'IoT 센서 대시보드',
      color: 'bg-gray-100 text-gray-400',
      summary: '서버 연결 안 됨',
      status: { color: 'bg-gray-300', text: '비활성', textColor: 'text-gray-400', bgColor: 'bg-gray-100' },
    };
  }
  if (!hasData) {
    return {
      to: '/iot',
      icon: '/images/icons/iot-sensors.jpg',
      label: 'IoT 센서 대시보드',
      color: 'bg-gray-100 text-gray-400',
      summary: '센서 데이터 없음',
      status: { color: 'bg-yellow-400', text: '대기', textColor: 'text-yellow-700', bgColor: 'bg-yellow-50' },
    };
  }
  return {
    to: '/iot',
    icon: '/images/icons/iot-sensors.jpg',
    label: 'IoT 센서 대시보드',
    color: 'bg-blue-50 text-blue-600',
    summary: '센서 모니터링 중',
    status: { color: 'bg-green-400', text: '정상', textColor: 'text-green-700', bgColor: 'bg-green-50' },
  };
}

export default function DashboardPage() {
  const { currentDay, notifications } = useScenario();
  const { user } = useAuth();
  const { connected, latest } = useSensorData();
  const recentAlerts = notifications.filter(n => !n.read).slice(0, 3);

  const iotModule = getIoTModule(connected, !!latest);
  const inactive = !connected || !latest;
  const MODULES = [iotModule, ...STATIC_MODULES];

  return (
    <div className="space-y-6 max-w-[1200px]">
      {/* Greeting */}
      <div className="card bg-gradient-to-br from-primary to-primary-light text-white !p-5 sm:!p-8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl sm:text-3xl font-bold">안녕하세요, {user?.name}님!</h2>
            <p className="text-white/90 mt-1.5 text-base sm:text-lg">
              FarmOS 2.0 스마트 농장 관리
            </p>
            <p className="text-white/70 mt-1 text-sm">
              시나리오 {currentDay}일차 진행 중
            </p>
          </div>
          <img src="/images/farm-hero.jpg" alt="농장" className="hidden sm:block w-28 h-28 rounded-2xl object-cover shadow-lg" />
        </div>
      </div>

      {/* Module Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-5">
        {MODULES.map(({ to, icon, label, color, summary, status }, index) => {
          const isIoTInactive = to === '/iot' && inactive;
          return (
            <motion.div
              key={to}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.06, ease: 'easeOut' }}
            >
              <Link to={to} className={`card-hover group !p-4 sm:!p-6 block ${isIoTInactive ? 'opacity-60 grayscale' : ''}`}>
                <div className="flex items-start justify-between">
                  <div className={`w-14 h-14 rounded-2xl flex items-center justify-center overflow-hidden ${color}`}>
                    {isIoTInactive ? (
                      <MdWifiOff className="text-2xl text-gray-400" />
                    ) : (
                      <img src={icon} alt={label} className="w-10 h-10 rounded-xl object-cover" />
                    )}
                  </div>
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${status.textColor} ${status.bgColor}`}>
                    <span className={`w-2 h-2 rounded-full ${status.color}`} />
                    {status.text}
                  </span>
                </div>
                <h3 className={`mt-4 text-lg font-bold ${isIoTInactive ? 'text-gray-400' : 'text-gray-900'}`}>{label}</h3>
                <p className={`text-base mt-1 ${isIoTInactive ? 'text-gray-300' : 'text-gray-500'}`}>{summary}</p>
                <div className={`mt-4 flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold transition-all ${
                  isIoTInactive
                    ? 'bg-gray-100 text-gray-400'
                    : 'bg-primary/5 text-primary group-hover:bg-primary group-hover:text-white'
                }`}>
                  바로가기 <MdArrowForward className="text-xl" />
                </div>
              </Link>
            </motion.div>
          );
        })}
      </div>

      {/* Recent Alerts */}
      {recentAlerts.length > 0 && (
        <div className="card !p-6">
          <h3 className="section-title mb-4">최근 알림</h3>
          <div className="space-y-3">
            {recentAlerts.map(n => (
              <div key={n.id} className={`flex items-start gap-4 p-4 rounded-xl ${
                n.type === 'danger' ? 'bg-red-50 border border-red-100' :
                n.type === 'warning' ? 'bg-yellow-50 border border-yellow-100' :
                n.type === 'success' ? 'bg-green-50 border border-green-100' :
                'bg-blue-50 border border-blue-100'
              }`}>
                <span className={`mt-0.5 w-3 h-3 rounded-full flex-shrink-0 ${
                  n.type === 'danger' ? 'bg-danger' :
                  n.type === 'warning' ? 'bg-warning' :
                  n.type === 'success' ? 'bg-success' : 'bg-info'
                }`} />
                <div>
                  <p className="font-semibold text-gray-900">{n.title}</p>
                  <p className="text-sm text-gray-600 mt-0.5">{n.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
