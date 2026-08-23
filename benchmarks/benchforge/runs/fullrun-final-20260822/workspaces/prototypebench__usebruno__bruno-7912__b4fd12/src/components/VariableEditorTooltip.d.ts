import React from 'react';

interface VariableEditorTooltipProps {
  /** The current resolved value of the variable */
  value: string;
  
  /** The initial value of the variable (for reference) */
  initialValue?: string;
  
  /** Callback when copy button is clicked */
  onCopy: (value: string) => void;
  
  /** Callback when pin state changes */
  onPinToggle: (isPinned: boolean) => void;
}

declare const VariableEditorTooltip: React.FC<VariableEditorTooltipProps>;

export default VariableEditorTooltip;