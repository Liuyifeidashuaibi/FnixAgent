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
  ElementRef,
  OnInit,
  Input,
  OnDestroy,
  ComponentRef,
  Injector,
  createComponent,
  EnvironmentInjector,
  ApplicationRef,
  HostListener,
  OnChanges,
  SimpleChanges,
} from '@angular/core'
import { Component } from '@angular/core'
import { TooltipComponent } from './tooltip.directive'

@Directive({
  selector: '[truncate]',
  standalone: true,
  host: {
    style: 'white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px',
  },
})
export class TruncateDirective implements OnInit, OnDestroy, OnChanges {
  @Input('truncate') text = ''

  private tooltipRef: ComponentRef<TooltipComponent> | null = null
  private el: HTMLElement

  constructor(
    private elementRef: ElementRef,
    private injector: Injector,
    private environmentInjector: EnvironmentInjector,
    private appRef: ApplicationRef
  ) {
    this.el = elementRef.nativeElement
  }

  ngOnInit() {
    this.el.innerHTML = this.text
  }

  ngOnChanges(changes: SimpleChanges) {
    if (changes['text'] && !changes['text'].firstChange) {
      this.el.innerHTML = this.text
    }
  }

  @HostListener('mouseenter')
  onMouseEnter() {
    if (this.el.offsetWidth < this.el.scrollWidth && !this.tooltipRef) {
      const tooltipContainer = document.createElement('div')
      document.body.appendChild(tooltipContainer)

      const tooltipRef = createComponent(TooltipComponent, {
        environmentInjector: this.environmentInjector,
        hostElement: tooltipContainer,
      })

      this.appRef.attachView(tooltipRef.hostView)

      const rect = this.el.getBoundingClientRect()

      tooltipRef.instance.text = this.text
      tooltipRef.instance.left = rect.left
      tooltipRef.instance.top = rect.bottom + 8

      tooltipRef.changeDetectorRef.detectChanges()

      this.tooltipRef = tooltipRef
    }
  }

  @HostListener('mouseleave')
  onMouseLeave() {
    if (this.tooltipRef) {
      this.appRef.detachView(this.tooltipRef.hostView)
      this.tooltipRef.destroy()
      this.tooltipRef.location.nativeElement.parentElement?.remove()
      this.tooltipRef = null
    }
  }

  ngOnDestroy() {
    if (this.tooltipRef) {
      this.appRef.detachView(this.tooltipRef.hostView)
      this.tooltipRef.destroy()
      this.tooltipRef.location.nativeElement.parentElement?.remove()
    }
  }
}
