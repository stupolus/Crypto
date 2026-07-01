import { useI18n } from '../i18n'
import { SectionHeading } from './ui'
import { exhibitionLogos } from '../assets'

export default function Exhibitions() {
  const { t } = useI18n()
  const names = t.exhibitions.names
  const row = [...names, ...names] // duplicate for seamless marquee

  return (
    <section id="exhibitions" className="overflow-hidden py-24 md:py-32" style={{ background: 'var(--color-paper)' }}>
      <div className="container-x">
        <SectionHeading kicker={t.exhibitions.kicker} title={t.exhibitions.title} subtitle={t.exhibitions.subtitle} align="center" />
      </div>

      <div className="relative mt-16">
        <div className="pointer-events-none absolute inset-y-0 start-0 z-10 w-24" style={{ background: 'linear-gradient(90deg, var(--color-paper), transparent)' }} />
        <div className="pointer-events-none absolute inset-y-0 end-0 z-10 w-24" style={{ background: 'linear-gradient(270deg, var(--color-paper), transparent)' }} />
        <div className="marquee flex w-max gap-4">
          {row.map((name, i) => (
            <div
              key={i}
              className="flex h-28 w-52 shrink-0 items-center justify-center rounded-2xl px-8"
              style={{ background: 'var(--color-cream)', border: '1px solid color-mix(in srgb, var(--color-gold-deep) 16%, transparent)' }}
              title={name}
            >
              {exhibitionLogos[name] ? (
                <img src={exhibitionLogos[name]} alt={name} className="max-h-14 w-auto max-w-full object-contain" loading="lazy" />
              ) : (
                <span className="text-sm" style={{ color: 'var(--color-espresso)' }}>{name}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      <style>{`
        .marquee { animation: marquee 42s linear infinite; }
        .marquee:hover { animation-play-state: paused; }
        @keyframes marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }
        [dir='rtl'] .marquee { animation-direction: reverse; }
        @media (prefers-reduced-motion: reduce) { .marquee { animation: none; } }
      `}</style>
    </section>
  )
}
