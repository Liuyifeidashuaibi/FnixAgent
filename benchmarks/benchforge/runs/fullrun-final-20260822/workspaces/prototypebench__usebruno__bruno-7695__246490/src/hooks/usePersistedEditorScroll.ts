import { useEffect, useRef, useState } from 'react';

/**
 * Hook to persist and restore editor scroll position
 * Uses key format: persisted::<tabUid>::editor-scroll-<entityUid>
 */
export const usePersistedEditorScroll = (tabUid: string, entityUid: string) => {
  const editorRef = useRef<HTMLDivElement | null>(null);
  const [isRestored, setIsRestored] = useState(false);

  useEffect(() => {
    if (!editorRef.current) return;

    const key = `persisted::${tabUid}::editor-scroll-${entityUid}`;
    
    try {
      const savedPosition = localStorage.getItem(key);
      if (savedPosition) {
        const position = JSON.parse(savedPosition);
        // Use requestAnimationFrame to ensure DOM is ready
        requestAnimationFrame(() => {
          if (editorRef.current) {
            editorRef.current.scrollTop = position.scrollTop || 0;
            editorRef.current.scrollLeft = position.scrollLeft || 0;
          }
        });
      }
    } catch (e) {
      console.warn(`Failed to restore scroll position for ${key}:`, e);
    }
    
    setIsRestored(true);
  }, [tabUid, entityUid]);

  useEffect(() => {
    if (!editorRef.current || !isRestored) return;

    const saveScrollPosition = () => {
      const key = `persisted::${tabUid}::editor-scroll-${entityUid}`;
      const position = {
        scrollTop: editorRef.current?.scrollTop || 0,
        scrollLeft: editorRef.current?.scrollLeft || 0
      };
      
      try {
        localStorage.setItem(key, JSON.stringify(position));
      } catch (e) {
        console.warn(`Failed to save scroll position for ${key}:`, e);
      }
    };

    const editor = editorRef.current;
    editor.addEventListener('scroll', saveScrollPosition);
    
    return () => {
      editor.removeEventListener('scroll', saveScrollPosition);
      // Also save on unmount
      saveScrollPosition();
    };
  }, [tabUid, entityUid, isRestored]);

  return {
    editorRef,
    isRestored
  };
};