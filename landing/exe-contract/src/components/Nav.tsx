import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useI18n, LANGS, type Lang } from '../i18n'
import { LogoMark, EASE } from './ui'

const CODE: Record<Lang, string> = { en: 'EN', ru: 'RU', es: 'ES', zh: '中', ko: '한', ar: 'ع' }

export default function Nav() {
  const { t, lang, setLang, langLabel } = useI18n()
  const [scrolled, setScrolled] = useState(false)
  const [openLang, setOpenLang] = useState(false)
  const [openMenu, setOpenMenu] = useState(false)
  const langRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (langRef.current && !langRef.current.contains(e.target as Node)) setOpenLang(false)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  const links = [
    { href: '#services', label: t.nav.services },
    { href: '#products', label: t.nav.products },
    { href: '#quality', label: t.nav.quality },
    { href: '#process', label: t.nav.process },
    { href: '#exhibitions', label: t.nav.exhibitions },
  ]

  return (
    <motion.header
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.9, ease: EASE }}
      className="fixed inset-x-0 top-0 z-50"
    >
      <div
        className="transition-all duration-500"
        style={{
          background: scrolled ? 'color-mix(in srgb, var(--color-paper) 82%, transparent)' : 'transparent',
          backdropFilter: scrolled ? 'blur(16px) saturate(140%)' : 'none',
          borderBottom: scrolled
            ? '1px solid color-mix(in srgb, var(--color-gold-deep) 20%, transparent)'
            : '1px solid transparent',
        }}
      >
        <nav className="container-x flex items-center justify-between" style={{ height: scrolled ? 68 : 84, transition: 'height .5s' }}>
          <a href="#top" className="flex items-center gap-2" aria-label="Exemera home">
            <LogoMark tone="espresso" className="h-4 w-auto md:h-[18px]" />
          </a>

          <div className="hidden items-center gap-8 lg:flex">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="text-[0.9rem] font-medium tracking-tight transition-colors"
                style={{ color: 'color-mix(in srgb, var(--color-espresso) 78%, transparent)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-gold-deep)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'color-mix(in srgb, var(--color-espresso) 78%, transparent)')}
              >
                {l.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-3">
            {/* Language switcher */}
            <div className="relative" ref={langRef}>
              <button
                onClick={() => setOpenLang((v) => !v)}
                className="pill font-semibold"
                style={{ color: 'var(--color-espresso)' }}
                aria-haspopup="listbox"
                aria-expanded={openLang}
              >
                <GlobeIcon /> {CODE[lang]}
              </button>
              <AnimatePresence>
                {openLang && (
                  <motion.ul
                    initial={{ opacity: 0, y: 8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.98 }}
                    transition={{ duration: 0.22, ease: EASE }}
                    className="absolute end-0 mt-2 w-44 overflow-hidden rounded-2xl p-1.5"
                    style={{
                      background: 'var(--color-paper)',
                      border: '1px solid color-mix(in srgb, var(--color-gold-deep) 22%, transparent)',
                      boxShadow: 'var(--shadow-lift)',
                    }}
                    role="listbox"
                  >
                    {LANGS.map((l) => (
                      <li key={l}>
                        <button
                          onClick={() => {
                            setLang(l)
                            setOpenLang(false)
                          }}
                          className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm transition-colors"
                          style={{
                            background: l === lang ? 'color-mix(in srgb, var(--color-gold) 18%, transparent)' : 'transparent',
                            color: 'var(--color-espresso)',
                          }}
                        >
                          <span>{langLabel(l)}</span>
                          <span className="opacity-50">{CODE[l]}</span>
                        </button>
                      </li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </div>

            <a href="#contact" className="btn btn-primary hidden md:inline-flex" style={{ padding: '0.7rem 1.25rem' }}>
              {t.nav.cta}
            </a>

            <button className="lg:hidden" aria-label="Menu" onClick={() => setOpenMenu((v) => !v)}>
              <BurgerIcon open={openMenu} />
            </button>
          </div>
        </nav>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {openMenu && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: EASE }}
            className="overflow-hidden lg:hidden"
            style={{ background: 'var(--color-paper)', borderBottom: '1px solid color-mix(in srgb, var(--color-gold-deep) 20%, transparent)' }}
          >
            <div className="container-x flex flex-col gap-1 py-4">
              {links.map((l) => (
                <a key={l.href} href={l.href} onClick={() => setOpenMenu(false)} className="py-2 text-lg" style={{ color: 'var(--color-espresso)' }}>
                  {l.label}
                </a>
              ))}
              <a href="#contact" onClick={() => setOpenMenu(false)} className="btn btn-primary mt-2 w-full">
                {t.nav.cta}
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  )
}

function GlobeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18" />
    </svg>
  )
}

function BurgerIcon({ open }: { open: boolean }) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--color-espresso)" strokeWidth="1.7" strokeLinecap="round">
      {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 8h16M4 16h16" />}
    </svg>
  )
}
