/**
 * Self-contained ISO/IEC 18004 QR Code matrix generator (Byte mode, Error Correction Level L, Versions 1-10)
 * for rendering scannable NPCI UPI payment QRs without external runtime dependencies.
 */

const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);
(() => {
  let x = 1;
  for (let i = 0; i < 255; i += 1) {
    EXP[i] = x;
    EXP[i + 255] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
})();

function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return EXP[LOG[a] + LOG[b]];
}

function rsGeneratorPoly(degree: number): Uint8Array {
  let poly = new Uint8Array([1]);
  for (let i = 0; i < degree; i += 1) {
    const next = new Uint8Array(poly.length + 1);
    const factor = EXP[i];
    for (let j = 0; j < poly.length; j += 1) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMul(poly[j], factor);
    }
    poly = next;
  }
  return poly;
}

function rsEncode(data: Uint8Array, ecCount: number): Uint8Array {
  const gen = rsGeneratorPoly(ecCount);
  const res = new Uint8Array(data.length + ecCount);
  res.set(data);
  for (let i = 0; i < data.length; i += 1) {
    const coeff = res[i];
    if (coeff !== 0) {
      for (let j = 0; j < gen.length; j += 1) {
        res[i + j] ^= gfMul(gen[j], coeff);
      }
    }
  }
  return res.slice(data.length);
}

type VersionSpec = {
  version: number;
  totalData: number;
  ecPerBlock: number;
  b1Count: number;
  b1Data: number;
  b2Count: number;
  b2Data: number;
  align: number[];
};

// Error Correction Level L specs for Versions 1..10 (up to 271 UTF-8 bytes)
const VERSIONS_L: VersionSpec[] = [
  { version: 1, totalData: 19, ecPerBlock: 7, b1Count: 1, b1Data: 19, b2Count: 0, b2Data: 0, align: [] },
  { version: 2, totalData: 34, ecPerBlock: 10, b1Count: 1, b1Data: 34, b2Count: 0, b2Data: 0, align: [6, 18] },
  { version: 3, totalData: 55, ecPerBlock: 15, b1Count: 1, b1Data: 55, b2Count: 0, b2Data: 0, align: [6, 22] },
  { version: 4, totalData: 80, ecPerBlock: 20, b1Count: 1, b1Data: 80, b2Count: 0, b2Data: 0, align: [6, 26] },
  { version: 5, totalData: 108, ecPerBlock: 26, b1Count: 1, b1Data: 108, b2Count: 0, b2Data: 0, align: [6, 30] },
  { version: 6, totalData: 136, ecPerBlock: 18, b1Count: 2, b1Data: 68, b2Count: 0, b2Data: 0, align: [6, 34] },
  { version: 7, totalData: 156, ecPerBlock: 20, b1Count: 2, b1Data: 78, b2Count: 0, b2Data: 0, align: [6, 22, 38] },
  { version: 8, totalData: 194, ecPerBlock: 24, b1Count: 2, b1Data: 97, b2Count: 0, b2Data: 0, align: [6, 24, 42] },
  { version: 9, totalData: 232, ecPerBlock: 30, b1Count: 2, b1Data: 116, b2Count: 0, b2Data: 0, align: [6, 26, 46] },
  { version: 10, totalData: 274, ecPerBlock: 18, b1Count: 2, b1Data: 68, b2Count: 2, b2Data: 69, align: [6, 28, 50] },
];

function computeFormatBits(mask: number): number {
  const data = (0b01 << 3) | (mask & 7); // EC Level L = 01
  let rem = data << 10;
  for (let i = 14; i >= 10; i -= 1) {
    if ((rem >> i) & 1) rem ^= 0x537 << (i - 10);
  }
  return ((data << 10) | rem) ^ 0x5412;
}

function computeVersionBits(version: number): number {
  let rem = version << 12;
  for (let i = 17; i >= 12; i -= 1) {
    if ((rem >> i) & 1) rem ^= 0x1f25 << (i - 12);
  }
  return (version << 12) | rem;
}

