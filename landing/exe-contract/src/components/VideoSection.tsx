import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useI18n } from '../i18n'
import { Reveal, EASE } from './ui'
import { img, media } from '../assets'

export default function VideoSection() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)

  return (
    <section className="relative overflow-hidden py-24 md:py-32" style={{ background: 'var(--color-espresso-deep)' }}>
      <div className="container-x relative">
        <div className="mx-auto max-w-2xl text-center">
          <Reveal>
            <span className="kicker" style={{ color: 'var(--color-gold)' }}>{t.video.kicker}</span>
          </Reveal>
          <Reveal delay={0.06}>
            <h2 className="mt-4 text-[clamp(2rem,4.4vw,3.2rem)] text-balance" style={{ color: 'var(--color-cream)' }}>{t.video.title}</h2>
          </Reveal>
          <Reveal delay={0.12}>
            <p className="mt-5 text-[1.02rem] leading-relaxed" style={{ color: 'color-mix(in srgb, var(--color-cream) 72%, transparent)' }}>{t.video.subtitle}</p>
          </Reveal>
        </div>

        <Reveal delay={0.15}>
          <button
            onClick={() => setOpen(true)}
            className="group relative mx-auto mt-12 block w-full max-w-4xl overflow-hidden rounded-[1.75rem]"
            style={{ boxShadow: 'var(--shadow-lift)' }}
            aria-label={t.video.cta}
          >
            <img src={img.production1} alt="" className="aspect-video w-full object-cover transition-transform duration-[900ms] group-hover:scale-105" loading="lazy" />
            <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(44,36,32,0.15), rgba(44,36,32,0.55))' }} />
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="flex h-20 w-20 items-center justify-center rounded-full transition-transform duration-500 group-hover:scale-110" style={{ background: 'color-mix(in srgb, var(--color-gold) 92%, white)', boxShadow: '0 0 0 12px color-mix(in srgb, var(--color-gold) 22%, transparent)' }}>
                <svg width="26" height="26" viewBox="0 0 24 24" fill="var(--color-espresso-deep)" className="ms-1"><path d="M8 5v14l11-7z" /></svg>
              </span>
            </span>
            <span className="absolute bottom-5 start-6 text-sm font-medium" style={{ color: 'var(--color-cream)' }}>{t.video.cta}</span>
          </button>
        </Reveal>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="fixed inset-0 z-[60] flex items-center justify-center p-4"
            style={{ background: 'rgba(25,21,18,0.86)', backdropFilter: 'blur(8px)' }}
            onClick={() => setOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.94, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.94, opacity: 0 }}
              transition={{ duration: 0.35, ease: EASE }}
              className="relative w-full max-w-5xl overflow-hidden rounded-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <video src={media.productionVideo} poster={img.production1} controls autoPlay playsInline className="w-full">
                {t.video.subtitle}
              </video>
              <button onClick={() => setOpen(false)} className="absolute end-3 top-3 flex h-10 w-10 items-center justify-center rounded-full" style={{ background: 'rgba(0,0,0,0.5)', color: '#fff' }} aria-label="Close">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
