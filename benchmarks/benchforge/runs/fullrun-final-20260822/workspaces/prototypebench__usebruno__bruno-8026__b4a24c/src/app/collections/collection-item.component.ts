import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CollectionService } from './collection.service';

@Component({
  selector: 'brn-collection-item',
  template: `
    <div class="collection-item">
      <span>{{ collection.name }}</span>
      <button (click)="onClose()" class="close-btn">×</button>
    </div>
  `
})
export class CollectionItemComponent {
  @Input() collection: { id: string; name: string };
  @Output() closed = new EventEmitter<string>();

  constructor(private collectionService: CollectionService) {}

  onClose(): void {
    // Close the collection and let the tab manager handle the tab activation priority
    this.collectionService.closeCollection(this.collection.id);
    this.closed.emit(this.collection.id);
  }
}
