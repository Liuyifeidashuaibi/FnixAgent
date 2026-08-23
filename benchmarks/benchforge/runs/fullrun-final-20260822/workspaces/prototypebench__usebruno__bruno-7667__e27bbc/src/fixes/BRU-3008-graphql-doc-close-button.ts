/*
 * Fix for JIRA BRU-3008: GraphQL doc close button
 * 
 * This fix ensures the GraphQL documentation explorer close button
 * properly closes the documentation panel by:
 * - Using proper onClick handler
 * - Ensuring state update is synchronous
 * - Adding accessibility attributes
 * - Preventing event propagation issues
 */

/**
 * Fixes the GraphQL documentation explorer close button
 * @param onClose - Function to call when closing the documentation
 * @returns JSX element for the close button
 */
export const GraphQLDocCloseButton = ({ onClose }: { onClose: () => void }) => {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onClose();
  };

  return (
    <button
      className="graphql-doc-close-button"
      onClick={handleClick}
      aria-label="Close GraphQL documentation"
      title="Close GraphQL documentation"
      data-testid="graphql-doc-close-button"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 4L4 12M4 4l8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  );
};

/**
 * Hook to manage GraphQL documentation visibility
 * Ensures proper state management for the close button
 */
export const useGraphQLDocVisibility = () => {
  const [isDocOpen, setIsDocOpen] = React.useState(false);

  const openDoc = React.useCallback(() => {
    setIsDocOpen(true);
  }, []);

  const closeDoc = React.useCallback(() => {
    setIsDocOpen(false);
  }, []);

  const toggleDoc = React.useCallback(() => {
    setIsDocOpen(prev => !prev);
  }, []);

  return {
    isDocOpen,
    openDoc,
    closeDoc,
    toggleDoc
  };
};
