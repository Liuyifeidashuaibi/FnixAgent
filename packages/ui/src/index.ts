/**
 * @fnixagent/ui — 共享组件库
 * shadcn/ui 风格,基于 Radix UI + Tailwind CSS
 */
export { Button, buttonVariants, type ButtonProps } from './button';
export { Input } from './input';
export { Card, CardHeader, CardTitle, CardContent } from './card';
export { cn } from './utils';

// 新增 shadcn/ui 风格组件(纯 React + Tailwind 实现,无新增 Radix 依赖)
export { Tabs, TabsList, TabsTrigger, TabsContent } from './tabs';
export type { TabsProps, TabsTriggerProps, TabsContentProps } from './tabs';
export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from './dialog';
export type {
  DialogProps,
  DialogTriggerProps,
  DialogContentProps,
} from './dialog';
export { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from './tooltip';
export type { TooltipProps } from './tooltip';
export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from './dropdown';
export type { DropdownMenuProps, DropdownMenuTriggerProps, DropdownMenuItemProps } from './dropdown';
export { Badge, badgeVariants, type BadgeProps } from './badge';
export { ScrollArea } from './scroll-area';
export type { ScrollAreaProps } from './scroll-area';
export { Progress } from './progress';
export type { ProgressProps } from './progress';
export { Spinner } from './spinner';
export type { SpinnerProps } from './spinner';
