import { useRef } from 'react'
import { motion, useScroll, useTransform, useReducedMotion } from 'framer-motion'
import { useI18n } from '../i18n'
import { SectionHeading, Reveal, staggerParent, staggerChild } from './ui'
import { img } from '../assets'

export default function Facility() {
  const { t } = useI18n()
  const ref = useRef<HTMLDivElement>(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] })
  const yImg = useTransform(scrollYProgress, [0, 1], [reduce ? 0 : -30, reduce ? 0 : 30])

  return (
    <section id="facility" ref={ref} className="py-24 md:py-32" style={{ background: 'var(--color-cream)' }}>
      <div className="container-x grid items-center gap-14 lg:grid-cols-[1.15fr_0.85fr]">
        {/* building image */}
        <Reveal>
          <div className="relative overflow-hidden rounded-[1.75rem]" style={{ boxShadow: 'var(--shadow-lift)' }}>
            <motion.img
              src={img.buildingSign}
              alt={t.facility.imageAlt}
              style={{ y: yImg, scale: 1.08 }}
              className="aspect-[16/11] w-full object-cover"
              loading="lazy"
            />
            <div className="absolute inset-0" style={{ background: 'linear-gradient(120deg, rgba(44,36,32,0) 60%, rgba(44,36,32,0.18))' }} />
            {/* corner label echoing the real red sign */}
            <div className="absolute bottom-5 start-5 rounded-xl px-4 py-2" style={{ background: 'color-mix(in srgb, var(--color-paper) 80%, transparent)', backdropFilter: 'blur(10px)', border: '1px solid color-mix(in srgb, var(--color-gold) 40%, transparent)' }}>
              <span className="text-xs font-semibold tracking-wide" style={{ color: 'var(--color-espresso)' }}>{t.hero.facilityChip}</span>
            </div>
          </div>
        </Reveal>

        {/* content */}
        <div>
          <SectionHeading kicker={t.facility.kicker} title={t.facility.title} subtitle={t.facility.subtitle} />
          <motion.div
            variants={staggerParent}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: '-60px' }}
            className="mt-9 grid grid-cols-2 gap-3"
          >
            {t.facility.points.map((p) => (
              <motion.div
                key={p.label}
                variants={staggerChild}
                className="rounded-2xl px-5 py-4"
                style={{ background: 'var(--color-paper)', border: '1px solid color-mix(in srgb, var(--color-gold-deep) 18%, transparent)' }}
              >
                <div className="font-display text-2xl" style={{ color: 'var(--color-gold-deep)' }}>{p.value}</div>
                <div className="mt-1 text-xs leading-snug" style={{ color: 'color-mix(in srgb, var(--color-espresso) 66%, transparent)' }}>{p.label}</div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  )
}
