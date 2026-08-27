import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { useQuantum } from '@/lib/quantum/store';
import { formatBytes, ketLabel, stateBytes } from '@/lib/quantum/types';
import { phaseColor } from '@/components/brand';
import { PanelFrame, Stat } from '@/components/panels/shell';

const WHEEL_CAP = 81;

export function StatePanel() {
  const { state, snap } = useQuantum();
  const [rows, setRows] = useState(16);
  const n = state.n;

  const norm = useMemo(() => {
    let s = 0;
    for (let k = 0; k < snap.dimension; k++) s += snap.probabilities[k];
    return s;
  }, [snap]);

  const support = useMemo(() => {
    let c = 0;
    for (let k = 0; k < snap.dimension; k++) if (snap.probabilities[k] > 1e-12) c++;
    return c;
  }, [snap]);

  const visible = snap.ranked.slice(0, Math.min(rows, snap.dimension));
  const wheels = snap.dimension <= WHEEL_CAP ? snap.dimension : 0;
  const peakMag = Math.sqrt(snap.peak) || 1;

  return (
    <PanelFrame
      title="State vector"
      subtitle="Interleaved [re, im] Float64 buffer — the exact layout R6.2a will export from wasm-bindgen."
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Qutrits" value={String(n)} hint="register width" />
        <Stat label="Basis states" value={snap.dimension.toLocaleString()} hint={`3^${n}`} />
        <Stat
          label="Buffer"
          value={formatBytes(stateBytes(n))}
          hint="2 × f64 per amplitude"
        />
        <Stat
          label="Norm"
          value={norm.toFixed(9)}
          hint={`Σ|α|² · ${support.toLocaleString()} states in support`}
        />
      </div>

      {wheels > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold">Phase wheels</h2>
          <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2">
            <p className="text-sm text-muted-foreground">
              Radius ∝ |α<sub>k</sub>| (relative to the largest amplitude), hue ∝ arg(α<sub>k</sub>).
              Shown up to 3⁴ = 81 states.
            </p>
            <PhaseLegend />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: wheels }, (_, k) => (
              <Wheel
                key={k}
                re={snap.amplitudes[2 * k]}
                im={snap.amplitudes[2 * k + 1]}
                label={ketLabel(k, n)}
                peakMag={peakMag}
              />
            ))}
          </div>
        </div>
      )}

      <div className="min-h-0">
        <div className="mb-2 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">Amplitudes by probability</h2>
          <div className="flex gap-1">
            {[16, 64, 243].map((r) => (
              <Button
                key={r}
                size="sm"
                variant={rows === r ? 'secondary' : 'ghost'}
                onClick={() => setRows(r)}
                data-testid={`button-rows-${r}`}
                className="font-mono text-xs"
              >
                {r}
              </Button>
            ))}
          </div>
        </div>
        <div className="pane-scroll max-h-[46vh] rounded-lg border border-card-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-[1] bg-card">
              <tr className="border-b border-card-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium">k</th>
                <th className="px-3 py-2 font-medium">ket</th>
                <th className="px-3 py-2 font-medium">re</th>
                <th className="px-3 py-2 font-medium">im</th>
                <th className="px-3 py-2 font-medium normal-case">|α|²</th>
                <th className="w-[28%] px-3 py-2 font-medium">weight</th>
              </tr>
            </thead>
            <tbody className="font-mono tnum">
              {visible.map((k) => {
                const re = snap.amplitudes[2 * k];
                const im = snap.amplitudes[2 * k + 1];
                const p = snap.probabilities[k];
                return (
                  <tr
                    key={k}
                    className="border-b border-border/50 last:border-0"
                    data-testid={`row-amplitude-${k}`}
                  >
                    <td className="px-3 py-1.5 text-muted-foreground">{k}</td>
                    <td className="px-3 py-1.5">|{ketLabel(k, n)}⟩</td>
                    <td className="px-3 py-1.5">{re.toFixed(6)}</td>
                    <td className="px-3 py-1.5">{im.toFixed(6)}</td>
                    <td className="px-3 py-1.5">{p.toExponential(3)}</td>
                    <td className="px-3 py-1.5">
                      <div className="h-1.5 w-full rounded-full bg-muted">
                        <div
                          className="h-1.5 rounded-full"
                          style={{
                            width: `${snap.peak > 0 ? (p / snap.peak) * 100 : 0}%`,
                            background: phaseColor(Math.atan2(im, re), 52),
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </PanelFrame>
  );
}

function PhaseLegend() {
  const stops = [
    { arg: 0, label: '0' },
    { arg: (2 * Math.PI) / 3, label: '2π/3' },
    { arg: (4 * Math.PI) / 3, label: '4π/3' },
  ];
  return (
    <div className="flex items-center gap-3">
      {stops.map((s) => (
        <span key={s.label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: phaseColor(s.arg, 56) }}
          />
          <span className="font-mono">{s.label}</span>
        </span>
      ))}
    </div>
  );
}

function Wheel({
  re,
  im,
  label,
  peakMag,
}: {
  re: number;
  im: number;
  label: string;
  peakMag: number;
}) {
  const mag = Math.hypot(re, im);
  const arg = Math.atan2(im, re);
  const r = 15 * Math.min(1, mag / peakMag);
  const color = phaseColor(arg, 58);
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" aria-label={`|${label}⟩`} role="img">
      <title>{`|${label}⟩  |α| = ${mag.toFixed(4)}  arg = ${arg.toFixed(3)}`}</title>
      <circle cx="18" cy="18" r="15.5" fill="hsl(var(--muted))" stroke="hsl(var(--border))" />
      {mag > 1e-9 && (
        <>
          <circle cx="18" cy="18" r={r} fill={color} opacity="0.32" />
          <line
            x1="18"
            y1="18"
            x2={18 + r * Math.cos(arg)}
            y2={18 - r * Math.sin(arg)}
            stroke={color}
            strokeWidth="2"
            strokeLinecap="round"
          />
        </>
      )}
    </svg>
  );
}
