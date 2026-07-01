import { useState, type FormEvent } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useI18n } from '../i18n'
import { SectionHeading, Reveal, EASE } from './ui'

export default function Contact() {
  const { t } = useI18n()
  const [sent, setSent] = useState(false)
  const f = t.contact.form

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    // No backend yet — front-end confirmation only. Wire to CRM/email later.
    setSent(true)
  }

  const field =
    'w-full rounded-xl px-4 py-3 text-sm outline-none transition-colors'
  const fieldStyle = {
    background: 'var(--color-paper)',
    border: '1px solid color-mix(in srgb, var(--color-gold-deep) 22%, transparent)',
    color: 'var(--color-espresso)',
  } as const

  return (
    <section id="contact" className="py-24 md:py-32" style={{ background: 'var(--color-cream)' }}>
      <div className="container-x grid gap-14 lg:grid-cols-[0.9fr_1.1fr]">
        {/* left */}
        <div>
          <SectionHeading kicker={t.contact.kicker} title={t.contact.title} subtitle={t.contact.subtitle} />
          <ul className="mt-8 flex flex-col gap-3">
            {t.contact.perks.map((p) => (
              <Reveal as="li" key={p} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full" style={{ background: 'color-mix(in srgb, var(--color-gold) 22%, transparent)' }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-gold-deep)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                </span>
                <span className="text-sm" style={{ color: 'color-mix(in srgb, var(--color-espresso) 72%, transparent)' }}>{p}</span>
              </Reveal>
            ))}
          </ul>

          <div className="mt-10">
            <div className="text-sm font-semibold" style={{ color: 'var(--color-espresso)' }}>{t.contact.directTitle}</div>
            <div className="mt-4 flex flex-wrap gap-3">
              <a href="https://wa.me/" target="_blank" rel="noopener" className="btn btn-ghost" style={{ color: 'var(--color-espresso)' }}>
                <DotIcon color="#25D366" /> {t.contact.whatsapp}
              </a>
              <a href="https://t.me/" target="_blank" rel="noopener" className="btn btn-ghost" style={{ color: 'var(--color-espresso)' }}>
                <DotIcon color="#0088cc" /> {t.contact.telegram}
              </a>
            </div>
            <p className="mt-4 text-xs" style={{ color: 'color-mix(in srgb, var(--color-espresso) 55%, transparent)' }}>{t.contact.callbackNote}</p>
          </div>
        </div>

        {/* form card */}
        <Reveal delay={0.1}>
          <div className="relative rounded-[1.75rem] p-7 md:p-9" style={{ background: 'color-mix(in srgb, var(--color-paper) 96%, white)', border: '1px solid color-mix(in srgb, var(--color-gold-deep) 20%, transparent)', boxShadow: 'var(--shadow-lift)' }}>
            <AnimatePresence mode="wait">
              {sent ? (
                <motion.div
                  key="success"
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, ease: EASE }}
                  className="flex min-h-[420px] flex-col items-center justify-center text-center"
                >
                  <span className="flex h-16 w-16 items-center justify-center rounded-full" style={{ background: 'color-mix(in srgb, var(--color-gold) 25%, transparent)' }}>
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--color-gold-deep)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                  </span>
                  <p className="mt-6 max-w-xs text-lg" style={{ color: 'var(--color-espresso)' }}>{f.success}</p>
                </motion.div>
              ) : (
                <motion.form key="form" onSubmit={onSubmit} className="grid gap-4" exit={{ opacity: 0 }}>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="grid gap-1.5">
                      <span className="text-xs font-medium" style={{ color: 'var(--color-espresso)' }}>{f.name}</span>
                      <input required className={field} style={fieldStyle} placeholder={f.namePh} />
                    </label>
                    <label className="grid gap-1.5">
                      <span className="text-xs font-medium" style={{ color: 'var(--color-espresso)' }}>{f.company}</span>
                      <input className={field} style={fieldStyle} placeholder={f.companyPh} />
                    </label>
                  </div>
                  <label className="grid gap-1.5">
                    <span className="text-xs font-medium" style={{ color: 'var(--color-espresso)' }}>{f.email}</span>
                    <input required type="email" className={field} style={fieldStyle} placeholder={f.emailPh} />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="grid gap-1.5">
                      <span className="text-xs font-medium" style={{ color: 'var(--color-espresso)' }}>{f.category}</span>
                      <select className={field} style={fieldStyle} defaultValue="">
                        <option value="" disabled>{f.categoryPh}</option>
                        {t.products.categories.map((c) => (
                          <option key={c.name} value={c.name}>{c.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className="grid gap-1.5">
                      <span className="text-xs font-medium" style={{ color: 'var(--color-espresso)' }}>{f.market}</span>
                      <input className={field} style={fieldStyle} placeholder={f.marketPh} />
                    </label>
                  </div>
                  <label className="grid gap-1.5">
                    <span className="text-xs font-medium" style={{ color: 'var(--color-espresso)' }}>{f.message}</span>
                    <textarea rows={3} className={field} style={fieldStyle} placeholder={f.messagePh} />
                  </label>
                  <button type="submit" className="btn btn-gold mt-1 w-full">{f.submit}</button>
                  <p className="text-center text-xs" style={{ color: 'color-mix(in srgb, var(--color-espresso) 52%, transparent)' }}>{f.consent}</p>
                </motion.form>
              )}
            </AnimatePresence>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function DotIcon({ color }: { color: string }) {
  return <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
}
