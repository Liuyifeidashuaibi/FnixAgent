// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// 
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// 
//     http://www.apache.org/licenses/LICENSE-2.0
// 
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {
  Directive,
  Input,
  ElementRef,
  OnDestroy,
  ComponentRef,
  Injector,
  createComponent,
  HostListener,
  EnvironmentInjector,
  ApplicationRef,
} from '@angular/core'
import { Component } from '@angular/core'

@Component({
  selector: 'app-tooltip',
  standalone: true,
  template: `
    <div class="tooltip" [style.left.px]="left" [style.top.px]="top">
      {{ text }}
    </div>
  `,
  styles: [
    `
      .tooltip {
        position: fixed;
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 8px;
        border-radius: 4px;
        font-size: 14px;
        z-index: 10000;
        width: max-content;
      }
    `,
  ],
})
export class TooltipComponent {
  text = ''
  left = 0
  top = 0
}

@Directive({
  selector: '[tooltip]',
  standalone: true,
})
export class TooltipDirective implements OnDestroy {
  @Input('tooltip') text = ''

  private tooltipRef: ComponentRef<TooltipComponent> | null = null

  constructor(
    private el: ElementRef,
    private injector: Injector,
    private environmentInjector: EnvironmentInjector,
    private appRef: ApplicationRef
  ) {}

  @HostListener('mouseenter')
  onMouseEnter() {
    if (this.tooltipRef) return

    // Create a new div as a container for the tooltip
    const tooltipContainer = document.createElement('div')
    document.body.appendChild(tooltipContainer)

    const tooltipRef = createComponent(TooltipComponent, {
      environmentInjector: this.environmentInjector,
      hostElement: tooltipContainer,
    })

    // Attach the component to ApplicationRef to ensure change detection works properly
    this.appRef.attachView(tooltipRef.hostView)

    const element = this.el.nativeElement
    const rect = element.getBoundingClientRect()

    tooltipRef.instance.text = this.text
    tooltipRef.instance.left = rect.left + (rect.width - 200) / 2
    tooltipRef.instance.top = rect.bottom + 8

    tooltipRef.changeDetectorRef.detectChanges()

    this.tooltipRef = tooltipRef
  }

  @HostListener('mouseleave')
  onMouseLeave() {
    if (!this.tooltipRef) return
    // Remove the view and clean up DOM
    this.appRef.detachView(this.tooltipRef.hostView)
    this.tooltipRef.destroy()
    // Remove the container element
    this.tooltipRef.location.nativeElement.parentElement?.remove()
    this.tooltipRef = null
  }

  ngOnDestroy() {
    if (this.tooltipRef) {
      this.appRef.detachView(this.tooltipRef.hostView)
      this.tooltipRef.destroy()
      this.tooltipRef.location.nativeElement.parentElement?.remove()
    }
  }
}
