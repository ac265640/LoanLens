import { useEffect, useRef } from 'react';

/**
 * Plain SVG + CSS hexagon background. No Tailwind, no shadcn, no dependencies.
 * A faint hex grid sits underneath; a brighter copy of the same grid is revealed
 * through a radial mask that follows the cursor (with a little easing).
 *
 * It listens on its parent element, so drop it inside any position:relative container.
 * Styles live in home.css (.hex-bg, .hex-layer, .hex-glow, .hex-halo).
 *
 * Hex size: change S below and the numbers in the two <path>s scale with it.
 * S = 28 -> W = 48.4974 (S * sqrt(3)), tile height = 84 (S * 3).
 */

const PATH =
    'M24.2487 0 L48.4974 14 L48.4974 42 L24.2487 56 L0 42 L0 14 Z M24.2487 56 L24.2487 84';

export default function HexBackground({ className = '' }: { className?: string }) {
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const el = ref.current;
        const host = el?.parentElement;
        if (!el || !host) return;

        let x = 0,
            y = 0,
            tx = 0,
            ty = 0,
            raf = 0,
            seeded = false;

        const tick = () => {
            x += (tx - x) * 0.14;
            y += (ty - y) * 0.14;
            el.style.setProperty('--mx', `${x}px`);
            el.style.setProperty('--my', `${y}px`);
            raf = Math.abs(tx - x) > 0.5 || Math.abs(ty - y) > 0.5 ? requestAnimationFrame(tick) : 0;
        };

        const onMove = (e: PointerEvent) => {
            const r = el.getBoundingClientRect();
            tx = e.clientX - r.left;
            ty = e.clientY - r.top;
            if (!seeded) {
                x = tx;
                y = ty;
                seeded = true;
            }
            el.dataset.active = '1';
            if (!raf) raf = requestAnimationFrame(tick);
        };
        const onLeave = () => {
            el.dataset.active = '0';
        };

        host.addEventListener('pointermove', onMove);
        host.addEventListener('pointerleave', onLeave);
        return () => {
            host.removeEventListener('pointermove', onMove);
            host.removeEventListener('pointerleave', onLeave);
            if (raf) cancelAnimationFrame(raf);
        };
    }, []);

    return (
        <div ref={ref} className={`hex-bg ${className}`} aria-hidden="true">
            <svg className="hex-layer hex-base" width="100%" height="100%">
                <defs>
                    <pattern id="ll-hex-base" width="48.4974" height="84" patternUnits="userSpaceOnUse">
                        <path d={PATH} fill="none" strokeWidth="1" style={{ stroke: 'var(--hex-line)' }} />
                    </pattern>
                </defs>
                <rect width="100%" height="100%" fill="url(#ll-hex-base)" />
            </svg>

            <div className="hex-halo" />

            <svg className="hex-layer hex-glow" width="100%" height="100%">
                <defs>
                    <pattern id="ll-hex-glow" width="48.4974" height="84" patternUnits="userSpaceOnUse">
                        <path d={PATH} fill="none" strokeWidth="1.5" style={{ stroke: 'var(--scored)' }} />
                    </pattern>
                </defs>
                <rect width="100%" height="100%" fill="url(#ll-hex-glow)" />
            </svg>
        </div>
    );
}