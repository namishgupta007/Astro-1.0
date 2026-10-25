import { useEffect, useRef } from 'react';

/**
 * Cinematic Deep Space Canvas Background for 2D Graph
 * Renders rich cosmic nebula dust (magenta/purple on right, cyan on left)
 * and starry sky matching the reference snapshot.
 */
export default function GalaxyBackground2D() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId;
    let width = (canvas.width = canvas.parentElement?.clientWidth || window.innerWidth);
    let height = (canvas.height = canvas.parentElement?.clientHeight || window.innerHeight);

    // Stars
    const starCount = 400;
    const stars = [];
    for (let i = 0; i < starCount; i++) {
      stars.push({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() * 1.3 + 0.3,
        alpha: Math.random() * 0.7 + 0.2,
        twinkleSpeed: (Math.random() - 0.5) * 0.015,
        color: i % 4 === 0 ? '#38bdf8' : i % 6 === 0 ? '#f43f5e' : i % 8 === 0 ? '#fb923c' : '#ffffff',
      });
    }

    const render = () => {
      // Base deep space navy
      ctx.fillStyle = '#03050d';
      ctx.fillRect(0, 0, width, height);

      // 1. Right-side vibrant magenta/purple cosmic nebula (matches reference screenshot)
      const gradRight = ctx.createRadialGradient(
        width * 0.82,
        height * 0.42,
        40,
        width * 0.82,
        height * 0.42,
        width * 0.48
      );
      gradRight.addColorStop(0, 'rgba(236, 72, 153, 0.16)');
      gradRight.addColorStop(0.35, 'rgba(168, 85, 247, 0.11)');
      gradRight.addColorStop(0.7, 'rgba(139, 92, 246, 0.04)');
      gradRight.addColorStop(1, 'rgba(3, 5, 13, 0)');
      ctx.fillStyle = gradRight;
      ctx.beginPath();
      ctx.arc(width * 0.82, height * 0.42, width * 0.48, 0, Math.PI * 2);
      ctx.fill();

      // 2. Left-side subtle cyan nebula
      const gradLeft = ctx.createRadialGradient(
        width * 0.18,
        height * 0.55,
        30,
        width * 0.18,
        height * 0.55,
        width * 0.38
      );
      gradLeft.addColorStop(0, 'rgba(6, 182, 212, 0.10)');
      gradLeft.addColorStop(0.5, 'rgba(14, 165, 233, 0.04)');
      gradLeft.addColorStop(1, 'rgba(3, 5, 13, 0)');
      ctx.fillStyle = gradLeft;
      ctx.beginPath();
      ctx.arc(width * 0.18, height * 0.55, width * 0.38, 0, Math.PI * 2);
      ctx.fill();

      // 3. Center subtle warm solar glow
      const gradCenter = ctx.createRadialGradient(
        width * 0.45,
        height * 0.72,
        20,
        width * 0.45,
        height * 0.72,
        width * 0.35
      );
      gradCenter.addColorStop(0, 'rgba(251, 146, 60, 0.06)');
      gradCenter.addColorStop(1, 'rgba(3, 5, 13, 0)');
      ctx.fillStyle = gradCenter;
      ctx.beginPath();
      ctx.arc(width * 0.45, height * 0.72, width * 0.35, 0, Math.PI * 2);
      ctx.fill();

      // 4. Twinkling stars
      stars.forEach((star) => {
        star.alpha += star.twinkleSpeed;
        if (star.alpha > 0.95 || star.alpha < 0.2) {
          star.twinkleSpeed = -star.twinkleSpeed;
        }

        ctx.fillStyle = star.color;
        ctx.globalAlpha = Math.max(0.1, Math.min(1, star.alpha));
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
        ctx.fill();
      });

      ctx.globalAlpha = 1.0;
      animId = requestAnimationFrame(render);
    };

    render();

    const handleResize = () => {
      if (!canvas.parentElement) return;
      width = canvas.width = canvas.parentElement.clientWidth;
      height = canvas.height = canvas.parentElement.clientHeight;
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 1,
      }}
    />
  );
}
