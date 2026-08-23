/**
 * Fix for Bruno preferences persistence issue
 * Ensures pending preference changes are saved when the Preferences panel is closed
 */

// This fix should be applied to the PreferencesPanel component
// It adds logic to save pending changes in the cleanup effect

// Example implementation for a React functional component:
/*
import { useEffect } from 'react';

const PreferencesPanel = () => {
  const [pendingChanges, setPendingChanges] = useState({});

  // Key fix: Save pending changes when component unmounts
  useEffect(() => {
    return () => {
      // This cleanup function runs when the component is unmounted
      // (e.g., when the Preferences panel is closed)
      if (Object.keys(pendingChanges).length > 0) {
        console.log('Saving pending preferences before panel close');
        savePreferences(pendingChanges);
      }
    };
  }, [pendingChanges]);

  const savePreferences = (changes) => {
    // Actual save logic would go here
    // This ensures changes are persisted even if user closes panel without clicking Save
  };

  // ... rest of component
};
*/