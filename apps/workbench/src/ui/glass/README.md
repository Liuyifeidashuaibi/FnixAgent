# Fnix Glass Kit

ChatGPT / Codex **light frost** components for Workbench.

## Use

```tsx
import {
  GlassComposer,
  GlassCapsule,
  GlassGoalRow,
  GlassProcessList,
  GlassSegment,
  GlassSurface,
  GlassPanel,
  GlassIconButton,
} from "../../ui/glass";

<div className="fnix-glass">
  <GlassComposer ... />
</div>
```

Root must have class `fnix-glass`. Styles live in `tokens.css` (imported by `index.ts`).

## Preview

```
http://127.0.0.1:5175/?glass=1
```

## Scope

Only project-needed surfaces: Surface, IconButton, Segment, Panel, Composer, Capsule, GoalRow, ProcessList. Not a full design system.
