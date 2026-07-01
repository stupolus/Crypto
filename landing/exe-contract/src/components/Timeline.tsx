import { useRef } from 'react'
import { motion, useScroll, useTransform } from 'framer-motion'
import { useI18n } from '../i18n'
import { SectionHeading } from './ui'

export default function Timeline() {
  const { t } = useI18n()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 70%', 'end 60%'] })
  const lineH = useTransform(scrollYProgress, [0, 1], ['0%', '100%'])

  return (
    <section id="process" className="py-24 md:py-32" style={{ background: 'var(--color-cream)' }}>
      <div className="container-x">
        <SectionHeading kicker={t.timeline.kicker} title={t.timeline.title} subtitle={t.timeline.subtitle} />

        <div ref={ref} className="relative mt-16 ms-3">
          {/* track */}
          <div className="absolute start-0 top-0 h-full w-px" style={{ background: 'color-mix(in srgb, var(--color-gold-deep) 22%, transparent)' }} />
          <motion.div className="absolute start-0 top-0 w-px origin-top" style={{ height: lineH, background: 'linear-gradient(var(--color-gold), var(--color-gold-deep))' }} />

          <div className="flex flex-col gap-10">
            {t.timeline.steps.map((s, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: 24 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: '-80px' }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
                className="relative ps-10"
              >
                <span className="absolute -start-[9px] top-1 flex h-[18px] w-[18px] items-center justify-center rounded-full" style={{ background: 'var(--color-cream)', border: '2px solid var(--color-gold)' }}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--color-gold-deep)' }} />
                </span>
                <div className="flex items-baseline gap-3">
                  <span className="font-display text-sm" style={{ color: 'var(--color-gold-deep)' }}>{String(i + 1).padStart(2, '0')}</span>
                  <h3 className="text-xl" style={{ color: 'var(--color-espresso)' }}>{s.title}</h3>
                </div>
                <p className="mt-2 max-w-lg text-sm leading-relaxed" style={{ color: 'color-mix(in srgb, var(--color-espresso) 64%, transparent)' }}>{s.text}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
