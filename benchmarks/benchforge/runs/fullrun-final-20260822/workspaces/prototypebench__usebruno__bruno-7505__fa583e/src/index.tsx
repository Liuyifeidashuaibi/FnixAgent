import React from 'react';
import ReactDOM from 'react-dom/client';
import RunnerTab from './components/RunnerTab';
import RunCollectionModal from './components/RunCollectionModal';

// Simple demo app that shows both components
const App = () => {
  const [isModalOpen, setIsModalOpen] = React.useState(false);

  return (
    <div className="min-h-screen bg-surface">
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8 text-text-primary">Bruno Collection Runner</h1>
        
        {/* Runner Tab */}
        <div className="mb-12">
          <RunnerTab />
        </div>
        
        {/* Modal Trigger */}
        <div className="text-center">
          <button 
            onClick={() => setIsModalOpen(true)}
            className="px-6 py-3 bg-brand text-white rounded-lg font-medium hover:bg-brand-dark transition-colors"
          >
            Open Run Collection Modal
          </button>
        </div>
      </div>
      
      {/* Run Collection Modal */}
      <RunCollectionModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
      />
    </div>
  );
};

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

export default App;