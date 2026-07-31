export interface GlassSegmentOption<T extends string = string> {
  id: T;
  label: string;
}

interface Props<T extends string> {
  value: T;
  options: GlassSegmentOption<T>[];
  onChange: (v: T) => void;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
}

export function GlassSegment<T extends string>({
  value,
  options,
  onChange,
  disabled,
  ariaLabel,
  className,
}: Props<T>) {
  const selectRelative = (current: T, delta: number): number | null => {
    const currentIndex = options.findIndex((opt) => opt.id === current);
    if (currentIndex < 0 || options.length === 0) return null;
    const nextIndex = (currentIndex + delta + options.length) % options.length;
    onChange(options[nextIndex].id);
    return nextIndex;
  };

  return (
    <div
      className={["glass-seg", className].filter(Boolean).join(" ")}
      role="tablist"
      aria-label={ariaLabel}
    >
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          role="tab"
          aria-selected={value === opt.id}
          tabIndex={value === opt.id ? 0 : -1}
          className={value === opt.id ? "on" : undefined}
          disabled={disabled}
          onClick={() => onChange(opt.id)}
          onKeyDown={(event) => {
            let nextIndex: number | null = null;
            if (event.key === "ArrowRight" || event.key === "ArrowDown") {
              event.preventDefault();
              nextIndex = selectRelative(opt.id, 1);
            } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
              event.preventDefault();
              nextIndex = selectRelative(opt.id, -1);
            }
            if (nextIndex != null) {
              const tabs = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                '[role="tab"]',
              );
              tabs?.[nextIndex]?.focus();
            }
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
