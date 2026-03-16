import React from 'react';
import { useTilt3D } from '../hooks/useTilt3D';

interface TiltCardProps {
    children: React.ReactNode;
    className?: string;
    style?: React.CSSProperties;
    onClick?: () => void;
    /** Max tilt in degrees */
    intensity?: number;
    /** Scale on hover */
    scale?: number;
}

/**
 * TiltCard — A wrapper that adds 3D perspective tilt on hover.
 *
 * Pairs with .nx-card-hover or .nx-stat-card CSS classes for
 * specular highlight, edge light sweep, and depth shadows.
 */
export function TiltCard({
    children,
    className = '',
    style,
    onClick,
    intensity = 8,
    scale = 1.04,
}: TiltCardProps) {
    const tilt = useTilt3D({ intensity, scale });

    return (
        <div
            // eslint-disable-next-line react-hooks/refs
            ref={tilt.ref}
            className={className}
            style={style}
            onClick={onClick}
            // eslint-disable-next-line react-hooks/refs
            {...tilt.handlers}
        >
            {children}
        </div>
    );
}
