import { motion } from 'framer-motion'
import { useI18n } from '../i18n'
import { SectionHeading, staggerParent, staggerChild } from './ui'
import { productImages } from '../assets'

export default function Products() {
  const { t } = useI18n()
  return (
    <section id="products" className="py-24 md:py-32" style={{ background: 'var(--color-cream)' }}>
      <div className="container-x">
        <SectionHeading kicker={t.products.kicker} title={t.products.title} subtitle={t.products.subtitle} />

        <motion.div
          variants={staggerParent}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-80px' }}
          className="mt-14 grid gap-6 md:grid-cols-2"
        >
          {t.products.categories.map((c, i) => (
            <motion.article
              key={c.name}
              variants={staggerChild}
              className="group relative overflow-hidden rounded-[1.5rem]"
              style={{ boxShadow: 'var(--shadow-soft)' }}
            >
              <div className="relative h-64 overflow-hidden md:h-72">
                <img
                  src={productImages[i]}
                  alt={c.name}
                  className="h-full w-full object-cover transition-transform duration-[900ms] ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-105"
                  loading="lazy"
                />
                <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(44,36,32,0.05) 30%, rgba(44,36,32,0.82))' }} />
                <div className="absolute inset-x-0 bottom-0 p-6">
                  <h3 className="text-2xl" style={{ color: 'var(--color-cream)' }}>{c.name}</h3>
                </div>
              </div>
              <div className="p-6" style={{ background: 'var(--color-paper)' }}>
                <p className="text-sm leading-relaxed" style={{ color: 'color-mix(in srgb, var(--color-espresso) 68%, transparent)' }}>{c.desc}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {c.tags.map((tag) => (
                    <span key={tag} className="rounded-full px-3 py-1 text-xs" style={{ background: 'color-mix(in srgb, var(--color-gold) 14%, transparent)', color: 'var(--color-gold-deep)' }}>
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </motion.article>
          ))}
        </motion.div>
      </div>
    </section>
  )
}
