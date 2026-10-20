export default {
    content: ['./index.html', './src/**/*.{ts,tsx}'],
    theme: {
        extend: {
            colors: {
                canvas: { DEFAULT: '#f6f8fb', raised: '#ffffff', sunk: '#edf1f6' },
                ink: { DEFAULT: '#0f1b33', soft: '#4a5872', faint: '#8794ab' },
                rule: '#dde3ec',
                navy: { DEFAULT: '#12305f', dark: '#0b2147', tint: '#e8eef8' },
                positive: { DEFAULT: '#1d6b4a', tint: '#e5f3ec' },
                due: { DEFAULT: '#a8431a', tint: '#fbece4' },
            },
            fontFamily: {
                display: ['Inter', 'system-ui', 'sans-serif'],
                sans: ['Inter', 'system-ui', 'sans-serif'],
            },
        },
    },
    plugins: [],
};
