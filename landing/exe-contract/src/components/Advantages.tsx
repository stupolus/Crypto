import { motion } from 'framer-motion'
import { useI18n } from '../i18n'
import { SectionHeading, staggerParent, staggerChild } from './ui'
import { img } from '../assets'

const ICONS = [ShieldIcon, FlaskIcon, LayersIcon, HandshakeIcon]

export default function Advantages() {
  const { t } = useI18n()
  return (
    <section className="relative overflow-hidden py-24 md:py-32" style={{ background: 'var(--color-espresso)' }}>
      <div className="grain absolute inset-0" />
      <img src={img.molecules} alt="" aria-hidden className="pointer-events-none absolute end-0 top-0 h-full w-1/2 object-cover opacity-[0.12]" />
      <div className="container-x relative">
        <SectionHeading kicker={t.advantages.kicker} title={t.advantages.title} subtitle={t.advantages.subtitle} invert />

        <motion.div
          variants={staggerParent}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-80px' }}
          className="mt-14 grid gap-5 sm:grid-cols-2"
        >
          {t.advantages.items.map((item, i) => {
            const Icon = ICONS[i]
            return (
              <motion.div
                key={item.title}
                variants={staggerChild}
                className="group relative flex gap-5 rounded-2xl p-7 transition-all duration-500"
                style={{ background: 'color-mix(in srgb, var(--color-cream) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--color-gold) 18%, transparent)' }}
              >
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl transition-transform duration-500 group-hover:-translate-y-1" style={{ background: 'color-mix(in srgb, var(--color-gold) 16%, transparent)', color: 'var(--color-gold)' }}>
                  <Icon />
                </div>
                <div>
                  <h3 className="text-lg" style={{ color: 'var(--color-cream)' }}>{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed" style={{ color: 'color-mix(in srgb, var(--color-cream) 62%, transparent)' }}>{item.text}</p>
                </div>
              </motion.div>
            )
          })}
        </motion.div>
      </div>
    </section>
  )
}

function ShieldIcon() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" /><path d="M9 12l2 2 4-4" /></svg>
}
function FlaskIcon() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M9 3h6M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3" /><path d="M7 15h10" /></svg>
}
function LayersIcon() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5" /></svg>
}
function HandshakeIcon() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M8 12l3 3 5-5 4 4M2 10l4-4 5 3M22 10l-4-4" /></svg>
}
