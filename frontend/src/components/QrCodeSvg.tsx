import { useMemo } from 'react';
import { encodeQrMatrix } from '../lib/qrcode';

export function QrCodeSvg({
  value,
  size = 168,
  label = 'Scan to pay via UPI',
}: {
  value: string;
  size?: number;
  label?: string;
}) {
  const svgData = useMemo(() => {
    try {
      const matrix = encodeQrMatrix(value);
      const quiet = 4;
      const total = matrix.length + quiet * 2;
      const paths: string[] = [];
      for (let r = 0; r < matrix.length; r += 1) {
        for (let c = 0; c < matrix[r].length; c += 1) {
          if (matrix[r][c]) {
            paths.push(`M${c + quiet},${r + quiet}h1v1h-1z`);
          }
        }
      }
      return { total, pathData: paths.join('') };
    } catch {
      return null;
    }
  }, [value]);

  if (!svgData) {
    return null;
  }

  return (
    <div className="inline-flex flex-col items-center rounded-lg border border-rule bg-white p-3 shadow-xs">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${svgData.total} ${svgData.total}`}
        role="img"
        aria-label={label}
        shapeRendering="crispEdges"
      >
        <rect width={svgData.total} height={svgData.total} fill="#ffffff" />
        <path d={svgData.pathData} fill="#0f172a" />
      </svg>
      <span className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-soft">
        Scan with GPay / PhonePe / Paytm
      </span>
    </div>
  );
}
