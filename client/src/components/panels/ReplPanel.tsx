import { useEffect, useRef, useState } from 'react';
import { CornerDownLeft, FileCode2, Eraser } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useQuantum } from '@/lib/quantum/store';
import { GOLDEN_SCRIPT } from '@/lib/quantum/qtest';
import { runScript } from '@/lib/quantum/interpreter';
import { PanelFrame } from '@/components/panels/shell';

const LINE_STYLE: Record<string, string> = {
  in: 'text-foreground',
  out: 'text-muted-foreground',
  ok: 'text-primary',
  err: 'text-destructive',
};

export function ReplPanel() {
  const q = useQuantum();
  const { state } = q;
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [cursor, setCursor] = useState(-1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [state.log]);

  /**
   * One entry point for both typed lines and loaded scripts. The interpreter is
   * pure, so a whole script is evaluated against a locally advanced session and
   * committed in a single store update — read-only commands can never observe a
   * stale snapshot.
   */
  const exec = (source: string) => {
    const result = runScript(
      { n: state.n, ops: state.ops, collapse: state.collapse },
      source,
    );
    if (result.clearLog) q.clearLog();
    q.load(result.session);
    if (result.lines.length) q.log(result.lines);
  };

  const submit = () => {
    if (!input.trim()) return;
    setHistory((h) => [...h, input]);
    setCursor(-1);
    exec(input);
    setInput('');
  };

  const loadGolden = () => {
    q.log([{ kind: 'out', text: '— loading R6.2d golden test —' }]);
    exec(GOLDEN_SCRIPT);
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') return submit();
    if (e.key === 'ArrowUp' && history.length) {
      e.preventDefault();
      const next = cursor < 0 ? history.length - 1 : Math.max(0, cursor - 1);
      setCursor(next);
      setInput(history[next]);
    }
    if (e.key === 'ArrowDown' && cursor >= 0) {
      e.preventDefault();
      const next = cursor + 1;
      if (next >= history.length) {
        setCursor(-1);
        setInput('');
      } else {
        setCursor(next);
        setInput(history[next]);
      }
    }
  };

  return (
    <PanelFrame
      title="REPL"
      subtitle="`.qtest` command surface. Phase 2 swaps this input for a CodeMirror 6 editor over the same grammar."
      actions={
        <>
          <Button variant="outline" size="sm" onClick={loadGolden} data-testid="button-golden">
            <FileCode2 className="mr-1.5 h-3.5 w-3.5" /> Golden test
          </Button>
          <Button variant="ghost" size="sm" onClick={q.clearLog} data-testid="button-clear-log">
            <Eraser className="mr-1.5 h-3.5 w-3.5" /> Clear log
          </Button>
        </>
      }
    >
      <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-card-border bg-card">
        <div className="pane-scroll h-[52vh] p-4">
          {state.log.map((e) => (
            <pre
              key={e.id}
              className={`whitespace-pre-wrap break-words font-mono text-xs leading-relaxed ${LINE_STYLE[e.kind]}`}
              data-testid={`text-log-${e.id}`}
            >
              {e.kind === 'in' ? `› ${e.text}` : e.text}
            </pre>
          ))}
          <div ref={endRef} />
        </div>
        <div className="flex items-center gap-2 border-t border-card-border px-3 py-2">
          <span className="font-mono text-sm text-primary">›</span>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            spellCheck={false}
            placeholder="h 0"
            aria-label="qtest command"
            data-testid="input-repl"
            className="min-w-0 flex-1 bg-transparent font-mono text-sm outline-none placeholder:text-muted-foreground/60"
          />
          <Button size="sm" variant="ghost" onClick={submit} data-testid="button-run">
            <CornerDownLeft className="h-3.5 w-3.5" />
            <span className="sr-only">Run</span>
          </Button>
        </div>
      </div>
    </PanelFrame>
  );
}
