import type en from './en'

export type Dict = typeof en

// Deep-partial so secondary locales only translate what they need;
// missing keys fall back to English at merge time.
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends readonly (infer U)[]
    ? readonly DeepPartial<U>[]
    : T[P] extends object
      ? DeepPartial<T[P]>
      : T[P]
}
