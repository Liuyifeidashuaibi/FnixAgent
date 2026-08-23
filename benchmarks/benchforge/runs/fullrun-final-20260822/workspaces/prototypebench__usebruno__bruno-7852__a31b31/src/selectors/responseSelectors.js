import { createSelector } from '@reduxjs/toolkit';

// Selector to get the entire response state
export const selectResponseState = (state) => state.response;

// Selector to get just the response
export const selectResponse = createSelector(
  selectResponseState,
  (responseState) => responseState.response
);

// Selector to get assertion results
export const selectAssertionResults = createSelector(
  selectResponseState,
  (responseState) => responseState.assertionResults
);

// Selector to get pre-request test results
export const selectPreRequestTestResults = createSelector(
  selectResponseState,
  (responseState) => responseState.preRequestTestResults
);

// Selector to get post-request test results
export const selectPostRequestTestResults = createSelector(
  selectResponseState,
  (responseState) => responseState.postRequestTestResults
);

// Selector to get all test results together
export const selectAllTestResults = createSelector(
  selectAssertionResults,
  selectPreRequestTestResults,
  selectPostRequestTestResults,
  (assertionResults, preRequestTestResults, postRequestTestResults) => ({
    assertionResults,
    preRequestTestResults,
    postRequestTestResults
  })
);
