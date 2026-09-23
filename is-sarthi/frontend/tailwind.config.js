/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        govNavy: {
          50: '#f0f6fc',
          100: '#e0ecf8',
          800: '#1e3a8a',
          900: '#0f2942',
          950: '#0a1d30',
        },
        govSaffron: {
          500: '#f59e0b',
          600: '#d97706',
        },
        govGreen: {
          50: '#f0fdf4',
          100: '#dcfce7',
          700: '#15803d',
          800: '#166534',
        },
        govRed: {
          50: '#fef2f2',
          100: '#fee2e2',
          700: '#b91c1c',
          800: '#991b1b',
        },
      },
    },
  },
  plugins: [],
};
