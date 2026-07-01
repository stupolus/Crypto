import { useRef } from 'react'
import { motion, useScroll, useTransform, useReducedMotion } from 'framer-motion'
import { useI18n } from '../i18n'
import { EASE } from './ui'
import { img } from '../assets'

export default function Hero() {
  const { t } = useI18n()
  const ref = useRef<HTMLDivElement>(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] })
  const yImg = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 120])
  const yGlow = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -60])
  const scaleImg = useTransform(scrollYProgress, [0, 1], [1, 1.08])

  const words = t.hero.titleLead.split(' ')

  return (
    <section id="top" ref={ref} className="relative overflow-hidden pt-32 pb-20 md:pt-40 md:pb-28" style={{ background: 'var(--color-cream)' }}>
      {/* soft aurora */}
      <motion.div
        aria-hidden
        style={{ y: yGlow }}
        className="pointer-events-none absolute -top-40 end-[-10%] h-[560px] w-[560px] rounded-full blur-3xl"
      >
        <div className="h-full w-full rounded-full" style={{ background: 'radial-gradient(circle, rgba(196,169,125,0.55), rgba(196,169,125,0) 62%)' }} />
      </motion.div>
      <div aria-hidden className="pointer-events-none absolute -bottom-40 start-[-12%] h-[480px] w-[480px] rounded-full blur-3xl" style={{ background: 'radial-gradient(circle, rgba(139,163,184,0.35), rgba(139,163,184,0) 60%)' }} />

      <div className="container-x relative grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
        {/* copy */}
        <div>
          <motion.span
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE }}
            className="pill"
            style={{ color: 'var(--color-gold-deep)', background: 'color-mix(in srgb, var(--color-gold) 12%, transparent)' }}
          >
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: 'var(--color-gold)' }} />
            {t.hero.badge}
          </motion.span>

          <h1 className="mt-6 text-[clamp(2.6rem,6.2vw,4.9rem)] leading-[1.02]" style={{ color: 'var(--color-espresso)' }}>
            <span className="block overflow-hidden">
              {words.map((w, i) => (
                <motion.span
                  key={i}
                  className="mr-[0.25em] inline-block"
                  initial={{ y: '110%' }}
                  animate={{ y: 0 }}
                  transition={{ duration: 0.9, ease: EASE, delay: 0.1 + i * 0.08 }}
                >
                  {w}
                </motion.span>
              ))}{' '}
              <motion.span
                className="italic text-gradient-gold"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.9, ease: EASE, delay: 0.1 + words.length * 0.08 }}
              >
                {t.hero.titleAccent}
              </motion.span>
              <motion.span
                className="block"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.9, ease: EASE, delay: 0.3 + words.length * 0.08 }}
              >
                {t.hero.titleTail}
              </motion.span>
            </span>
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: EASE, delay: 0.5 }}
            className="mt-7 max-w-xl text-[1.06rem] leading-relaxed"
            style={{ color: 'color-mix(in srgb, var(--color-espresso) 72%, transparent)' }}
          >
            {t.hero.subtitle}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: EASE, delay: 0.62 }}
            className="mt-9 flex flex-wrap items-center gap-3"
          >
            <a href="#contact" className="btn btn-gold">{t.hero.ctaPrimary}</a>
            <a href="#services" className="btn btn-ghost" style={{ color: 'var(--color-espresso)' }}>
              {t.hero.ctaSecondary} <Arrow />
            </a>
          </motion.div>

          <motion.ul
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.8 }}
            className="mt-10 flex flex-wrap gap-x-7 gap-y-3"
          >
            {t.hero.trust.map((item) => (
              <li key={item} className="flex items-center gap-2 text-sm" style={{ color: 'color-mix(in srgb, var(--color-espresso) 66%, transparent)' }}>
                <Check /> {item}
              </li>
            ))}
          </motion.ul>
        </div>

        {/* image */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.1, ease: EASE, delay: 0.2 }}
          className="relative"
        >
          <div className="relative overflow-hidden rounded-[1.75rem]" style={{ boxShadow: 'var(--shadow-lift)' }}>
            <motion.img
              src={img.hero}
              alt="Exemera aseptic filling line"
              style={{ y: yImg, scale: scaleImg }}
              className="aspect-[4/5] w-full object-cover"
              loading="eager"
            />
            <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(44,36,32,0) 55%, rgba(44,36,32,0.45))' }} />
          </div>

          {/* floating glass stat */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease: EASE, delay: 0.9 }}
            className="absolute -bottom-6 start-6 rounded-2xl px-5 py-4"
            style={{
              background: 'color-mix(in srgb, var(--color-paper) 78%, transparent)',
              backdropFilter: 'blur(14px)',
              border: '1px solid color-mix(in srgb, var(--color-gold) 40%, transparent)',
              boxShadow: 'var(--shadow-soft)',
            }}
          >
            <div className="font-display text-3xl" style={{ color: 'var(--color-espresso)' }}>ISO 7</div>
            <div className="text-xs tracking-wide" style={{ color: 'var(--color-gold-deep)' }}>Cleanroom · Class B</div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}

function Arrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="rtl:rotate-180">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}
function Check() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-gold)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  )
}
