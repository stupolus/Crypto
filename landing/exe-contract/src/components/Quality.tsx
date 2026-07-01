import { motion } from 'framer-motion'
import { useI18n } from '../i18n'
import { SectionHeading, Reveal, staggerParent, staggerChild } from './ui'
import { img } from '../assets'

export default function Quality() {
  const { t } = useI18n()
  return (
    <section id="quality" className="py-24 md:py-32" style={{ background: 'var(--color-paper)' }}>
      <div className="container-x grid items-center gap-14 lg:grid-cols-2">
        <Reveal>
          <div className="relative">
            <div className="overflow-hidden rounded-[1.75rem]" style={{ boxShadow: 'var(--shadow-lift)' }}>
              <img src={img.gmpCorridor} alt={t.quality.imageAlt} className="aspect-[4/3] w-full object-cover" loading="lazy" />
            </div>
            <div className="absolute -end-4 -top-4 rounded-2xl px-5 py-4" style={{ background: 'var(--color-espresso)', boxShadow: 'var(--shadow-soft)' }}>
              <div className="font-display text-2xl" style={{ color: 'var(--color-gold)' }}>GMP</div>
              <div className="text-xs" style={{ color: 'color-mix(in srgb, var(--color-cream) 70%, transparent)' }}>ISO 13485</div>
            </div>
          </div>
        </Reveal>

        <div>
          <SectionHeading kicker={t.quality.kicker} title={t.quality.title} subtitle={t.quality.subtitle} />
          <motion.ul
            variants={staggerParent}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: '-60px' }}
            className="mt-9 grid gap-3 sm:grid-cols-2"
          >
            {t.quality.points.map((p) => (
              <motion.li key={p} variants={staggerChild} className="flex items-center gap-3 rounded-xl px-4 py-3" style={{ background: 'var(--color-cream)', border: '1px solid color-mix(in srgb, var(--color-gold-deep) 18%, transparent)' }}>
                <span className="flex h-6 w-6 items-center justify-center rounded-full" style={{ background: 'color-mix(in srgb, var(--color-gold) 22%, transparent)' }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-gold-deep)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                </span>
                <span className="text-sm font-medium" style={{ color: 'var(--color-espresso)' }}>{p}</span>
              </motion.li>
            ))}
          </motion.ul>
        </div>
      </div>
    </section>
  )
}
