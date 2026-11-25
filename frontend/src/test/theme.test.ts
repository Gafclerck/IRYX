import { describe, it, expect } from 'vitest'
import tailwindConfig from '../../tailwind.config'
import { palette } from '../styles/tokens'

describe('Thème strict IRYX', () => {
  const AUTHORIZED_COLORS = {
    ink: '#020C0C',
    deep: '#19595A',
    teal: '#019F9E',
    cyan: '#01DBDC',
    mist: '#B7DFDF',
  }

  it("n'expose que les cinq couleurs autorisées dans tokens", () => {
    const tokenColors = palette
    const keys = Object.keys(tokenColors).sort()
    const expectedKeys = Object.keys(AUTHORIZED_COLORS).sort()

    expect(keys).toEqual(expectedKeys)
    expect(tokenColors).toEqual(AUTHORIZED_COLORS)
  })

  it("n'expose que les cinq couleurs autorisées dans la configuration Tailwind", () => {
    const themeColors = tailwindConfig.theme?.colors as Record<string, string>
    expect(themeColors).toBeDefined()

    const keys = Object.keys(themeColors).sort()
    const expectedKeys = Object.keys(AUTHORIZED_COLORS).sort()

    expect(keys).toEqual(expectedKeys)
    expect(themeColors).toEqual(AUTHORIZED_COLORS)
  })

  it('interdit explicitement les couleurs standard (blanc, noir, rouge, vert, etc.)', () => {
    const themeColors = tailwindConfig.theme?.colors as Record<string, string>
    const forbiddenKeys = [
      'white',
      'black',
      'red',
      'green',
      'blue',
      'yellow',
      'orange',
      'gray',
      'slate',
      'zinc',
      'neutral',
      'stone',
      'amber',
      'emerald',
      'violet',
      'purple',
      'fuchsia',
      'pink',
      'rose',
    ]

    for (const forbidden of forbiddenKeys) {
      expect(themeColors[forbidden]).toBeUndefined()
    }
  })
})
