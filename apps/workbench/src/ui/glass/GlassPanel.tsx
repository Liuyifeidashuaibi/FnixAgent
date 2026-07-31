import type { ReactNode } from "react";

interface Props {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
  footer?: ReactNode;
  footerClassName?: string;
  width?: number | string;
}

export function GlassPanel({
  title,
  actions,
  children,
  className,
  headerClassName,
  bodyClassName,
  footer,
  footerClassName,
  width,
}: Props) {
  return (
    <aside
      className={["glass-panel", className].filter(Boolean).join(" ")}
      style={width != null ? { width } : undefined}
    >
      {title != null || actions != null ? (
        <div className={["glass-panel-h", headerClassName].filter(Boolean).join(" ")}>
          <div>{title}</div>
          {actions ? <div className="row">{actions}</div> : null}
        </div>
      ) : null}
      <div className={["glass-panel-body", bodyClassName].filter(Boolean).join(" ")}>
        {children}
      </div>
      {footer ? (
        <div className={["glass-panel-footer", footerClassName].filter(Boolean).join(" ")}>
          {footer}
        </div>
      ) : null}
    </aside>
  );
}
