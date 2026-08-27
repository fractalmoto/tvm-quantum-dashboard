# TVM Quantum Dashboard

Browser front-end for the TrinaryVM quantum simulation subsystem (spec workstream **R6.2b**).

This repository holds the front-end only. It is deliberately decoupled from `trinaryvm_rust`: all
quantum state comes through a single adapter interface, so the Rust/WASM core can be wired in later
without touching a panel. See [Engine seam](#engine-seam).

Tracked in Linear as [TVM Quantum Dashboard](https://linear.app/trinaryvm/project/tvm-quantum-dashboard-01634ac9227f/overview).

## Status

**Phase 0 complete** ([TRI-185](https://linear.app/trinaryvm/issue/TRI-185)) — app shell, four panels,
and a pure-TypeScript mock engine so UI work never blocks on the Rust side.

| Workstream | Issue | State |
| --- | --- | --- |
| R6.2b Phase 0 — shell + mock engine | TRI-185 | Done |
| R6.2a — WASM target build | TRI-188 | Todo |
| R6.2c — RPC daemon wiring | TRI-187 | Todo |
| R6.2b Phase 1 — engine integration | TRI-186 | Blocked on TRI-188/187 |
| R6.2b Phase 2 — composer canvas + CodeMirror REPL | TRI-184 | Todo |
| SVP lattice core (Rust/WASM) | TRI-183 | Todo |

## Stack

Vite · React 18 · TypeScript · Tailwind. No state-management dependency — React context plus
reducers, per the project's zero-dependency ethos.

```bash
npm install
npm run dev      # http://localhost:5000
npm run build    # static bundle to dist/public
npx tsc --noEmit
npx tsx script/engine.test.ts
npx tsx script/interpreter.test.ts
```

The build is static; `server/` is inherited scaffolding and no route is required at runtime.

## Panels

- **Circuit** — click-to-append gate composer (H X Z S T, CX CZ) with target/control selection, an
  SVG circuit diagram, exact undo, and measurement. Drag-and-drop lands in Phase 2.
- **State vector** — phase wheels (radius from |α|, hue from arg α) plus a probability-sorted
  amplitude table. Norm readout doubles as a sanity check on the engine.
- **REPL** — `.qtest` command surface, including the R6.2d golden Hadamard-uniformity test.
  CodeMirror 6 replaces the plain input in Phase 2 over the same grammar.
- **SVP / lattice** — 2D projection of the balanced-ternary coefficient box {−1,0,+1}^n against a
  deterministic seeded integer basis, with Gram–Schmidt length readout.

## Engine seam

`client/src/lib/quantum/types.ts` defines `QuantumEngineAdapter` — the **only** module the UI is
allowed to import for state. Amplitudes cross the boundary as an interleaved
`Float64Array` of length `2 · 3^n` (`[re0, im0, re1, im1, …]`), chosen to be byte-identical to the
planned `wasm-bindgen` zero-copy export so TRI-186 is a swap rather than a rewrite.

Dispatch rule surfaced in the status bar:

| Register width | Backend |
| --- | --- |
| n ≤ 10 | in-browser WASM (`trinaryvm_quantum_wasm`) |
| n > 10 | native RPC daemon, `tvm quantum --server --port 9546` at `127.0.0.1:9546` |

The mock engine is hard-capped at **9 qutrits** (19,683 states, 307.5 KB) so it can never be
mistaken for the real backend.

## Conventions the Rust core must match

Documented in the header of `client/src/lib/quantum/mockEngine.ts`. Divergence here silently
mislabels every readout.

- ω = exp(2πi/3); qutrit 0 is the **most significant** trit.
- Digits are stored unsigned 0,1,2 and displayed balanced −1,0,+1.
- **The register zero state is the all-zero digit vector at index `(3^n − 1)/2`** — the middle of the
  index range, *not* index 0. Index 0 is |−…−⟩.
- X is the shift |t⟩ → |t+1 mod 3⟩. Z is the clock ω^t. H is the Chrestenson transform
  H[j][k] = ω^(jk)/√3. S = Z^(1/3), T = Z^(1/9).
- CX: |c,t⟩ → |c, t+c mod 3⟩. CZ: phase ω^(c·t).

Verified in `script/engine.test.ts`: X³ = I, H⁴ = I, Z³ = I, S³ = Z, T⁹ = Z, and H^⊗n uniformity to
~1e-16 for n = 1, 2, 3, 5.

## Scope boundary — visualization is not a security claim

The lattice panel visualises **3^n qutrit coefficient vectors**. That is a rendering and
WASM-scaling concern. It is *not* the TriFHE cryptographic ring-dimension ladder
(n = 27, 81, 243, 729, 2187), and raw 3^n keyspace is **not** a public-key hardness argument.
Any hardness claim must be stated as the minimum cost of known structured attacks — primal, dual,
hybrid, BKW, small- and sparse-secret — against the exact LWE/RLWE instance, with reproducible
`(n, q, χ, m)` parameter records. The UI is written to keep those two ideas apart on purpose.

## License

Private. © Favourable Group.
