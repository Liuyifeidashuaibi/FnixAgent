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
  Injectable,
  ComponentRef,
  createComponent,
  ApplicationRef,
  EnvironmentInjector,
  Component,
} from '@angular/core'

@Component({
  selector: 'app-toast',
  standalone: true,
  template: `
    <div class="toast" [class.big]="isBig">
      {{ message }}
    </div>
  `,
  styles: [
    `
      .toast {
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: #4caf50;
        color: white;
        padding: 12px 24px;
        border-radius: 4px;
        font-size: 12px;
        z-index: 10000;
        animation: fadeInOut 2s ease-in-out;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
      }

      .toast.big {
        font-size: 50px;
      }

      @keyframes fadeInOut {
        0% {
          opacity: 0;
          transform: translate(-50%, -20px);
        }
        15% {
          opacity: 1;
          transform: translate(-50%, 0);
        }
        85% {
          opacity: 1;
          transform: translate(-50%, 0);
        }
        100% {
          opacity: 0;
          transform: translate(-50%, -20px);
        }
      }
    `,
  ],
})
class ToastComponent {
  message = ''
  isBig = false
}

@Injectable({
  providedIn: 'root',
})
export class ToastService {
  private toastRef: ComponentRef<ToastComponent> | null = null
  private hideTimeout: any

  constructor(
    private appRef: ApplicationRef,
    private environmentInjector: EnvironmentInjector
  ) {}

  show(message: string, isBig = false) {
    this.hide()

    const toastContainer = document.createElement('div')
    document.body.appendChild(toastContainer)

    this.toastRef = createComponent(ToastComponent, {
      environmentInjector: this.environmentInjector,
      hostElement: toastContainer,
    })

    this.toastRef.instance.message = message
    this.toastRef.instance.isBig = isBig
    this.toastRef.changeDetectorRef.detectChanges()

    this.appRef.attachView(this.toastRef.hostView)

    this.hideTimeout = setTimeout(() => {
      this.hide()
    }, 2000)
  }

  private hide() {
    if (this.hideTimeout) {
      clearTimeout(this.hideTimeout)
    }

    if (this.toastRef) {
      this.appRef.detachView(this.toastRef.hostView)
      this.toastRef.destroy()
      this.toastRef.location.nativeElement.parentElement?.remove()
      this.toastRef = null
    }
  }
}