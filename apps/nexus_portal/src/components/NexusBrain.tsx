/**
 * NexusBrain — Animated circuit-brain logo.
 *
 * Uses the actual Nexus brain PNG with CSS animations:
 *   • Breathing pulse (scale) animation
 *   • Teal ↔ navy glow color shift
 *   • Transparent background
 */
export default function NexusBrain({ size = 38 }: { size?: number }) {
    return (
        <>
            <style>{`
                @keyframes nexusPulse {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.06); }
                }
                @keyframes nexusGlow {
                    0%, 100% {
                        filter: drop-shadow(0 0 4px rgba(0,206,209,0.6));
                    }
                    50% {
                        filter: drop-shadow(0 0 8px rgba(0,0,128,0.5));
                    }
                }
                @keyframes nexusHueShift {
                    0%, 100% { filter: drop-shadow(0 0 6px rgba(0,206,209,0.7)) hue-rotate(0deg); }
                    50%  { filter: drop-shadow(0 0 8px rgba(0,0,128,0.6)) hue-rotate(-30deg); }
                }
                .nexus-brain-wrap {
                    animation: nexusPulse 3s ease-in-out infinite;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                }
                .nexus-brain-img {
                    animation: nexusHueShift 4s ease-in-out infinite;
                    width: 100%;
                    height: 100%;
                    object-fit: contain;
                }
            `}</style>
            <span
                className="nexus-brain-wrap"
                style={{ width: size, height: size }}
            >
                <img
                    className="nexus-brain-img"
                    src="/nexus-brain.png"
                    alt="Nexus Brain"
                    width={size}
                    height={size}
                />
            </span>
        </>
    );
}
