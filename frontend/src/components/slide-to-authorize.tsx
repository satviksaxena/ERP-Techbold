import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronRight, Lock } from "lucide-react";

const KNOB = 44;

export function SlideToAuthorize({
  onAuthorize,
  disabled,
  label = "Slide to authorize command",
}: {
  onAuthorize: () => void | Promise<void>;
  disabled?: boolean;
  label?: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const xRef = useRef(0);
  const onAuthorizeRef = useRef(onAuthorize);
  const disabledRef = useRef(disabled);
  const [x, setX] = useState(0);
  const [trackWidth, setTrackWidth] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [done, setDone] = useState(false);

  onAuthorizeRef.current = onAuthorize;
  disabledRef.current = disabled;

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const measure = () => setTrackWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  const resetKnob = useCallback(() => {
    xRef.current = 0;
    setX(0);
    setDone(false);
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const move = (e: PointerEvent) => {
      const rect = trackRef.current?.getBoundingClientRect();
      if (!rect) return;
      const max = Math.max(0, rect.width - KNOB);
      const next = Math.max(0, Math.min(max, e.clientX - rect.left - KNOB / 2));
      xRef.current = next;
      setX(next);
    };

    const up = () => {
      setDragging(false);
      const rect = trackRef.current?.getBoundingClientRect();
      const w = rect?.width ?? trackWidth;
      const max = Math.max(0, w - KNOB);
      const threshold = max * 0.92;
      const currentX = xRef.current;

      if (currentX >= threshold && !disabledRef.current) {
        xRef.current = max;
        setX(max);
        setDone(true);
        void Promise.resolve(onAuthorizeRef.current()).catch(() => {
          resetKnob();
        });
      } else {
        resetKnob();
      }
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, [dragging, trackWidth, resetKnob]);

  const maxTravel = Math.max(0, trackWidth - KNOB);
  const pct = maxTravel ? Math.min(100, (x / maxTravel) * 100) : 0;
  const locked = disabled || done;

  return (
    <div
      ref={trackRef}
      className={cn(
        "relative h-12 rounded-full border border-border bg-background/40 overflow-hidden select-none touch-none",
        disabled && "opacity-50",
        done && "glow-safe",
      )}
    >
      <div
        className="absolute inset-y-0 left-0 bg-gradient-to-r from-safe/40 via-safe/30 to-primary/40 transition-[width]"
        style={{ width: `${pct}%`, transitionDuration: dragging ? "0ms" : "200ms" }}
      />
      <div className="absolute inset-0 grid place-items-center pointer-events-none">
        <span className="font-mono text-xs uppercase tracking-[0.25em] text-muted-foreground px-14 text-center">
          {done ? "authorized · executing" : label}
        </span>
      </div>
      <button
        type="button"
        onPointerDown={(e) => {
          if (locked) return;
          e.preventDefault();
          e.currentTarget.setPointerCapture(e.pointerId);
          setDragging(true);
        }}
        className={cn(
          "absolute top-1 z-10 h-10 w-10 rounded-full grid place-items-center border border-border bg-surface-2 shadow-lg text-primary",
          locked ? "cursor-not-allowed" : "cursor-grab active:cursor-grabbing",
          done && "bg-safe text-safe-foreground border-safe",
        )}
        style={{ left: `${x + 4}px`, transitionDuration: dragging ? "0ms" : "200ms" }}
        aria-label={label}
        disabled={locked}
      >
        {done ? <Lock className="h-4 w-4" /> : <ChevronRight className="h-5 w-5" />}
      </button>
    </div>
  );
}
