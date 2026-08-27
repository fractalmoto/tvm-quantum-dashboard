import { useState } from 'react';
import { CircuitBoard, Grid3x3, Terminal, Waves, Minus, Plus, AlertTriangle } from 'lucide-react';
import { Logo } from '@/components/brand';
import { ThemeToggle } from '@/components/theme';
import { QuantumProvider, useQuantum } from '@/lib/quantum/store';
import { CircuitPanel } from '@/components/panels/CircuitPanel';
import { StatePanel } from '@/components/panels/StatePanel';
import { ReplPanel } from '@/components/panels/ReplPanel';
import { LatticePanel } from '@/components/panels/LatticePanel';
import { WASM_QUTRIT_CEILING, formatBytes, stateBytes } from '@/lib/quantum/types';
import type { EngineKind } from '@/lib/quantum/types';

type PanelId = 'circuit' | 'state' | 'repl' | 'lattice';

const NAV: Array<{ id: PanelId; label: string; icon: typeof CircuitBoard }> = [
  { id: 'circuit', label: 'Circuit', icon: CircuitBoard },
  { id: 'state', label: 'State vector', icon: Waves },
  { id: 'repl', label: 'REPL', icon: Terminal },
  { id: 'lattice', label: 'SVP / lattice', icon: Grid3x3 },
];

export default function DashboardPage() {
  return (
    <QuantumProvider>
      <Shell />
    </QuantumProvider>
  );
}

function Shell() {
  const [panel, setPanel] = useState<PanelId>('circuit');
  const { state, snap, maxQutrits, setQutrits } = useQuantum();

  return (
    <div className="grid h-full grid-cols-1 grid-rows-[1fr_auto] md:grid-cols-[228px_1fr]">
      <aside className="hidden min-h-0 flex-col border-r border-sidebar-border bg-sidebar md:flex md:row-span-1">
        <div className="flex items-center gap-2.5 px-4 py-4 text-sidebar-primary">
          <Logo className="h-7 w-7" />
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-semibold text-sidebar-foreground">
              TVM Quantum
            </p>
            <p className="truncate text-xs text-muted-foreground">Dashboard · Phase 0</p>
          </div>
        </div>

        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setPanel(id)}
              aria-current={panel === id ? 'page' : undefined}
              data-testid={`link-panel-${id}`}
              className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors ${
                panel === id
                  ? 'bg-sidebar-accent font-medium text-sidebar-foreground'
                  : 'text-muted-foreground hover:bg-sidebar-accent/60'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{label}</span>
            </button>
          ))}
        </nav>

        <div className="mt-6 px-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Register width
          </p>
          <div className="mt-2 flex items-center gap-2">
            <StepButton
              label="Fewer qutrits"
              disabled={state.n <= 1}
              onClick={() => setQutrits(state.n - 1)}
              testId="button-qutrits-dec"
            >
              <Minus className="h-3.5 w-3.5" />
            </StepButton>
            <span className="min-w-8 text-center font-mono text-base font-semibold tnum">
              {state.n}
            </span>
            <StepButton
              label="More qutrits"
              disabled={state.n >= maxQutrits}
              onClick={() => setQutrits(state.n + 1)}
              testId="button-qutrits-inc"
            >
              <Plus className="h-3.5 w-3.5" />
            </StepButton>
          </div>
          <p className="mt-2 font-mono text-xs text-muted-foreground tnum">
            3^{state.n} = {snap.dimension.toLocaleString()}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Changing width re-allocates |0…0⟩.
          </p>
        </div>

        <div className="mt-auto px-4 py-4 text-xs text-muted-foreground">
          <p>Mock TypeScript engine.</p>
          <p className="mt-0.5">WASM lands in TRI-186.</p>
        </div>
      </aside>

      <main className="pane-scroll min-h-0">
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5 md:px-6">
          <div className="flex items-center gap-2 md:hidden">
            <Logo className="h-5 w-5 text-primary" />
            <select
              value={panel}
              onChange={(e) => setPanel(e.target.value as PanelId)}
              aria-label="Panel"
              className="rounded-md border border-border bg-card px-2 py-1 text-sm"
            >
              {NAV.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.label}
                </option>
              ))}
            </select>
          </div>
          <p className="hidden text-xs text-muted-foreground md:block">
            trinaryvm · quantum subsystem · R6.2b
          </p>
          <div className="flex items-center gap-2">
            {/* The sidebar stepper is hidden on small screens, so mirror it here. */}
            <div className="flex items-center gap-1.5 md:hidden">
              <StepButton
                label="Fewer qutrits"
                disabled={state.n <= 1}
                onClick={() => setQutrits(state.n - 1)}
                testId="button-qutrits-dec-mobile"
              >
                <Minus className="h-3.5 w-3.5" />
              </StepButton>
              <span className="min-w-6 text-center font-mono text-sm font-semibold tnum">
                {state.n}
              </span>
              <StepButton
                label="More qutrits"
                disabled={state.n >= maxQutrits}
                onClick={() => setQutrits(state.n + 1)}
                testId="button-qutrits-inc-mobile"
              >
                <Plus className="h-3.5 w-3.5" />
              </StepButton>
            </div>
            <ThemeToggle />
          </div>
        </div>

        <div className="px-4 py-5 md:px-6 md:py-6">
          {panel === 'circuit' && <CircuitPanel />}
          {panel === 'state' && <StatePanel />}
          {panel === 'repl' && <ReplPanel />}
          {panel === 'lattice' && <LatticePanel />}
        </div>
      </main>

      <StatusBar />
    </div>
  );
}

