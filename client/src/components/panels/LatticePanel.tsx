import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { useQuantum } from '@/lib/quantum/store';
import { phaseColor } from '@/components/brand';
import { PanelFrame, Stat } from '@/components/panels/shell';

/** Deterministic small-integer basis, so the view is reproducible across reloads. */
function makeBasis(n: number, seed: number): number[][] {
  let s = seed >>> 0;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const B: number[][] = [];
  for (let i = 0; i < n; i++) {
    const row = new Array<number>(n).fill(0);
    for (let j = 0; j < n; j++) row[j] = Math.round((rnd() - 0.5) * 8);
    row[i] += 5 + Math.round(rnd() * 3); // keep it well-conditioned
    B.push(row);
  }
  return B;
}

function gramSchmidtLengths(B: number[][]): number[] {
  const n = B.length;
  const star: number[][] = [];
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const v = B[i].slice();
    for (let j = 0; j < i; j++) {
      const sj = star[j];
      const den = sj.reduce((a, x) => a + x * x, 0);
      if (den < 1e-12) continue;
      const mu = B[i].reduce((a, x, k) => a + x * sj[k], 0) / den;
      for (let k = 0; k < n; k++) v[k] -= mu * sj[k];
    }
    star.push(v);
    out.push(Math.sqrt(v.reduce((a, x) => a + x * x, 0)));
  }
  return out;
}

