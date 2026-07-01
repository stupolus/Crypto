import type { DeepPartial, Dict } from './types'

// 中文 — 核心界面文案；未翻译的键回退到英文。
const zh: DeepPartial<Dict> = {
  meta: { dir: 'ltr', label: '中文' },
  nav: { services: '服务', products: '产品', quality: '质量', process: '流程', exhibitions: '活动', contact: '联系', cta: '免费方案' },
  hero: {
    badge: '欧洲代工制造商 · GMP · ISO 13485',
    kineticLead: '我们为您生产',
    kineticTail: '以您的品牌交付。',
    titleLead: '从概念到',
    titleAccent: '货架',
    titleTail: '我们打造您的注射美学品牌。',
    subtitle:
      'Exemera 是全流程注射美学代工制造商——真皮填充剂、生物活化剂、中胚层疗法鸡尾酒与医用换肤。研发、生产、法规与物流，全部以您的品牌交付。',
    ctaPrimary: '获取免费方案',
    ctaSecondary: '了解流程',
    trust: ['ISO 13485 认证', 'GMP 生产', 'B 级洁净室 · ISO 7'],
    facilityChip: '我们的 GMP 工厂 · 欧洲',
  },
  facility: {
    kicker: '我们的工厂',
    title: '真实的欧洲工厂——而非中间商',
    subtitle: '一个屋檐下的全流程生产：研发实验室、GMP 洁净室、无菌灌装与质量控制——支撑您品牌的工厂。',
  },
  services: {
    kicker: '一站式服务', title: '从配方到货架',
    subtitle: '透明高效地推出您自己的注射美学品牌——四个阶段，一个伙伴。',
  },
  advantages: { kicker: '为何选择 Exemera', title: '降低上市风险的优势' },
  products: {
    kicker: '产品类别', title: '全面的注射产品组合',
    subtitle: '从现成配方中选择，或委托完全定制的开发。',
    categories: [
      { name: '玻尿酸填充剂' }, { name: '生物活化剂' }, { name: '中胚层鸡尾酒' }, { name: '医用换肤' },
    ],
  },
  quality: { kicker: '质量控制', title: '每一步都达到药品级标准' },
  video: { kicker: '走进工厂', title: '精密工程，药品级无菌', cta: '播放' },
  timeline: { kicker: '合作方式', title: '典型生产周期' },
  exhibitions: { kicker: '与我们相见', title: '在全球领先展会与我们相见' },
  contact: {
    kicker: '启动项目', title: '获取免费配方方案',
    subtitle: '填写表单，我们的团队将在 48 小时内为您准备个性化方案——无需承诺。',
    form: {
      name: '姓名', company: '公司名称', email: '企业邮箱', category: '产品类别', categoryPh: '选择类别',
      market: '目标市场', message: '介绍您的项目', submit: '获取免费方案',
      consent: '提交即表示您同意我们的隐私政策。', success: '感谢您——我们将在 48 小时内准备好方案。',
    },
    callback: '请求回电', whatsapp: '通过 WhatsApp 联系', telegram: '通过 Telegram 联系',
  },
  footer: { tagline: '以您的品牌进行注射美学代工制造。', rights: '版权所有。', made: 'GMP · ISO 13485 · 欧洲制造' },
}

export default zh
