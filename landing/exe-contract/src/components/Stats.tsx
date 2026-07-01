import { useI18n } from '../i18n'
import { Counter, Reveal } from './ui'

export default function Stats() {
  const { t } = useI18n()
  return (
    <section className="relative" style={{ background: 'var(--color-espresso)' }}>
      <div className="grain absolute inset-0" />
      <div className="container-x relative grid grid-cols-2 gap-y-10 py-14 md:py-16 lg:grid-cols-4">
        {t.stats.items.map((s, i) => (
          <Reveal key={i} delay={i * 0.08} className="text-center">
            <div className="font-display text-[clamp(2.4rem,5vw,3.6rem)] leading-none" style={{ color: 'var(--color-cream)' }}>
              <Counter to={s.value} suffix={s.suffix} />
            </div>
            <div className="mt-3 text-sm tracking-wide" style={{ color: 'color-mix(in srgb, var(--color-gold) 85%, white)' }}>
              {s.label}
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}
