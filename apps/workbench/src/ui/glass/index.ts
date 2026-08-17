/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Fnix Glass Kit — ChatGPT / Codex light frost components.
 * Import: `import { GlassComposer, ... } from "../../ui/glass"`
 * Root must include class `fnix-glass` and import `./tokens.css`.
 */

import "./tokens.css";

export { GlassIconButton } from "./GlassIconButton";

export { GlassSegment } from "./GlassSegment";
export type { GlassSegmentOption } from "./GlassSegment";

export { GlassPanel } from "./GlassPanel";

export { GlassComposer } from "./GlassComposer";
export type { GlassComposerProps } from "./GlassComposer";

export { GlassCapsule } from "./GlassCapsule";
export type { GlassCapsuleKind, GlassCapsuleProps } from "./GlassCapsule";

export { GlassGoalRow } from "./GlassGoalRow";
export type { GlassGoalRowProps } from "./GlassGoalRow";

export { GlassProcessList } from "./GlassProcessList";
export type { GlassProcessListProps } from "./GlassProcessList";

export type {
  GlassActivityItem,
  GlassActivityKind,
  GlassActivityStatus,
} from "./types";
