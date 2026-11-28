export const tokens = {
  colors: {
    ink: '#020C0C',
    deep: '#19595A',
    teal: '#019F9E',
    cyan: '#01DBDC',
    mist: '#B7DFDF',
  },
} as const

export const palette = tokens.colors
export type PaletteColor = keyof typeof palette
