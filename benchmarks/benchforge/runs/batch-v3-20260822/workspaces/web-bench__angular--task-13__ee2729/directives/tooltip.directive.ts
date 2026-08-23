import {
  Directive,
  ElementRef,
  HostListener,
  Input,
  ApplicationRef,
  ComponentRef,
  EmbeddedViewRef,
  Injector,
  inject,
  Component,
  OnDestroy,
  createComponent,
} from '@angular/core';

@Component({
  selector: 'app-tooltip',
  template: `<div class="tooltip">{{ text }}</div>`,
  styles: [
    `
      .tooltip {
        position: absolute;
        background-color: #333;
        color: #fff;
        padding: 6px 12px;
        border-radius: 4px;
        font-size: 13px;
        white-space: nowrap;
        pointer-events: none;
        z-index: 9999;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
        transition: opacity 0.2s ease;
      }
    `,
  ],
})
export class TooltipComponent {
  text: string = '';
}

@Directive({
  selector: '[appTooltip]',
})
export class TooltipDirective implements OnDestroy {
  @Input('appTooltip') tooltipText: string = '';

  private el = inject(ElementRef);
  private appRef = inject(ApplicationRef);
  private injector = inject(Injector);

  private componentRef: ComponentRef<TooltipComponent> | null = null;

  @HostListener('mouseenter')
  onMouseEnter(): void {
    this.showTooltip();
  }

  @HostListener('mouseleave')
  onMouseLeave(): void {
    this.hideTooltip();
  }

  private showTooltip(): void {
    if (this.componentRef) {
      return;
    }

    // Dynamically create the tooltip component and attach to document.body
    this.componentRef = createComponent(TooltipComponent, {
      environmentInjector: this.injector,
    });

    this.componentRef.instance.text = this.tooltipText;

    // Attach the component's view to the application
    this.appRef.attachView(this.componentRef.hostView);

    // Append the root DOM element to document.body
    const domElem = (this.componentRef.hostView as EmbeddedViewRef<unknown>)
      .rootNodes[0] as HTMLElement;
    document.body.appendChild(domElem);

    this.positionTooltip();
  }

  private positionTooltip(): void {
    if (!this.componentRef) return;

    const rect = this.el.nativeElement.getBoundingClientRect();
    const domElem = (this.componentRef.hostView as EmbeddedViewRef<unknown>)
      .rootNodes[0] as HTMLElement;

    domElem.style.left = `${rect.left + rect.width / 2}px`;
    domElem.style.top = `${rect.bottom + 8}px`;
    domElem.style.transform = 'translateX(-50%)';
  }

  private hideTooltip(): void {
    this.destroyTooltip();
  }

  private destroyTooltip(): void {
    if (this.componentRef) {
      this.appRef.detachView(this.componentRef.hostView);
      this.componentRef.destroy();
      this.componentRef = null;
    }
  }

  ngOnDestroy(): void {
    this.destroyTooltip();
  }
}
