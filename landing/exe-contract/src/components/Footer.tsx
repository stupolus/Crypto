import { useI18n } from '../i18n'
import { LogoMark } from './ui'

export default function Footer() {
  const { t } = useI18n()
  const year = 2026
  return (
    <footer className="relative overflow-hidden pt-20 pb-10" style={{ background: 'var(--color-espresso-deep)' }}>
      <div className="grain absolute inset-0" />
      <div className="container-x relative">
        <div className="grid gap-12 md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <LogoMark tone="cream" className="h-5 w-auto" />
            <p className="mt-5 max-w-xs text-sm leading-relaxed" style={{ color: 'color-mix(in srgb, var(--color-cream) 62%, transparent)' }}>{t.footer.tagline}</p>
            <div className="mt-6 pill" style={{ color: 'var(--color-gold)', width: 'fit-content' }}>{t.footer.made}</div>
          </div>

          <FooterCol title={t.footer.columns.company} links={[
            { label: t.footer.links.services, href: '#services' },
            { label: t.footer.links.products, href: '#products' },
            { label: t.footer.links.quality, href: '#quality' },
            { label: t.footer.links.contact, href: '#contact' },
          ]} />

          <FooterCol title={t.footer.columns.legal} links={[
            { label: t.footer.links.privacy, href: '#' },
            { label: t.footer.links.imprint, href: '#' },
          ]} />
        </div>

        <div className="mt-14 flex flex-col items-center justify-between gap-3 border-t pt-6 text-xs sm:flex-row" style={{ borderColor: 'color-mix(in srgb, var(--color-cream) 12%, transparent)', color: 'color-mix(in srgb, var(--color-cream) 50%, transparent)' }}>
          <span>© {year} Exemera. {t.footer.rights}</span>
          <span>Contract Manufacturing of Injectable Aesthetics</span>
        </div>
      </div>
    </footer>
  )
}

function FooterCol({ title, links }: { title: string; links: { label: string; href: string }[] }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: 'var(--color-gold)' }}>{title}</div>
      <ul className="mt-4 flex flex-col gap-2.5">
        {links.map((l) => (
          <li key={l.label}>
            <a href={l.href} className="text-sm transition-colors" style={{ color: 'color-mix(in srgb, var(--color-cream) 68%, transparent)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-gold)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'color-mix(in srgb, var(--color-cream) 68%, transparent)')}>
              {l.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
