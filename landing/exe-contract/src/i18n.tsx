import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import en from './locales/en'
import ru from './locales/ru'
import es from './locales/es'
import zh from './locales/zh'
import ko from './locales/ko'
import ar from './locales/ar'
import type { Dict } from './locales/types'

export type Lang = 'en' | 'ru' | 'es' | 'zh' | 'ko' | 'ar'

const RAW: Record<Lang, unknown> = { en, ru, es, zh, ko, ar }
export const LANGS: Lang[] = ['en', 'ru', 'es', 'zh', 'ko', 'ar']

// Deep-merge a partial locale over the English master so every key resolves.
function deepMerge<T>(base: T, over: unknown): T {
  if (over === undefined || over === null) return base
  if (Array.isArray(base)) {
    const o = Array.isArray(over) ? over : []
    return base.map((item, i) =>
      typeof item === 'object' && item !== null ? deepMerge(item, o[i]) : (o[i] ?? item),
    ) as unknown as T
  }
  if (typeof base === 'object' && base !== null) {
    const out: Record<string, unknown> = { ...(base as Record<string, unknown>) }
    const ov = over as Record<string, unknown>
    for (const k of Object.keys(out)) out[k] = deepMerge(out[k], ov?.[k])
    return out as T
  }
  return (over as T) ?? base
}

const DICTS: Record<Lang, Dict> = LANGS.reduce((acc, l) => {
  acc[l] = l === 'en' ? en : deepMerge(en, RAW[l])
  return acc
}, {} as Record<Lang, Dict>)

interface I18nValue {
  lang: Lang
  setLang: (l: Lang) => void
  t: Dict
  dir: 'ltr' | 'rtl'
  langLabel: (l: Lang) => string
}

const I18nCtx = createContext<I18nValue | null>(null)

function detectInitial(): Lang {
  if (typeof window === 'undefined') return 'en'
  const saved = localStorage.getItem('exemera_lang') as Lang | null
  if (saved && LANGS.includes(saved)) return saved
  const nav = navigator.language.slice(0, 2).toLowerCase()
  return (LANGS as string[]).includes(nav) ? (nav as Lang) : 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>('en')

  useEffect(() => {
    setLangState(detectInitial())
  }, [])

  const t = DICTS[lang]
  const dir = t.meta.dir as 'ltr' | 'rtl'

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
    localStorage.setItem('exemera_lang', lang)
  }, [lang, dir])

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      setLang: setLangState,
      t,
      dir,
      langLabel: (l: Lang) => DICTS[l].meta.label,
    }),
    [lang, t, dir],
  )

  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nCtx)
  if (!ctx) throw new Error('useI18n must be used within I18nProvider')
  return ctx
}
