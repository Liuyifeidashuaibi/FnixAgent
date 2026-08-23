/*
 * CodeSnippet.js
 * Reusable code display component with line numbers and error highlighting
 */

import React from 'react';
import PropTypes from 'prop-types';

/**
 * CodeSnippet component displays code with line numbers and optional error highlighting
 * @component
 * @param {Object} props - Component props
 * @param {Array<string>} props.lines - Array of code lines to display
 * @param {number} props.highlightedLine - Line number to highlight (1-based)
 * @param {string} [props.className] - Additional CSS classes
 * @param {boolean} [props.showLineNumbers=true] - Whether to show line numbers
 * @param {number} [props.startLine=1] - Starting line number for numbering
 * @returns {JSX.Element} Code snippet component
 */
const CodeSnippet = ({ 
  lines, 
  highlightedLine, 
  className = '', 
  showLineNumbers = true, 
  startLine = 1 
}) => {
  if (!lines || lines.length === 0) {
    return (
      <div className={`code-snippet ${className}`}>
        <pre className="code-content">No code to display</pre>
      </div>
    );
  }

  const getLineNumberClass = (lineNumber) => {
    if (lineNumber === highlightedLine) {
      return 'line-number highlighted';
    }
    return 'line-number';
  };

  const getLineClass = (lineNumber) => {
    if (lineNumber === highlightedLine) {
      return 'code-line highlighted';
    }
    return 'code-line';
  };

  return (
    <div className={`code-snippet ${className}`}>
      <div className="code-container">
        {showLineNumbers && (
          <div className="line-numbers">
            {lines.map((_, index) => {
              const lineNumber = startLine + index;
              return (
                <div 
                  key={lineNumber} 
                  className={getLineNumberClass(lineNumber)}
                >
                  {lineNumber}
                </div>
              );
            })}
          </div>
        )}
        <div className="code-content">
          {lines.map((line, index) => {
            const lineNumber = startLine + index;
            return (
              <div 
                key={index} 
                className={getLineClass(lineNumber)}
                data-line-number={lineNumber}
              >
                {line}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

CodeSnippet.propTypes = {
  lines: PropTypes.arrayOf(PropTypes.string).isRequired,
  highlightedLine: PropTypes.number.isRequired,
  className: PropTypes.string,
  showLineNumbers: PropTypes.bool,
  startLine: PropTypes.number
};

CodeSnippet.defaultProps = {
  className: '',
  showLineNumbers: true,
  startLine: 1
};

export default CodeSnippet;