export function LatticePanel() {
  const { state, snap } = useQuantum();
  const n = state.n;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [seed, setSeed] = useState(7);
  const [axes, setAxes] = useState<[number, number]>([0, 1]);

  const B = useMemo(() => makeBasis(n, seed), [n, seed]);
  const lengths = useMemo(() => gramSchmidtLengths(B), [B]);
  const [i, j] = [Math.min(axes[0], n - 1), Math.min(axes[1], n - 1)];

  /** Orthogonalised projection pair (u, v) — the shader-uniform analogue. */
  const proj = useMemo(() => {
    const u = B[i].slice();
    const raw = B[j === i ? (i + 1) % n : j].slice();
    const den = u.reduce((a, x) => a + x * x, 0) || 1;
    const mu = raw.reduce((a, x, k) => a + x * u[k], 0) / den;
    const v = raw.map((x, k) => x - mu * u[k]);
    const nu = Math.hypot(...u) || 1;
    const nv = Math.hypot(...v) || 1;
    return { u: u.map((x) => x / nu), v: v.map((x) => x / nv) };
  }, [B, i, j, n]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const d = snap.dimension;
    const xs = new Float64Array(d);
    const ys = new Float64Array(d);
    let extX = 1e-9;
    let extY = 1e-9;
    const trits = new Int8Array(n);
    for (let k = 0; k < d; k++) {
      let rest = k;
      for (let q = n - 1; q >= 0; q--) {
        trits[q] = (rest % 3) - 1;
        rest = (rest - (rest % 3)) / 3;
      }
      let x = 0;
      let y = 0;
      for (let q = 0; q < n; q++) {
        x += trits[q] * proj.u[q];
        y += trits[q] * proj.v[q];
      }
      xs[k] = x;
      ys[k] = y;
      extX = Math.max(extX, Math.abs(x));
      extY = Math.max(extY, Math.abs(y));
    }

    // Fit the cloud to the box independently per axis, then take the tighter
    // scale so the projection stays isotropic (no shear) while still using the
    // full width of a wide panel.
    const pad = 22;
    const scale = Math.min((w / 2 - pad) / extX, (h / 2 - pad) / extY);
    const cx = w / 2;
    const cy = h / 2;

    // faint axis cross
    ctx.strokeStyle = 'rgba(127,140,160,0.20)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad, cy);
    ctx.lineTo(w - pad, cy);
    ctx.moveTo(cx, pad);
    ctx.lineTo(cx, h - pad);
    ctx.stroke();

    // Unit basis directions, so the viewer can read which rows are in play.
    const arm = Math.min(w / 2 - pad, h / 2 - pad) * 0.9;
    ctx.strokeStyle = 'rgba(127,140,160,0.5)';
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + arm, cy);
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx, cy - arm);
    ctx.stroke();
    ctx.fillStyle = 'rgba(127,140,160,0.85)';
    ctx.font = '11px ui-monospace, monospace';
    ctx.fillText(`b${i}*`, cx + arm - 16, cy + 14);
    ctx.fillText(`b${j}*`, cx + 6, cy - arm + 10);

    const peak = snap.peak || 1;
    // Draw low-weight nodes first so bright, high-amplitude nodes sit on top.
    const order = Array.from({ length: d }, (_, k) => k).sort(
      (a, b) => snap.probabilities[a] - snap.probabilities[b],
    );
    for (const k of order) {
      const rel = snap.probabilities[k] / peak;
      const px = cx + xs[k] * scale;
      const py = cy - ys[k] * scale;
      if (rel < 1e-9) {
        // Unoccupied coefficient vectors still belong to the lattice, so keep
        // the structure legible rather than letting the box vanish on collapse.
        ctx.fillStyle = 'rgba(127,140,160,0.38)';
        ctx.beginPath();
        ctx.arc(px, py, 1.9, 0, Math.PI * 2);
        ctx.fill();
        continue;
      }
      const re = snap.amplitudes[2 * k];
      const im = snap.amplitudes[2 * k + 1];
      const r = 2.4 + 4.2 * Math.sqrt(rel);
      const color = phaseColor(Math.atan2(im, re), 58, 0.35 + 0.65 * rel);
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
      if (rel > 0.9) {
        ctx.strokeStyle = phaseColor(Math.atan2(im, re), 72, 0.9);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(px, py, r + 3.5, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }, [snap, proj, n, i, j]);

  return (
    <PanelFrame
      title="SVP / lattice"
      subtitle="Balanced-ternary coefficient box {−1,0,+1}ⁿ projected to 2D. Node hue and brightness read from the same amplitude buffer as the state panel."
      actions={
        <Button
          variant="outline"
          size="sm"
          onClick={() => setSeed((s) => s + 1)}
          data-testid="button-reseed"
        >
          New basis
        </Button>
      }
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Nodes" value={snap.dimension.toLocaleString()} hint={`3^${n} coefficient vectors`} />
        <Stat
          label="Projection"
          value={`b${i} × b${j}`}
          hint="Gram–Schmidt orthogonalised pair"
        />
        <Stat
          label="Basis seed"
          value={String(seed)}
          hint="deterministic integer basis"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="overflow-hidden rounded-lg border border-card-border bg-card">
          <canvas
            ref={canvasRef}
            className="block h-[46vh] w-full"
            data-testid="img-lattice"
            aria-label="Ternary lattice projection"
          />
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <h2 className="mb-2 text-sm font-semibold">Projection axes</h2>
            <div className="flex flex-wrap gap-1">
              {Array.from({ length: n }, (_, q) => (
                <button
                  key={q}
                  onClick={() => setAxes(([a]) => (a === q ? [a, q] : [q, a]))}
                  data-testid={`button-axis-${q}`}
                  aria-pressed={q === i || q === j}
                  className={`h-8 w-8 rounded-md border font-mono text-xs tnum transition-colors ${
                    q === i
                      ? 'border-primary bg-primary/20 text-foreground'
                      : q === j
                        ? 'border-primary/60 bg-primary/10 text-foreground'
                        : 'border-border text-muted-foreground hover:bg-accent'
                  }`}
                >
                  {q}
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Click to promote a basis row to the horizontal axis; the previous one moves to
              vertical.
            </p>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-semibold">‖bᵢ*‖ readout</h2>
            <div className="flex flex-col gap-1">
              {lengths.map((len, k) => {
                const max = Math.max(...lengths);
                return (
                  <div key={k} className="flex items-center gap-2">
                    <span className="w-7 font-mono text-[11px] text-muted-foreground tnum">
                      b{k}
                    </span>
                    <div className="h-1.5 flex-1 rounded-full bg-muted">
                      <div
                        className="h-1.5 rounded-full bg-primary"
                        style={{ width: `${(len / max) * 100}%` }}
                      />
                    </div>
                    <span className="w-12 text-right font-mono text-[11px] tnum">
                      {len.toFixed(2)}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Static basis for now. TRI-179 animates these shrinking across LLL/BKZ steps.
            </p>
          </div>
        </div>
      </div>

      <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        Scope note: this panel visualises <span className="font-mono">3ⁿ</span> qutrit coefficient
        vectors — a rendering and WASM/RPC scaling concern. It is not the TriFHE cryptographic ring
        dimension ladder (<span className="font-mono">n = 27, 81, 243, 729, 2187</span>), and raw{' '}
        <span className="font-mono">3ⁿ</span> keyspace is never a hardness claim.
      </p>
    </PanelFrame>
  );
}
