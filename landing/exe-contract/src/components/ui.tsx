import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  motion,
  useInView,
  useMotionValue,
  useSpring,
  useReducedMotion,
  type Variants,
} from 'framer-motion'

export const EASE = [0.16, 1, 0.3, 1] as const

/** Fade + rise reveal on scroll into view. */
export function Reveal({
  children,
  delay = 0,
  y = 24,
  className,
  as = 'div',
}: {
  children: ReactNode
  delay?: number
  y?: number
  className?: string
  as?: 'div' | 'span' | 'li' | 'section'
}) {
  const reduce = useReducedMotion()
  const MotionTag = motion[as]
  return (
    <MotionTag
      className={className}
      initial={{ opacity: 0, y: reduce ? 0 : y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.8, ease: EASE, delay }}
    >
      {children}
    </MotionTag>
  )
}

/** Container that staggers its Reveal-like children. */
export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
}
export const staggerChild: Variants = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: EASE } },
}

/** Count-up number that animates when scrolled into view. */
export function Counter({ to, suffix = '' }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })
  const reduce = useReducedMotion()
  const mv = useMotionValue(0)
  const spring = useSpring(mv, { duration: 1.6, bounce: 0 })
  const [display, setDisplay] = useState('0')

  useEffect(() => {
    if (inView) mv.set(reduce ? to : to)
  }, [inView, mv, to, reduce])

  useEffect(() => {
    if (reduce) {
      setDisplay(String(to))
      return
    }
    return spring.on('change', (v) => setDisplay(String(Math.round(v))))
  }, [spring, reduce, to])

  return (
    <span ref={ref}>
      {display}
      {suffix}
    </span>
  )
}

export function SectionHeading({
  kicker,
  title,
  subtitle,
  align = 'left',
  invert = false,
}: {
  kicker: string
  title: ReactNode
  subtitle?: string
  align?: 'left' | 'center'
  invert?: boolean
}) {
  return (
    <div className={align === 'center' ? 'mx-auto max-w-2xl text-center' : 'max-w-2xl'}>
      <Reveal>
        <span
          className="kicker"
          style={{ color: invert ? 'var(--color-gold)' : 'var(--color-gold-deep)' }}
        >
          {kicker}
        </span>
      </Reveal>
      <Reveal delay={0.06}>
        <h2
          className="mt-4 text-[clamp(2rem,4.6vw,3.4rem)] text-balance"
          style={{ color: invert ? 'var(--color-cream)' : 'var(--color-espresso)' }}
        >
          {title}
        </h2>
      </Reveal>
      {subtitle && (
        <Reveal delay={0.12}>
          <p
            className="mt-5 text-[1.05rem] leading-relaxed"
            style={{ color: invert ? 'color-mix(in srgb, var(--color-cream) 75%, transparent)' : 'color-mix(in srgb, var(--color-espresso) 68%, transparent)' }}
          >
            {subtitle}
          </p>
        </Reveal>
      )}
    </div>
  )
}

/** Exemera wordmark from the reconstructed brand SVG. `tone` sets fill. */
export function LogoMark({ tone = 'espresso', className }: { tone?: 'espresso' | 'cream' | 'gold'; className?: string }) {
  const fill =
    tone === 'cream' ? 'var(--color-cream)' : tone === 'gold' ? 'var(--color-gold)' : 'var(--color-espresso)'
  return (
    <svg viewBox="0 0 1606.45 237.1" className={className} role="img" aria-label="Exemera" fill={fill}>
      <ExemeraShapes />
    </svg>
  )
}

// Exact wordmark shapes (7 letters) reconstructed from the brand asset.
function ExemeraShapes() {
  return (
    <>
      <polygon points="408.71 16.17 370.45 16.17 320.43 92.42 318.99 92.42 267.97 16.17 226.12 16.17 293.34 116.93 225.4 219.7 263.67 219.7 314.26 142.88 315.84 142.88 367.44 219.7 409.29 219.7 341.35 118.08 408.71 16.17" />
      <polygon points="464.9 219.7 614.39 219.7 614.39 188.45 502.16 188.45 502.16 131.98 595.33 131.98 595.33 103.03 502.16 103.03 502.16 47.42 614.39 47.42 614.39 16.17 464.9 16.17 464.9 219.7" />
      <polygon points="796.56 175.27 794.98 175.27 736.79 16.17 678.89 16.17 678.89 219.7 711.71 219.7 711.71 54.73 713.71 54.73 775.06 219.7 811.32 219.7 872.66 54.73 874.67 54.73 874.67 219.7 911.08 219.7 911.08 16.17 853.74 16.17 796.56 175.27" />
      <polygon points="989.31 219.7 1138.8 219.7 1138.8 188.45 1026.58 188.45 1026.58 131.98 1119.74 131.98 1119.74 103.03 1026.58 103.03 1026.58 47.42 1138.8 47.42 1138.8 16.17 989.31 16.17 989.31 219.7" />
      <path d="M1360.31,77.05c0-26.52-16.8-60.87-69.5-60.87h-88.38v203.52h37.55v-80.69h29.24l56.61,80.69h41.85l-59.66-83.88c20.12-4.16,52.29-18.51,52.29-58.77ZM1239.98,111.06V45.99h43.26c32.16,0,43.33,15.56,43.33,32.39,0,27.49-25.12,32.68-45.5,32.68h-41.09Z" />
      <path d="M110.77,15.45c-32.87,0-53.01,9.94-65.42,20.12C16.69,59.09,10.06,92.75,10.06,120.15c0,29.01,8.85,53.61,25.6,71.14,18.21,19.06,45.52,29.13,78.97,29.13,30.72,0,50.92-7.41,51.76-7.72l3.4-1.27v-33.8s-6.91,2.35-6.91,2.35c-.18.06-18.37,6.03-37.74,7.31-27.16,1.79-47.44-2.85-61.65-16.45-8.81-8.43-16.82-22.83-17.46-37.69h69.25c45.98,0,72.35-17.54,72.35-56.59,0-19.72-10.24-40.67-31.9-52.18-11.64-6.19-23.8-8.92-44.98-8.92ZM110.45,45.22c29.74,0,45.27,12.81,45.27,31.41,0,17.64-14.89,26.06-38.9,26.06H45.17c.9-10.98,4.54-26.31,19.08-40.96,10.76-10.85,28.43-16.5,46.19-16.5Z" />
      <path d="M1488.01,220.42c32.87,0,53.01-9.94,65.42-20.12,28.66-23.51,35.28-57.18,35.28-84.58,0-29.01-8.85-53.61-25.6-71.14-18.21-19.06-45.52-29.13-78.97-29.13-30.72,0-50.92,7.41-51.76,7.72l-3.4,1.27v33.8s6.91-2.35,6.91-2.35c.18-.06,18.37-6.03,37.74-7.31,27.16-1.79,47.44,2.85,61.65,16.45,8.81,8.43,16.82,22.83,17.46,37.69h-69.25c-45.98,0-72.35,17.54-72.35,56.59,0,19.72,10.24,40.67,31.9,52.18,11.64,6.19,23.8,8.92,44.98,8.92ZM1488.33,190.65c-29.74,0-45.27-12.81-45.27-31.41,0-17.64,14.89-26.06,38.9-26.06h71.64c-.9,10.98-4.54,26.31-19.08,40.96-10.76,10.85-28.43,16.5-46.19,16.5Z" />
    </>
  )
}
