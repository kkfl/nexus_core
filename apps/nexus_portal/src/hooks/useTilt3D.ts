import { useCallback, useRef } from 'react';

/**
 * useTilt3D — Apple-style 3D perspective tilt on hover.
 *
 * Tracks mouse position relative to the card center and applies
 * rotateX / rotateY transforms in real time, plus a dynamic
 * specular highlight that follows the cursor.
 *
 * Usage:
 *   const tilt = useTilt3D();
 *   <div ref={tilt.ref} {...tilt.handlers} className="nx-card-hover">
 *
 * @param intensity  Max tilt in degrees (default 8)
 * @param perspective  CSS perspective value (default 800px)
 * @param scale  Scale on hover (default 1.04)
 */
export function useTilt3D({
    intensity = 8,
    perspective = 800,
    scale = 1.04,
} = {}) {
    const ref = useRef<HTMLDivElement>(null);

    const onMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        const el = ref.current;
        if (!el) return;

        const rect = el.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        // Normalized -1 → 1
        const nx = (x - centerX) / centerX;
        const ny = (y - centerY) / centerY;

        // Rotate in opposite direction for natural feel
        const rotateY = nx * intensity;
        const rotateX = -ny * intensity;

        el.style.transform = `perspective(${perspective}px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(${scale}, ${scale}, ${scale})`;

        // Move specular highlight (the ::after pseudo via CSS variables)
        el.style.setProperty('--shine-x', `${x}px`);
        el.style.setProperty('--shine-y', `${y}px`);
    }, [intensity, perspective, scale]);

    const onMouseEnter = useCallback(() => {
        const el = ref.current;
        if (!el) return;
        el.style.transition = 'transform 0.1s ease-out';
    }, []);

    const onMouseLeave = useCallback(() => {
        const el = ref.current;
        if (!el) return;
        el.style.transition = 'transform 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
        el.style.transform = `perspective(${perspective}px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)`;
        el.style.removeProperty('--shine-x');
        el.style.removeProperty('--shine-y');
    }, [perspective]);

    return {
        ref,
        handlers: {
            onMouseMove,
            onMouseEnter,
            onMouseLeave,
        },
    };
}
