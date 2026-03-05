import {
  extractUTMParameters,
  hasAnyUTM,
  loadStoredUTM,
  mergeUTMParameters,
  storeUTM,
} from '@/lib/utm'

class MockStorage implements Storage {
  private readonly entries = new Map<string, string>()

  get length(): number {
    return this.entries.size
  }

  clear(): void {
    this.entries.clear()
  }

  getItem(key: string): string | null {
    return this.entries.get(key) ?? null
  }

  key(index: number): string | null {
    return Array.from(this.entries.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.entries.delete(key)
  }

  setItem(key: string, value: string): void {
    this.entries.set(key, value)
  }
}

describe('utm helpers', () => {
  it('extracts UTM params from query', () => {
    const params = new URLSearchParams('utm_source=google&utm_medium=cpc&utm_campaign=spring')
    const result = extractUTMParameters(params)

    expect(result).toEqual({
      source: 'google',
      medium: 'cpc',
      campaign: 'spring',
      term: undefined,
      content: undefined,
    })
  })

  it('merges incoming UTM values over stored values', () => {
    const merged = mergeUTMParameters(
      { source: 'newsletter', medium: 'email', campaign: 'a' },
      { source: 'linkedin' },
    )

    expect(merged).toEqual({
      source: 'linkedin',
      medium: 'email',
      campaign: 'a',
      term: undefined,
      content: undefined,
    })
  })

  it('stores and loads UTM values', () => {
    const storage = new MockStorage()
    storeUTM(storage, { source: 'x', campaign: 'y' })

    const loaded = loadStoredUTM(storage)
    expect(loaded).toEqual({
      source: 'x',
      medium: undefined,
      campaign: 'y',
      term: undefined,
      content: undefined,
    })

    expect(hasAnyUTM(loaded)).toBe(true)
  })
})
