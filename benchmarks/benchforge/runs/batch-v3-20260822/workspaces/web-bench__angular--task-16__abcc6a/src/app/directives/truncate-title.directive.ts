import {
  Directive,
  ElementRef,
  HostBinding,
  HostListener,
  Input,
  OnDestroy,
  Renderer2,
} from '@angular/core';

@Directive({
  selector: '[appTruncateTitle]',
  standalone: true,
})
export class TruncateTitleDirective implements OnDestroy {
  /** Full title text to display when truncated */
  @Input('appTruncateTitle') titleText: string = '';

  /** Maximum width in pixels before truncation (default 300) */
  @Input() maxWidth: number = 300;

  @HostBinding('style.max-width') get maxWidthStyle(): string {
    return `${this.maxWidth}px`;
  }

  @HostBinding('style.overflow') get overflowStyle(): string {
    return 'hidden';
  }

  @HostBinding('style.text-overflow') get textOverflowStyle(): string {
    return 'ellipsis';
  }

  @HostBinding('style.white-space') get whiteSpaceStyle(): string {
    return 'nowrap';
  }

  @HostBinding('style.display') get displayStyle(): string {
    return 'inline-block';
  }

  private tooltipEl: HTMLElement | null = null;
  private tooltipVisible: boolean = false;

  constructor(
    private el: ElementRef<HTMLElement>,
    private renderer: Renderer2
  ) {}

  @HostListener('mouseenter')
  onMouseEnter(): void {
    if (this.isTruncated()) {
      this.showTooltip();
    }
  }

  @HostListener('mouseleave')
  onMouseLeave(): void {
    this.hideTooltip();
  }

  /** Check if the element's content is actually overflowing */
  private isTruncated(): boolean {
    const element = this.el.nativeElement;
    return element.scrollWidth > element.clientWidth;
  }

  private showTooltip(): void {
    if (this.tooltipVisible) return;

    const tooltip = this.renderer.createElement('div');
    this.renderer.addClass(tooltip, 'truncate-tooltip');
    this.renderer.setStyle(tooltip, 'position', 'fixed');
    this.renderer.setStyle(tooltip, 'z-index', '9999');
    this.renderer.setStyle(tooltip, 'padding', '6px 10px');
    this.renderer.setStyle(tooltip, 'background', '#333');
    this.renderer.setStyle(tooltip, 'color', '#fff');
    this.renderer.setStyle(tooltip, 'border-radius', '4px');
    this.renderer.setStyle(tooltip, 'font-size', '13px');
    this.renderer.setStyle(tooltip, 'line-height', '1.4');
    this.renderer.setStyle(tooltip, 'max-width', '350px');
    this.renderer.setStyle(tooltip, 'word-break', 'break-word');
    this.renderer.setStyle(tooltip, 'pointer-events', 'none');
    this.renderer.setStyle(tooltip, 'box-shadow', '0 2px 8px rgba(0,0,0,0.2)');
    this.renderer.setProperty(tooltip, 'textContent', this.titleText);

    this.renderer.appendChild(document.body, tooltip);
    this.tooltipEl = tooltip;
    this.tooltipVisible = true;

    // Position tooltip below the element
    requestAnimationFrame(() => {
      if (!this.tooltipEl) return;
      const rect = this.el.nativeElement.getBoundingClientRect();
      const tooltipRect = this.tooltipEl.getBoundingClientRect();

      let left = rect.left;
      let top = rect.bottom + 6;

      // Prevent overflow on right edge
      if (left + tooltipRect.width > window.innerWidth) {
        left = window.innerWidth - tooltipRect.width - 8;
      }
      // Prevent overflow on left edge
      if (left < 8) {
        left = 8;
      }
      // If tooltip goes below viewport, show above
      if (top + tooltipRect.height > window.innerHeight) {
        top = rect.top - tooltipRect.height - 6;
      }

      this.renderer.setStyle(this.tooltipEl, 'left', `${left}px`);
      this.renderer.setStyle(this.tooltipEl, 'top', `${top}px`);
    });
  }

  private hideTooltip(): void {
    if (this.tooltipEl) {
      this.renderer.removeChild(document.body, this.tooltipEl);
      this.tooltipEl = null;
      this.tooltipVisible = false;
    }
  }

  ngOnDestroy(): void {
    this.hideTooltip();
  }
}
