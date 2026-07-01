import type { DeepPartial, Dict } from './types'

// 한국어 — 핵심 UI 문구; 미번역 키는 영어로 대체됩니다.
const ko: DeepPartial<Dict> = {
  meta: { dir: 'ltr', label: '한국어' },
  nav: { services: '서비스', products: '제품', quality: '품질', process: '프로세스', exhibitions: '행사', contact: '문의', cta: '무료 브리프' },
  hero: {
    badge: '유럽 위탁 제조사 · GMP · ISO 13485',
    kineticLead: '귀사의',
    kineticTail: '을(를) 귀사 브랜드로 제조합니다.',
    titleLead: '컨셉에서',
    titleAccent: '출시',
    titleTail: '까지, 당신의 주사 미용 브랜드를 만듭니다.',
    subtitle:
      'Exemera는 주사 미용 제품의 풀사이클 위탁 제조사입니다 — 더멀 필러, 바이오리비탈라이저, 메조테라피 칵테일, 메디컬 필. 개발·제조·인허가·물류를 모두 귀사의 브랜드로 제공합니다.',
    ctaPrimary: '무료 브리프 받기',
    ctaSecondary: '프로세스 보기',
    trust: ['ISO 13485 인증', 'GMP 제조', 'Class B 클린룸 · ISO 7'],
    facilityChip: '자사 GMP 시설 · 유럽',
  },
  facility: {
    kicker: '자사 시설',
    title: '중개자가 아닌, 실제 유럽 공장',
    subtitle: '한 지붕 아래 풀사이클 생산: R&D 실험실, GMP 클린룸, 무균 충전, 품질 관리 — 귀사 브랜드를 뒷받침하는 시설입니다.',
  },
  services: {
    kicker: '턴키 서비스', title: '포뮬러에서 선반까지',
    subtitle: '자체 주사 미용 브랜드를 출시하는 투명한 여정 — 4단계, 하나의 파트너.',
  },
  advantages: { kicker: '왜 Exemera인가', title: '출시 리스크를 낮추는 강점' },
  products: {
    kicker: '제품 카테고리', title: '종합 주사 제품 포트폴리오',
    subtitle: '기성 포뮬러를 선택하거나 완전 맞춤 개발을 의뢰하세요.',
    categories: [
      { name: 'HA 더멀 필러' }, { name: '바이오리비탈라이저' }, { name: '메조테라피 칵테일' }, { name: '메디컬 필' },
    ],
  },
  quality: { kicker: '품질 관리', title: '모든 단계에서 의약품 등급' },
  video: { kicker: '시설 내부', title: '정밀 엔지니어링, 의약품급 무균', cta: '재생' },
  timeline: { kicker: '작업 방식', title: '일반적인 생산 일정' },
  exhibitions: { kicker: '만나요', title: '세계 유수의 행사에서 만나요' },
  contact: {
    kicker: '프로젝트 시작', title: '무료 포뮬레이션 브리프 받기',
    subtitle: '양식을 작성하시면 48시간 내에 맞춤 브리프를 준비해 드립니다 — 부담 없이.',
    form: {
      name: '성명', company: '회사명', email: '업무 이메일', category: '제품 카테고리', categoryPh: '카테고리 선택',
      market: '목표 시장', message: '프로젝트 소개', submit: '무료 브리프 받기',
      consent: '제출 시 개인정보 처리방침에 동의합니다.', success: '감사합니다 — 48시간 내에 브리프를 준비하겠습니다.',
    },
    callback: '콜백 요청', whatsapp: 'WhatsApp으로 문의', telegram: 'Telegram으로 문의',
  },
  footer: { tagline: '귀사의 브랜드로 주사 미용 제품을 위탁 제조합니다.', rights: '모든 권리 보유.', made: 'GMP · ISO 13485 · 유럽 제조' },
}

export default ko