function maskBit(mask: number, r: number, c: number): boolean {
  switch (mask) {
    case 0:
      return (r + c) % 2 === 0;
    case 1:
      return r % 2 === 0;
    case 2:
      return c % 3 === 0;
    case 3:
      return (r + c) % 3 === 0;
    case 4:
      return (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0;
    case 5:
      return ((r * c) % 2) + ((r * c) % 3) === 0;
    case 6:
      return (((r * c) % 2) + ((r * c) % 3)) % 2 === 0;
    default:
      return (((r + c) % 2) + ((r * c) % 3)) % 2 === 0;
  }
}

function penaltyScore(modules: boolean[][]): number {
  const n = modules.length;
  let score = 0;

  // N1: 5+ consecutive same-color modules in rows and columns
  for (let r = 0; r < n; r += 1) {
    let runR = 1;
    let runC = 1;
    for (let i = 1; i < n; i += 1) {
      if (modules[r][i] === modules[r][i - 1]) {
        runR += 1;
      } else {
        if (runR >= 5) score += 3 + (runR - 5);
        runR = 1;
      }
      if (modules[i][r] === modules[i - 1][r]) {
        runC += 1;
      } else {
        if (runC >= 5) score += 3 + (runC - 5);
        runC = 1;
      }
    }
    if (runR >= 5) score += 3 + (runR - 5);
    if (runC >= 5) score += 3 + (runC - 5);
  }

  // N2: 2x2 blocks of same color
  for (let r = 0; r < n - 1; r += 1) {
    for (let c = 0; c < n - 1; c += 1) {
      const v = modules[r][c];
      if (v === modules[r][c + 1] && v === modules[r + 1][c] && v === modules[r + 1][c + 1]) {
        score += 3;
      }
    }
  }

  // N3: finder-like 1:1:3:1:1 patterns (with 4 light margin)
  let darkCount = 0;
  for (let r = 0; r < n; r += 1) {
    for (let c = 0; c < n; c += 1) {
      if (modules[r][c]) darkCount += 1;
    }
  }

  // N4: dark module ratio deviation from 50%
  const pct = (darkCount * 100) / (n * n);
  const k = Math.floor(Math.abs(pct - 50) / 5);
  score += k * 10;
  return score;
}

export function encodeQrMatrix(text: string): boolean[][] {
  const bytes = new TextEncoder().encode(text);
  const spec = VERSIONS_L.find((v) => {
    const countBits = v.version >= 10 ? 16 : 8;
    const neededBits = 4 + countBits + bytes.length * 8;
    return neededBits <= v.totalData * 8;
  });
  if (!spec) {
    throw new Error('QR payload exceeds supported length');
  }

  // 1. Encode data codewords (Byte mode 0100)
  const bits: number[] = [];
  const pushBits = (val: number, len: number) => {
    for (let i = len - 1; i >= 0; i -= 1) bits.push((val >> i) & 1);
  };
  pushBits(0b0100, 4);
  pushBits(bytes.length, spec.version >= 10 ? 16 : 8);
  for (const b of bytes) pushBits(b, 8);

  const totalDataBits = spec.totalData * 8;
  const term = Math.min(4, totalDataBits - bits.length);
  for (let i = 0; i < term; i += 1) bits.push(0);
  while (bits.length % 8 !== 0) bits.push(0);

  const dataCodewords = new Uint8Array(spec.totalData);
  let byteIdx = 0;
  for (let i = 0; i < bits.length; i += 8) {
    let v = 0;
    for (let b = 0; b < 8; b += 1) v = (v << 1) | bits[i + b];
    dataCodewords[byteIdx++] = v;
  }
  const padBytes = [0xec, 0x11];
  let padIdx = 0;
  while (byteIdx < spec.totalData) {
    dataCodewords[byteIdx++] = padBytes[padIdx % 2];
    padIdx += 1;
  }

  // 2. Split into blocks + compute Reed-Solomon EC + interleave
  const dataBlocks: Uint8Array[] = [];
  const ecBlocks: Uint8Array[] = [];
  let offset = 0;
  for (let i = 0; i < spec.b1Count; i += 1) {
    const blk = dataCodewords.slice(offset, offset + spec.b1Data);
    offset += spec.b1Data;
    dataBlocks.push(blk);
    ecBlocks.push(rsEncode(blk, spec.ecPerBlock));
  }
  for (let i = 0; i < spec.b2Count; i += 1) {
    const blk = dataCodewords.slice(offset, offset + spec.b2Data);
    offset += spec.b2Data;
    dataBlocks.push(blk);
    ecBlocks.push(rsEncode(blk, spec.ecPerBlock));
  }

  const finalCodewords: number[] = [];
  const maxDataLen = Math.max(spec.b1Data, spec.b2Data);
  for (let i = 0; i < maxDataLen; i += 1) {
    for (const blk of dataBlocks) {
      if (i < blk.length) finalCodewords.push(blk[i]);
    }
  }
  for (let i = 0; i < spec.ecPerBlock; i += 1) {
    for (const blk of ecBlocks) {
      finalCodewords.push(blk[i]);
    }
  }

  // 3. Build fixed function module layout
  const size = 17 + spec.version * 4;
  const base: boolean[][] = Array.from({ length: size }, () => Array<boolean>(size).fill(false));
  const reserved: boolean[][] = Array.from({ length: size }, () => Array<boolean>(size).fill(false));

  const setFixed = (r: number, c: number, dark: boolean) => {
    if (r >= 0 && r < size && c >= 0 && c < size) {
      base[r][c] = dark;
      reserved[r][c] = true;
    }
  };

  const drawFinder = (r0: number, c0: number) => {
    for (let dr = -1; dr <= 7; dr += 1) {
      for (let dc = -1; dc <= 7; dc += 1) {
        const r = r0 + dr;
        const c = c0 + dc;
        if (r < 0 || r >= size || c < 0 || c >= size) continue;
        const inOuter = dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6;
        const onBorder = dr === 0 || dr === 6 || dc === 0 || dc === 6;
        const inInner = dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4;
        setFixed(r, c, inOuter && (onBorder || inInner));
      }
    }
  };
  drawFinder(0, 0);
  drawFinder(0, size - 7);
  drawFinder(size - 7, 0);

  for (const r of spec.align) {
    for (const c of spec.align) {
      const overlapsCorner =
        (r <= 8 && c <= 8) || (r <= 8 && c >= size - 8) || (r >= size - 8 && c <= 8);
      if (overlapsCorner) continue;
      for (let dr = -2; dr <= 2; dr += 1) {
        for (let dc = -2; dc <= 2; dc += 1) {
          const dark = Math.abs(dr) === 2 || Math.abs(dc) === 2 || (dr === 0 && dc === 0);
          setFixed(r + dr, c + dc, dark);
        }
      }
    }
  }

  for (let i = 8; i < size - 8; i += 1) {
    setFixed(6, i, i % 2 === 0);
    setFixed(i, 6, i % 2 === 0);
  }
  setFixed(4 * spec.version + 9, 8, true);

  // Reserve format info strips
  for (let i = 0; i <= 8; i += 1) {
    if (i !== 6) {
      reserved[8][i] = true;
      reserved[i][8] = true;
    }
  }
  for (let i = 0; i < 8; i += 1) {
    reserved[8][size - 1 - i] = true;
    if (i < 7) reserved[size - 1 - i][8] = true;
  }

  // Version info for versions >= 7
  if (spec.version >= 7) {
    const vbits = computeVersionBits(spec.version);
    for (let i = 0; i < 18; i += 1) {
      const dark = ((vbits >> i) & 1) === 1;
      const a = Math.floor(i / 3);
      const b = size - 11 + (i % 3);
      setFixed(a, b, dark);
      setFixed(b, a, dark);
    }
  }

  // 4. Place data bits in zig-zag order
  const dataBits: boolean[] = [];
  for (const cw of finalCodewords) {
    for (let b = 7; b >= 0; b -= 1) dataBits.push(((cw >> b) & 1) === 1);
  }

  let bitIdx = 0;
  let upward = true;
  for (let col = size - 1; col >= 1; col -= 2) {
    if (col === 6) col -= 1;
    for (let step = 0; step < size; step += 1) {
      const row = upward ? size - 1 - step : step;
      for (let offsetC = 0; offsetC < 2; offsetC += 1) {
        const c = col - offsetC;
        if (!reserved[row][c]) {
          base[row][c] = bitIdx < dataBits.length ? dataBits[bitIdx++] : false;
        }
      }
    }
    upward = !upward;
  }

  // 5. Evaluate masks 0..7 and select optimal matrix
  let bestMatrix: boolean[][] | null = null;
  let bestPenalty = Infinity;
  for (let mask = 0; mask < 8; mask += 1) {
    const candidate = base.map((row, r) =>
      row.map((val, c) => (reserved[r][c] ? val : maskBit(mask, r, c) ? !val : val)),
    );
    const fmt = computeFormatBits(mask);
    for (let i = 0; i <= 5; i += 1) {
      const dark = ((fmt >> (14 - i)) & 1) === 1;
      candidate[8][i] = dark;
      candidate[size - 1 - i][8] = dark;
    }
    candidate[8][7] = ((fmt >> 8) & 1) === 1;
    candidate[size - 7][8] = ((fmt >> 8) & 1) === 1;
    candidate[8][8] = ((fmt >> 7) & 1) === 1;
    candidate[7][8] = ((fmt >> 6) & 1) === 1;
    for (let i = 0; i <= 5; i += 1) {
      candidate[5 - i][8] = ((fmt >> (5 - i)) & 1) === 1;
    }
    for (let i = 0; i <= 7; i += 1) {
      candidate[8][size - 8 + i] = ((fmt >> (7 - i)) & 1) === 1;
    }

    const score = penaltyScore(candidate);
    if (score < bestPenalty) {
      bestPenalty = score;
      bestMatrix = candidate;
    }
  }

  return bestMatrix ?? base;
}
