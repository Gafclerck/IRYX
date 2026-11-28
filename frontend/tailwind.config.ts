import type { Config } from 'tailwindcss'
import tokens from './src/styles/tokens.json'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    colors: {
      ink: tokens.colors.ink,
      deep: tokens.colors.deep,
      teal: tokens.colors.teal,
      cyan: tokens.colors.cyan,
      mist: tokens.colors.mist,
    },
    extend: {
      fontFamily: {
        display: ['Inter Tight', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
