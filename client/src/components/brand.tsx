/** Geometric mark: a trit triangle — three states, one centre. */
export function Logo({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      aria-label="TrinaryVM"
      role="img"
      data-testid="img-logo"
    >
      <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="1.5" opacity="0.35" />
      <path
        d="M16 5.5 L26.5 23.5 L5.5 23.5 Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="5.5" r="2.75" fill="currentColor" />
      <circle cx="26.5" cy="23.5" r="2.4" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="16" cy="17.5" r="1.6" fill="currentColor" opacity="0.6" />
    </svg>
  );
}

/**
 * Shared phase colormap. Defined once here; the state-vector panel, the phase
 * wheels and the SVP lattice panel (TRI-182) must all read from this so that
 * hue means the same thing in every view.
 */
export function phaseColor(arg: number, lightness = 60, alpha = 1): string {
  // Anchor zero phase at the interface's cyan primary, then travel the wheel.
  const deg = ((arg / (Math.PI * 2)) * 360 + PHASE_ORIGIN + 720) % 360;
  return `hsl(${deg.toFixed(1)} 74% ${lightness}% / ${alpha})`;
}

/** Hue (deg) assigned to arg = 0. Matches --primary so |0…0⟩ reads as "on brand". */
export const PHASE_ORIGIN = 187;

export const TRIT_GLYPH = ['−', '0', '+'] as const;

export function tritColor(t: number): string {
  if (t < 0) return 'hsl(var(--trit-neg))';
  if (t > 0) return 'hsl(var(--trit-pos))';
  return 'hsl(var(--trit-zero))';
}
