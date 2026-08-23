/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  size?: "md" | "sm";
  round?: boolean;
}

export function GlassIconButton({
  children,
  size = "md",
  round,
  className,
  type = "button",
  title,
  "aria-label": ariaLabel,
  ...rest
}: Props) {
  return (
    <button
      type={type}
      title={title}
      aria-label={ariaLabel ?? (typeof title === "string" ? title : undefined)}
      className={["glass-ibtn", size === "sm" ? "sm" : "", round ? "round" : "", className]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}
