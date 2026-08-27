import { Undo2, Trash2, Activity } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useQuantum } from '@/lib/quantum/store';
import { validateGate } from '@/lib/quantum/interpreter';
import { ketLabel, type GateName } from '@/lib/quantum/types';
import { PanelFrame, EmptyState } from '@/components/panels/shell';

const SINGLES: Array<{ g: GateName; note: string }> = [
  { g: 'H', note: 'Chrestenson — uniform superposition' },
  { g: 'X', note: 'shift |t⟩ → |t+1⟩' },
  { g: 'Z', note: 'clock, phase ω^t' },
  { g: 'S', note: 'Z^(1/3) phase' },
  { g: 'T', note: 'Z^(1/9) phase' },
];
const PAIRS: Array<{ g: GateName; note: string }> = [
  { g: 'CX', note: 'controlled shift' },
  { g: 'CZ', note: 'controlled clock' },
];

const LANE = 44;
const COL = 46;

export function CircuitPanel() {
  const { state, snap, pushGate, undo, clearCircuit, measure, log, select } = useQuantum();
  const n = state.n;
  const tgt = Math.min(state.sel.target, n - 1);
  const ctl = Math.min(state.sel.control, n - 1);

  const add = (g: GateName) => {
    const twoQutrit = g === 'CX' || g === 'CZ';
    // Same validator the .qtest interpreter uses, so palette clicks and typed
    // commands can never disagree about what is a legal op.
    const invalid = validateGate(g, tgt, twoQutrit ? ctl : undefined, n);
    if (invalid) {
      log([{ kind: 'err', text: invalid }]);
      return;
    }
    pushGate(twoQutrit ? { gate: g, target: tgt, control: ctl } : { gate: g, target: tgt });
    log([
      {
        kind: 'in',
        text: twoQutrit ? `${g.toLowerCase()} ${ctl} ${tgt}` : `${g.toLowerCase()} ${tgt}`,
      },
    ]);
  };

  const width = Math.max(state.ops.length * COL + 96, 320);

  return (
    <PanelFrame
      title="Circuit"
      subtitle="Phase 0 composer — click a gate to append. Drag-and-drop editing lands in Phase 2 (TRI-184)."
      actions={
        <>
          <Button variant="outline" size="sm" onClick={measure} data-testid="button-measure">
            <Activity className="mr-1.5 h-3.5 w-3.5" /> Measure
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={undo}
            disabled={!state.ops.length && !state.collapse}
            data-testid="button-undo"
          >
            <Undo2 className="mr-1.5 h-3.5 w-3.5" /> Undo
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={clearCircuit}
            disabled={!state.ops.length}
            data-testid="button-clear-circuit"
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Clear
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <Selector
            label="Target"
            value={tgt}
            max={n - 1}
            onChange={(q) => select('target', q)}
            id="target"
          />
          <Selector
            label="Control"
            value={ctl}
            max={n - 1}
            onChange={(q) => select('control', q)}
            id="control"
          />
        </div>

        <div className="flex flex-wrap gap-4">
          <GateGroup label="Single qutrit" items={SINGLES} onPick={add} />
          <GateGroup label="Two qutrit" items={PAIRS} onPick={add} />
        </div>

        {snap.error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {snap.error}
          </p>
        )}

        {state.ops.length === 0 ? (
          <EmptyState
            title="No gates yet"
            body="Append a gate above, or run a `.qtest` script in the REPL panel. The circuit replays from scratch on every change, so Undo is exact."
          />
        ) : (
          <div className="pane-scroll rounded-lg border border-card-border bg-card p-4">
            <svg
              width={width}
              height={n * LANE + 28}
              className="text-muted-foreground"
              data-testid="img-circuit"
            >
              {Array.from({ length: n }, (_, q) => (
                <g key={q}>
                  <text
                    x={4}
                    y={q * LANE + 30}
                    className="fill-muted-foreground font-mono text-[11px]"
                  >
                    q{q}
                  </text>
                  <line
                    x1={34}
                    x2={width - 12}
                    y1={q * LANE + 26}
                    y2={q * LANE + 26}
                    stroke="currentColor"
                    strokeWidth="1"
                    opacity="0.35"
                  />
                </g>
              ))}
              {state.ops.map((op, i) => {
                const x = 56 + i * COL;
                const y = op.target * LANE + 26;
                const two = op.control !== undefined;
                const cy = two ? op.control! * LANE + 26 : y;
                return (
                  <g key={op.id}>
                    {two && (
                      <>
                        <line
                          x1={x}
                          x2={x}
                          y1={cy}
                          y2={y}
                          stroke="hsl(var(--primary))"
                          strokeWidth="1.5"
                        />
                        <circle cx={x} cy={cy} r="5" fill="hsl(var(--primary))" />
                      </>
                    )}
                    <rect
                      x={x - 15}
                      y={y - 14}
                      width="30"
                      height="28"
                      rx="5"
                      fill="hsl(var(--primary) / 0.14)"
                      stroke="hsl(var(--primary))"
                      strokeWidth="1.25"
                    />
                    <text
                      x={x}
                      y={y + 5}
                      textAnchor="middle"
                      className="fill-foreground font-mono text-[11px] font-semibold"
                    >
                      {two ? op.gate.slice(1) : op.gate}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary" className="tnum font-mono">
            depth {state.ops.length}
          </Badge>
          {state.collapse && (
            <Badge variant="outline" className="tnum font-mono" data-testid="badge-collapsed">
              collapsed → |{ketLabel(state.collapse.outcome, n)}⟩ (k = {state.collapse.outcome})
            </Badge>
          )}
        </div>
      </div>
    </PanelFrame>
  );
}

function Selector({
  label,
  value,
  max,
  onChange,
  id,
}: {
  label: string;
  value: number;
  max: number;
  onChange: (v: number) => void;
  id: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <div className="flex gap-1">
        {Array.from({ length: max + 1 }, (_, q) => (
          <button
            key={q}
            onClick={() => onChange(q)}
            data-testid={`button-${id}-${q}`}
            aria-pressed={value === q}
            className={`h-8 w-8 rounded-md border font-mono text-xs tnum transition-colors ${
              value === q
                ? 'border-primary bg-primary/15 text-foreground'
                : 'border-border text-muted-foreground hover:bg-accent'
            }`}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function GateGroup({
  label,
  items,
  onPick,
}: {
  label: string;
  items: Array<{ g: GateName; note: string }>;
  onPick: (g: GateName) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <div className="flex flex-wrap gap-1.5">
        {items.map(({ g, note }) => (
          <button
            key={g}
            title={note}
            onClick={() => onPick(g)}
            data-testid={`button-gate-${g}`}
            className="h-9 min-w-11 rounded-md border border-border bg-card px-2.5 font-mono text-sm font-semibold text-foreground transition-colors hover:border-primary hover:bg-primary/10"
          >
            {g}
          </button>
        ))}
      </div>
    </div>
  );
}
