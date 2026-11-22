/**
 * Small dependency-free SVG charts. Colours come from CSS tokens
 * (`--series-*`, `--status-*`) defined for light and dark mode in admin.css.
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { Tone } from './labels.ts';

function useWidth<T extends HTMLElement>(fallback = 600) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth || fallback);
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fallback]);
  return { ref, width };
}

/** Whole-number tick step (1, 2, 5 × 10^k) giving about three intervals. */
function niceStep(max: number): number {
  const raw = Math.max(1, max / 3);
  const exp = 10 ** Math.floor(Math.log10(raw));
  const n = raw / exp;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * exp;
}

export interface SeriesDef {
  key: string;
  label: string;
  color: string;
  values: number[];
  area?: boolean;
}

/** Line chart with a shared crosshair tooltip. One y-axis only. */
export function TimeSeriesChart({
  labels,
  series,
  height = 220,
  ariaLabel,
}: {
  labels: string[];
  series: SeriesDef[];
  height?: number;
  ariaLabel: string;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pad = { top: 12, right: 12, bottom: 26, left: 36 };
  const innerW = Math.max(10, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;
  const n = labels.length;
  const step = niceStep(Math.max(1, ...series.flatMap((s) => s.values)));
  const max = Math.max(step, Math.ceil(Math.max(1, ...series.flatMap((s) => s.values)) / step) * step);
  const x = (i: number) => pad.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(innerW / 70))));

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - rect.left) / rect.width;
    setHover(Math.max(0, Math.min(n - 1, Math.round(rel * (n - 1)))));
  };

  return (
    <div className="chart" ref={ref}>
      <div className="legend" aria-hidden="true">
        {series.map((s) => (
          <span key={s.key} className="legend-item">
            <span className="legend-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={pad.left + innerW} y1={y(t)} y2={y(t)} className="grid-line" />
            <text x={pad.left - 8} y={y(t)} className="axis-text" textAnchor="end" dominantBaseline="middle">
              {Math.round(t)}
            </text>
          </g>
        ))}
        {labels.map((l, i) =>
          i % labelEvery === 0 || i === n - 1 ? (
            <text key={i} x={x(i)} y={height - 6} className="axis-text" textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}>
              {l}
            </text>
          ) : null,
        )}
        {series.map((s) => {
          const points = s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
          return (
            <g key={s.key}>
              {s.area && (
                <polygon
                  points={`${x(0)},${y(0)} ${points} ${x(n - 1)},${y(0)}`}
                  fill={s.color}
                  opacity={0.12}
                />
              )}
              <polyline points={points} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + innerH} className="crosshair" />
            {series.map((s) => (
              <circle key={s.key} cx={x(hover)} cy={y(s.values[hover] ?? 0)} r={4.5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            ))}
          </g>
        )}
        <rect
          x={pad.left}
          y={pad.top}
          width={innerW}
          height={innerH}
          fill="transparent"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hover !== null && (
        <div
          className="tooltip"
          style={{ left: Math.min(width - 170, Math.max(0, x(hover) + 10)), top: pad.top }}
          role="presentation"
        >
          <div className="tooltip-title">{labels[hover]}</div>
          {series.map((s) => (
            <div key={s.key} className="tooltip-row">
              <span className="legend-swatch" style={{ background: s.color }} />
              <span>{s.label}</span>
              <strong>{s.values[hover] ?? 0}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Sparkline({
  values,
  width = 96,
  height = 26,
  color = 'var(--series-1)',
  label,
}: {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  label: string;
}) {
  const max = Math.max(1, ...values);
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - (v / max) * (height - 4)).toFixed(1)}`).join(' ');
  return (
    <svg width={width} height={height} role="img" aria-label={label} className="sparkline">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

const TONE_VAR: Record<Tone, string> = {
  good: 'var(--status-good)',
  warning: 'var(--status-warning)',
  serious: 'var(--status-serious)',
  critical: 'var(--status-critical)',
  info: 'var(--series-1)',
  neutral: 'var(--neutral-mark)',
  muted: 'var(--muted-mark)',
};

export interface Segment {
  key: string;
  label: string;
  value: number;
  tone: Tone;
}

/** One 100% bar with a legend that carries labels and values (identity is never colour alone). */
export function StackedBar({ segments, ariaLabel }: { segments: Segment[]; ariaLabel: string }) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div className="stacked">
      <div className="stacked-bar" role="img" aria-label={ariaLabel}>
        {total === 0 && <div className="stacked-empty" />}
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <div
              key={s.key}
              className={`stacked-seg ${hover && hover !== s.key ? 'is-dim' : ''}`}
              style={{ flexGrow: s.value, background: TONE_VAR[s.tone] }}
              title={`${s.label}: ${s.value}`}
              onPointerEnter={() => setHover(s.key)}
              onPointerLeave={() => setHover(null)}
            />
          ))}
      </div>
      <ul className="stacked-legend">
        {segments.map((s) => (
          <li key={s.key} onPointerEnter={() => setHover(s.key)} onPointerLeave={() => setHover(null)}>
            <span className="legend-swatch" style={{ background: TONE_VAR[s.tone] }} />
            <span className="stacked-label">{s.label}</span>
            <strong>{s.value}</strong>
            <span className="muted">{total ? `${Math.round((s.value / total) * 100)}%` : '—'}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Horizontal bars in one hue; values are printed as text next to each bar. */
export function BarList({
  items,
  format = (v) => String(v),
}: {
  items: { key: string; label: string; value: number; hint?: string }[];
  format?: (v: number) => string;
}) {
  const max = useMemo(() => Math.max(1, ...items.map((i) => i.value)), [items]);
  return (
    <ul className="barlist">
      {items.map((item) => (
        <li key={item.key} title={item.hint}>
          <div className="barlist-row">
            <span className="barlist-label">{item.label}</span>
            <strong>{format(item.value)}</strong>
          </div>
          <div className="barlist-track">
            <div className="barlist-fill" style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Metric vs target: a bar with the target marked; status shown as text, too. */
export function TargetMeter({
  value,
  target,
  direction,
  max,
  format,
}: {
  value: number;
  target: number;
  direction: 'min' | 'max';
  max: number;
  format: (v: number) => string;
}) {
  const ok = direction === 'min' ? value >= target : value <= target;
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div className="meter" aria-label={`${format(value)}, cel ${direction === 'min' ? '≥' : '≤'} ${format(target)}`}>
      <div className="meter-track">
        <div className={`meter-fill ${ok ? 'is-ok' : 'is-bad'}`} style={{ width: pct(value) }} />
        <div className="meter-target" style={{ left: pct(target) }} title={`Cel: ${format(target)}`} />
      </div>
    </div>
  );
}
