import { useEffect, useRef, useState } from 'react';

/**
 * Hook to persist and restore container scroll position
 * Uses key format: persisted::<tabUid>::container-scroll-<entityUid>
 */
export const usePersistedContainerScroll = (tabUid: string, entityUid: string) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isRestored, setIsRestored] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const key = `persisted::${tabUid}::container-scroll-${entityUid}`;
    
    try {
      const savedPosition = localStorage.getItem(key);
      if (savedPosition) {
        const position = JSON.parse(savedPosition);
        // Use requestAnimationFrame to ensure DOM is ready
        requestAnimationFrame(() => {
          if (containerRef.current) {
            containerRef.current.scrollTop = position.scrollTop || 0;
            containerRef.current.scrollLeft = position.scrollLeft || 0;
          }
        });
      }
    } catch (e) {
      console.warn(`Failed to restore scroll position for ${key}:`, e);
    }
    
    setIsRestored(true);
  }, [tabUid, entityUid]);

  useEffect(() => {
    if (!containerRef.current || !isRestored) return;

    const saveScrollPosition = () => {
      const key = `persisted::${tabUid}::container-scroll-${entityUid}`;
      const position = {
        scrollTop: containerRef.current?.scrollTop || 0,
        scrollLeft: containerRef.current?.scrollLeft || 0
      };
      
      try {
        localStorage.setItem(key, JSON.stringify(position));
      } catch (e) {
        console.warn(`Failed to save scroll position for ${key}:`, e);
      }
    };

    const container = containerRef.current;
    container.addEventListener('scroll', saveScrollPosition);
    
    return () => {
      container.removeEventListener('scroll', saveScrollPosition);
      // Also save on unmount
      saveScrollPosition();
    };
  }, [tabUid, entityUid, isRestored]);

  return {
    containerRef,
    isRestored
  };
};