export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: {
          DEFAULT: '#ffffff',
          raised: '#ffffff',
          sunk: '#f5f6f7',
          band: '#eaecee',
          bandBlue: '#ebf8ff',
          bandLavender: '#f7f4ff',
        },
        chrome: '#f5f6f7',
        ink: {
          DEFAULT: '#000000',
          lead: '#3c3c3c',
          body: '#223548',
          list: '#354a5f',
          soft: '#475e75',
          faint: '#6b7280',
          nav: '#545454',
        },
        rule: '#e5e7eb',
        hairline: '#475e75',
        navy: {
          DEFAULT: '#0057d2', // SAP Blue primary
          dark: '#0040b0',    // SAP Primary-deep
          tint: '#ebf8ff',    // Pale blue band
          deep: '#022879',    // SAP Navy
        },
        primary: {
          DEFAULT: '#0057d2',
          deep: '#0040b0',
          tint: '#ebf8ff',
        },
        positive: {
          DEFAULT: '#107e3e',
          tint: '#edf7ed',
        },
        due: {
          DEFAULT: '#b00020',
          tint: '#fde8e8',
        },
      },
      borderRadius: {
        sm: '4px',
        md: '8px',
        lg: '12px',
      },
      fontFamily: {
        display: ['Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
