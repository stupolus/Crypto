import type { DeepPartial, Dict } from './types'

// Español — parcial; las claves faltantes recurren al inglés.
const es: DeepPartial<Dict> = {
  meta: { dir: 'ltr', label: 'Español' },
  nav: {
    services: 'Servicio',
    products: 'Productos',
    quality: 'Calidad',
    process: 'Proceso',
    exhibitions: 'Eventos',
    contact: 'Contacto',
    cta: 'Brief gratuito',
  },
  hero: {
    badge: 'Fabricante europeo por contrato · GMP · ISO 13485',
    titleLead: 'Del concepto al',
    titleAccent: 'lineal',
    titleTail: 'construimos su marca de inyectables.',
    subtitle:
      'Exemera es un fabricante por contrato de estética inyectable de ciclo completo: rellenos dérmicos, biorevitalizantes, cócteles de mesoterapia y peelings médicos. Desarrollo, fabricación, asuntos regulatorios y logística, bajo su marca.',
    ctaPrimary: 'Solicitar brief gratuito',
    ctaSecondary: 'Ver el proceso',
    trust: ['Certificado ISO 13485', 'Fabricación GMP', 'Sala limpia Clase B · ISO 7'],
  },
  stats: {
    items: [
      { value: 12, suffix: '+', label: 'Años de experiencia' },
      { value: 60, suffix: '+', label: 'Productos en cartera' },
      { value: 30, suffix: '+', label: 'Países atendidos' },
      { value: 48, suffix: 'h', label: 'Para su brief' },
    ],
  },
  services: {
    kicker: 'Servicio integral',
    title: 'De la fórmula al lineal',
    subtitle:
      'Un camino transparente y eficiente para lanzar su propia marca de estética inyectable — cuatro etapas, un socio.',
    steps: [
      { n: '01', title: 'Desarrollo I+D', text: 'Nuestro equipo de I+D crea o adapta una fórmula a sus requisitos en nuestro laboratorio en Europa.' },
      { n: '02', title: 'Fabricación GMP', text: 'Producción a gran escala en nuestra línea Clase B certificada con llenado aséptico y control multinivel.' },
      { n: '03', title: 'Asuntos regulatorios', text: 'Gestionamos documentación, certificación y registro de producto en sus mercados objetivo.' },
      { n: '04', title: 'Logística global', text: 'Entrega mundial de productos terminados bajo su marca a cualquier destino.' },
    ],
  },
  advantages: {
    kicker: 'Por qué Exemera',
    title: 'Ventajas que reducen el riesgo de su lanzamiento',
    subtitle: 'Ventajas claras para marcas que buscan lanzar o ampliar su cartera de estética inyectable.',
    items: [
      { title: 'Fabricación certificada', text: 'Cumplimiento GMP, gestión de calidad ISO 13485 y áreas de sala limpia Clase B (ISO 7).' },
      { title: 'Experiencia científica', text: 'Laboratorio de I+D propio en Europa con científicos de formulación experimentados.' },
      { title: 'Servicio integral', text: 'Del concepto a la entrega: desarrollo, fabricación, regulación y logística en una sola mano.' },
      { title: 'Proveedores de confianza', text: 'Materias primas de grado farmacéutico de proveedores verificados y contractualmente obligados.' },
    ],
  },
  products: {
    kicker: 'Categorías de producto',
    title: 'Una cartera integral de inyectables',
    subtitle: 'Elija entre formulaciones listas o desarrollo completamente personalizado.',
    categories: [
      { name: 'Rellenos de AH', desc: 'Rellenos inyectables a base de ácido hialurónico para volumen, contorno y rejuvenecimiento.', tags: ['AH reticulado', 'Lifting y firmeza', 'Rejuvenecimiento'] },
      { name: 'Biorevitalizantes', desc: 'Inyectables de rejuvenecimiento que restauran hidratación, elasticidad y luminosidad.', tags: ['Hidratación profunda', 'Elasticidad', 'Recuperación de barrera'] },
      { name: 'Cócteles de mesoterapia', desc: 'Cócteles de tratamiento específicos para un efecto terapéutico concreto.', tags: ['Fortalecimiento capilar', 'Antiinflamación', 'Drenaje linfático'] },
      { name: 'Peelings médicos', desc: 'Peelings profesionales para renovación, corrección del tono y fotoenvejecimiento.', tags: ['Arrugas y fotoenvejecimiento', 'Acné', 'Piel sensible'] },
    ],
  },
  quality: {
    kicker: 'Control de calidad',
    title: 'Grado farmacéutico en cada etapa',
    subtitle: 'Cada lote se somete a un riguroso control de calidad multinivel en cumplimiento con los estándares internacionales.',
    points: ['Línea de llenado aséptico', 'Sala limpia Clase B · ISO 7', 'Prueba de materias primas', 'Pruebas de estabilidad', 'Garantía de esterilidad', 'Inspección de liberación final'],
    imageAlt: 'Corredor de sala limpia certificado GMP en Exemera',
  },
  video: {
    kicker: 'Dentro de la planta',
    title: 'Ingeniería de precisión, esterilidad farmacéutica',
    subtitle: 'Vea nuestra línea de llenado aséptico en funcionamiento — precisión y esterilidad de grado farmacéutico.',
    cta: 'Ver vídeo',
  },
  timeline: {
    kicker: 'Cómo trabajamos',
    title: 'Cronograma de producción típico',
    subtitle: 'Un camino claro desde la primera llamada hasta el producto terminado.',
    steps: [
      { title: 'Consulta inicial', text: 'Hablamos de su visión, mercados objetivo, requisitos regulatorios y especificaciones.' },
      { title: 'Desarrollo de fórmula', text: 'Nuestro equipo de I+D crea o adapta una fórmula a sus requisitos.' },
      { title: 'Aprobación de muestras', text: 'Revisa y aprueba muestras, especificaciones, empaque y documentación.' },
      { title: 'Fabricación', text: 'Producción en nuestra planta Clase B certificada GMP con control multinivel.' },
      { title: 'Entrega global', text: 'Entrega mundial de productos terminados a cualquier destino.' },
    ],
  },
  exhibitions: {
    kicker: 'Encuéntrenos',
    title: 'Estamos en los eventos líderes del mundo',
    subtitle: 'Visite nuestro stand en las principales exposiciones internacionales de medicina estética y cosmética.',
  },
  contact: {
    kicker: 'Inicie su proyecto',
    title: 'Solicite su brief de formulación gratuito',
    subtitle: 'Complete el formulario y nuestro equipo preparará su brief personalizado en 48 horas — sin compromiso.',
    perks: [
      'Recomendaciones de producto personalizadas para su mercado',
      'Cronograma estimado y MOQ para su proyecto',
      'Un gerente de proyecto personal dedicado',
    ],
    form: {
      name: 'Nombre completo', namePh: 'Juan Pérez',
      company: 'Nombre de la empresa', companyPh: 'Su Empresa S.L.',
      email: 'Email empresarial', emailPh: 'usted@empresa.com',
      category: 'Categoría de producto', categoryPh: 'Seleccione una categoría',
      market: 'Mercado objetivo', marketPh: 'p. ej. UE, GCC, LATAM',
      message: 'Cuéntenos sobre su proyecto', messagePh: 'Volúmenes, plazos, posicionamiento…',
      submit: 'Solicitar brief gratuito',
      consent: 'Al enviar, acepta nuestra política de privacidad.',
      success: 'Gracias — prepararemos su brief en 48 horas.',
    },
    directTitle: '¿Prefiere hablar?',
    callback: 'Solicitar llamada',
    callbackNote: 'Deje su número — le contactamos en un día hábil.',
    whatsapp: 'Escribir por WhatsApp',
    telegram: 'Escribir por Telegram',
  },
  footer: {
    tagline: 'Fabricación por contrato de estética inyectable, bajo su marca.',
    rights: 'Todos los derechos reservados.',
    made: 'GMP · ISO 13485 · Hecho en Europa',
    columns: { company: 'Empresa', legal: 'Legal' },
    links: { services: 'Servicio', products: 'Productos', quality: 'Calidad', contact: 'Contacto', privacy: 'Política de privacidad', imprint: 'Aviso legal' },
  },
}

export default es