function StepButton({
  children,
  label,
  onClick,
  disabled,
  testId,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  testId: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      data-testid={testId}
      className="flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-accent disabled:opacity-40"
    >
      {children}
    </button>
  );
}

const ENGINES: Array<{ id: EngineKind; label: string }> = [
  { id: 'wasm', label: 'WASM' },
  { id: 'rpc', label: 'RPC' },
];

function StatusBar() {
  const { state, snap, activeEngine, setOverride } = useQuantum();
  const auto = state.override === null;
  return (
    <footer className="col-span-full flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border bg-sidebar px-4 py-2 text-xs md:px-6">
      <span className="flex items-center gap-1.5">
        <span
          className="h-1.5 w-1.5 rounded-full bg-primary"
          style={{ boxShadow: '0 0 0 3px hsl(var(--primary) / 0.25)' }}
        />
        <span className="font-medium">Engine</span>
        <span className="font-mono uppercase text-primary" data-testid="status-engine">
          mock
        </span>
        <span className="text-muted-foreground">
          → would dispatch to <span className="font-mono uppercase">{activeEngine}</span>
        </span>
      </span>

      <span className="flex items-center gap-1">
        <button
          onClick={() => setOverride(null)}
          aria-pressed={auto}
          data-testid="button-dispatch-auto"
          className={`rounded px-1.5 py-0.5 font-mono transition-colors ${auto ? 'bg-primary/15 text-foreground' : 'text-muted-foreground hover:bg-accent'}`}
        >
          auto
        </button>
        {ENGINES.map((e) => (
          <button
            key={e.id}
            onClick={() => setOverride(e.id)}
            aria-pressed={state.override === e.id}
            data-testid={`button-dispatch-${e.id}`}
            className={`rounded px-1.5 py-0.5 font-mono transition-colors ${
              state.override === e.id
                ? 'bg-primary/15 text-foreground'
                : 'text-muted-foreground hover:bg-accent'
            }`}
          >
            {e.label}
          </button>
        ))}
      </span>

      <span className="text-muted-foreground tnum">
        n = <span className="font-mono text-foreground">{state.n}</span> · 3^{state.n} ={' '}
        <span className="font-mono text-foreground">{snap.dimension.toLocaleString()}</span> states ·{' '}
        <span className="font-mono text-foreground">{formatBytes(stateBytes(state.n))}</span>
      </span>

      {snap.error && (
        <span
          className="flex items-center gap-1.5 rounded bg-destructive/15 px-1.5 py-0.5 text-destructive"
          data-testid="status-engine-error"
        >
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span className="truncate font-mono" title={snap.error}>
            {snap.error}
          </span>
        </span>
      )}

      <span className="ml-auto text-muted-foreground">
        rule: n ≤ {WASM_QUTRIT_CEILING} → WASM, n &gt; {WASM_QUTRIT_CEILING} → 127.0.0.1:9546
      </span>
    </footer>
  );
}
