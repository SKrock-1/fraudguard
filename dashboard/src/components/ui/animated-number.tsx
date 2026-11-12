"use client";

import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect } from "react";

export function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const mv = useMotionValue(0);
  const text = useTransform(() => format(mv.get()));

  useEffect(() => {
    const controls = animate(mv, value, { duration: 0.9, ease: [0.2, 0.7, 0.2, 1] });
    return () => controls.stop();
  }, [mv, value]);

  return <motion.span className="tabular">{text}</motion.span>;
}
