import { motion } from 'framer-motion'
import { useI18n } from '../i18n'
import { SectionHeading, Reveal, staggerParent, staggerChild } from './ui'

export default function Services() {
  const { t } = useI18n()
  return (
    <section id="services" className="py-24 md:py-32" style={{ background: 'var(--color-paper)' }}>
      <div className="container-x">
        <SectionHeading kicker={t.services.kicker} title={t.services.title} subtitle={t.services.subtitle} />

        <motion.div
          variants={staggerParent}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-80px' }}
          className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-4"
        >
          {t.services.steps.map((s) => (
            <motion.div key={s.n} variants={staggerChild} className="card group relative flex flex-col p-7">
              <div className="flex items-baseline justify-between">
                <span className="font-display text-5xl" style={{ color: 'color-mix(in srgb, var(--color-gold) 70%, transparent)' }}>{s.n}</span>
                <span className="h-2 w-2 rounded-full transition-transform duration-500 group-hover:scale-[2.5]" style={{ background: 'var(--color-gold)' }} />
              </div>
              <h3 className="mt-6 text-xl" style={{ color: 'var(--color-espresso)' }}>{s.title}</h3>
              <p className="mt-3 text-sm leading-relaxed" style={{ color: 'color-mix(in srgb, var(--color-espresso) 65%, transparent)' }}>{s.text}</p>
            </motion.div>
          ))}
        </motion.div>

        <Reveal delay={0.1} className="mt-8">
          <div className="h-px w-full" style={{ background: 'linear-gradient(90deg, transparent, color-mix(in srgb, var(--color-gold) 45%, transparent), transparent)' }} />
        </Reveal>
      </div>
    </section>
  )
}
