import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        terracotta: {
          DEFAULT: '#D4795C',
          light: '#E8A090',
          dark: '#B85E44',
          50: '#FDF3F0',
          100: '#FAE3DC',
        },
        sage: {
          DEFAULT: '#7A8F7A',
          light: '#A0B0A0',
          dark: '#5A6F5A',
          50: '#F0F4F0',
        },
        cream: '#F5EDE0',
        paper: '#FBF7F0',
        ink: '#1C1917',
        muted: '#9A8F8A',
        border: '#EDE8E3',
      },
      fontFamily: {
        heading: ['var(--font-cormorant)', 'Georgia', 'serif'],
        body: ['var(--font-onest)', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        '4xl': '2rem',
      },
    },
  },
  plugins: [],
}

export default config
