import { useEffect, useRef } from "react";

const LINES = 120;

export default function Wave() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext?.("2d");
    if (!element || !context) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? true;
    let width = 0;
    let height = 0;
    let time = 0;
    let frame = 0;

    function size() {
      if (!element || !context) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = element.clientWidth;
      height = element.clientHeight;
      element.width = width * ratio;
      element.height = height * ratio;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    function draw() {
      if (!context) return;
      context.clearRect(0, 0, width, height);
      const step = Math.max(5, width / 220);
      for (let line = 0; line < LINES; line++) {
        const k = line / (LINES - 1);
        context.strokeStyle = `rgba(40, 170, 100, ${0.1 + 0.09 * Math.sin(k * Math.PI)})`;
        context.lineWidth = 0.6;
        context.beginPath();
        for (let x = -40; x <= width + 40; x += step) {
          const u = x / width;
          const phase = k * 0.8;
          const y =
            height * (0.95 - 0.75 * u) +
            Math.sin(u * 6 + time + phase) * height * 0.22 +
            Math.sin(u * 2.3 - time * 0.6 + phase * 0.5) * height * 0.07 +
            (k - 0.5) * height * 0.2;
          if (x === -40) context.moveTo(x, y);
          else context.lineTo(x, y);
        }
        context.stroke();
      }
    }

    function tick() {
      time += 0.0045;
      draw();
      if (!still) frame = requestAnimationFrame(tick);
    }

    function resize() {
      size();
      draw();
    }

    size();
    tick();
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div className="live" aria-hidden="true">
      <canvas ref={canvas} />
    </div>
  );
}
