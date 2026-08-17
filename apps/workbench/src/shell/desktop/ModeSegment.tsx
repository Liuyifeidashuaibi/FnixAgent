/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Work | Code 左右分段 — 侧栏顶栏唯一产品开关（非下拉菜单）。
 */

import { GlassSegment } from "../../ui/glass";
import type { ShellMode } from "./useChatFlow";

interface Props {
  value: ShellMode;
  onChange: (v: ShellMode) => void;
  disabled?: boolean;
}

export function ProductSegment({ value, onChange, disabled }: Props) {
  return (
    <GlassSegment
      className="fnix-product-seg"
      value={value}
      onChange={onChange}
      disabled={disabled}
      ariaLabel="Work 或 Code 模式切换"
      options={[
        { id: "work", label: "Work" },
        { id: "code", label: "Code" },
      ]}
    />
  );
}
