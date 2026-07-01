// English — master dictionary. All other locales deep-merge over this,
// so any missing key transparently falls back to English.
const en = {
  meta: { dir: 'ltr', label: 'English' },

  nav: {
    services: 'Service',
    products: 'Products',
    quality: 'Quality',
    process: 'Process',
    exhibitions: 'Events',
    contact: 'Contact',
    cta: 'Request Free Brief',
  },

  hero: {
    badge: 'European contract manufacturer · GMP · ISO 13485',
    titleLead: 'From concept to',
    titleAccent: 'shelf',
    titleTail: 'we build your injectable brand.',
    subtitle:
      'Exemera is a full-cycle contract manufacturer of injectable aesthetics — dermal fillers, biorevitalizants, mesotherapy cocktails and medical peels. Development, manufacturing, regulatory and logistics, all under your brand.',
    ctaPrimary: 'Request your free brief',
    ctaSecondary: 'Explore the process',
    trust: ['ISO 13485 certified', 'GMP manufacturing', 'Cleanroom Class B · ISO 7'],
  },

  stats: {
    items: [
      { value: 12, suffix: '+', label: 'Years of expertise' },
      { value: 60, suffix: '+', label: 'Products in portfolio' },
      { value: 30, suffix: '+', label: 'Countries served' },
      { value: 48, suffix: 'h', label: 'To your custom brief' },
    ],
  },

  services: {
    kicker: 'Turnkey service',
    title: 'From formula to shelf',
    subtitle:
      'A transparent, end-to-end pathway to launching your own injectable aesthetics brand — four stages, one partner.',
    steps: [
      {
        n: '01',
        title: 'R&D Development',
        text: 'Our R&D team creates or adapts a formula tailored to your exact requirements in our proprietary European laboratory.',
      },
      {
        n: '02',
        title: 'GMP Manufacturing',
        text: 'Full-scale production on our certified Class B line with aseptic filling and rigorous multi-level quality control.',
      },
      {
        n: '03',
        title: 'Regulatory Affairs',
        text: 'We handle documentation, certification and product registration in your target markets so you stay compliant.',
      },
      {
        n: '04',
        title: 'Global Logistics',
        text: 'End-to-end delivery of finished products under your brand to any destination worldwide.',
      },
    ],
  },

  advantages: {
    kicker: 'Why Exemera',
    title: 'Advantages that de-risk your launch',
    subtitle:
      'Distinct advantages for brands looking to launch or expand their injectable aesthetics portfolio.',
    items: [
      {
        title: 'Certified Manufacturing',
        text: 'GMP compliance, ISO 13485 quality management, and Cleanroom Class B (ISO 7) production areas.',
      },
      {
        title: 'Scientific Expertise',
        text: 'A proprietary R&D laboratory in Europe staffed by experienced formulation scientists.',
      },
      {
        title: 'Turnkey Service',
        text: 'From concept to delivery: development, manufacturing, regulatory and logistics in one hand.',
      },
      {
        title: 'Trusted Suppliers',
        text: 'Pharmaceutical-grade raw materials from vetted, contractually bound global suppliers.',
      },
    ],
  },

  products: {
    kicker: 'Product categories',
    title: 'A comprehensive injectable portfolio',
    subtitle:
      'Choose from our ready-made formulations or commission fully custom development for your market.',
    categories: [
      {
        name: 'HA Dermal Fillers',
        desc: 'Hyaluronic-acid based injectable fillers for volume, contouring and skin rejuvenation.',
        tags: ['Cross-linked HA', 'Lifting & firming', 'Skin rejuvenation'],
      },
      {
        name: 'Biorevitalizants',
        desc: 'Skin rejuvenation injectables that restore hydration, elasticity and glow.',
        tags: ['Deep hydration', 'Elasticity', 'Barrier recovery'],
      },
      {
        name: 'Mesotherapy Cocktails',
        desc: 'Targeted treatment cocktails formulated for a specific therapeutic effect.',
        tags: ['Hair strengthening', 'Anti-puffiness', 'Lymphatic drainage'],
      },
      {
        name: 'Medical Peels',
        desc: 'Professional peels for resurfacing, tone correction and photoaging.',
        tags: ['Wrinkles & photoaging', 'Acne & inflammation', 'Sensitive skin'],
      },
    ],
  },

  quality: {
    kicker: 'Quality control',
    title: 'Pharmaceutical-grade at every stage',
    subtitle:
      'Every batch undergoes rigorous multi-level quality control in full compliance with international regulatory standards.',
    points: [
      'Aseptic filling line',
      'Cleanroom Class B · ISO 7',
      'Raw material testing',
      'Stability testing',
      'Sterility assurance',
      'Final release inspection',
    ],
    imageAlt: 'GMP-certified cleanroom corridor at the Exemera facility',
  },

  video: {
    kicker: 'Inside the facility',
    title: 'Precision engineering, pharmaceutical sterility',
    subtitle:
      'Watch our aseptic filling line in operation — precision engineering meets pharmaceutical-grade sterility.',
    cta: 'Play film',
  },

  timeline: {
    kicker: 'How we work',
    title: 'Typical production timeline',
    subtitle: 'A clear path from first call to finished product on your shelf.',
    steps: [
      { title: 'Initial consultation', text: 'We discuss your vision, target markets, regulatory needs and specs.' },
      { title: 'Formula development', text: 'Our R&D team creates or adapts a formula to your requirements.' },
      { title: 'Sample approval', text: 'You review and approve samples, specifications, packaging and documentation.' },
      { title: 'Manufacturing', text: 'Production at our GMP-certified Class B facility with multi-level QC.' },
      { title: 'Global delivery', text: 'Worldwide delivery of finished products to any destination.' },
    ],
  },

  exhibitions: {
    kicker: 'Meet us',
    title: 'Find us at the world’s leading events',
    subtitle:
      'Visit our booth at leading international aesthetic-medicine and cosmetics exhibitions.',
    names: ['AMWC', 'IMCAS', 'Cosmoprof Bologna', 'Cosmoprof Asia', 'Dubai Derma', 'Beautyworld ME', 'BeautyIstanbul', 'in-cosmetics Asia'],
  },

  contact: {
    kicker: 'Start your project',
    title: 'Request your free formulation brief',
    subtitle:
      'Fill out the form and our team will prepare your personalised brief within 48 hours — no commitment required.',
    perks: [
      'Personalised product recommendations for your market',
      'Estimated timeline and MOQ for your project',
      'A dedicated personal project manager',
    ],
    form: {
      name: 'Full name',
      namePh: 'Jane Doe',
      company: 'Company name',
      companyPh: 'Your Company Ltd.',
      email: 'Business email',
      emailPh: 'you@company.com',
      category: 'Product category',
      categoryPh: 'Select a category',
      market: 'Target market',
      marketPh: 'e.g. European Union, GCC, LATAM',
      message: 'Tell us about your project',
      messagePh: 'Volumes, timeline, positioning…',
      submit: 'Request free brief',
      consent: 'By submitting, you agree to our privacy policy.',
      success: 'Thank you — we’ll prepare your brief within 48 hours.',
    },
    directTitle: 'Prefer to talk?',
    callback: 'Request a callback',
    callbackNote: 'Leave your number — our team reaches out within one business day.',
    whatsapp: 'Message on WhatsApp',
    telegram: 'Message on Telegram',
  },

  footer: {
    tagline: 'Contract manufacturing of injectable aesthetics, under your brand.',
    rights: 'All rights reserved.',
    made: 'GMP · ISO 13485 · Made in Europe',
    columns: {
      company: 'Company',
      legal: 'Legal',
    },
    links: {
      services: 'Service',
      products: 'Products',
      quality: 'Quality',
      contact: 'Contact',
      privacy: 'Privacy policy',
      imprint: 'Imprint',
    },
  },
}

export default en
export type Dict = typeof en
