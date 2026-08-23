import responseReducer from './responseReducer';
import {
  clearResponse,
  setResponse,
  setAssertionResults,
  setPreRequestTestResults,
  setPostRequestTestResults
} from '../actions/responseActions';

// Initial state
const initialState = {
  response: null,
  assertionResults: [],
  preRequestTestResults: [],
  postRequestTestResults: []
};

describe('responseReducer', () => {
  test('should return initial state', () => {
    expect(responseReducer(undefined, {})).toEqual(initialState);
  });

  test('CLEAR_RESPONSE should clear response and all test results', () => {
    const previousState = {
      response: { status: 200, data: 'test' },
      assertionResults: [{ passed: true, message: 'Status check' }],
      preRequestTestResults: [{ passed: true, message: 'Pre-request setup' }],
      postRequestTestResults: [{ passed: false, message: 'Data validation' }]
    };

    const newState = responseReducer(previousState, clearResponse());
    
    expect(newState.response).toBeNull();
    expect(newState.assertionResults).toEqual([]);
    expect(newState.preRequestTestResults).toEqual([]);
    expect(newState.postRequestTestResults).toEqual([]);
  });

  test('SET_RESPONSE should set response', () => {
    const previousState = initialState;
    const response = { status: 200, data: 'test' };
    
    const newState = responseReducer(previousState, setResponse(response));
    
    expect(newState.response).toEqual(response);
  });

  test('SET_ASSERTION_RESULTS should set assertion results', () => {
    const previousState = initialState;
    const results = [{ passed: true, message: 'Status check' }];
    
    const newState = responseReducer(previousState, setAssertionResults(results));
    
    expect(newState.assertionResults).toEqual(results);
  });

  test('SET_PRE_REQUEST_TEST_RESULTS should set pre-request test results', () => {
    const previousState = initialState;
    const results = [{ passed: true, message: 'Pre-request setup' }];
    
    const newState = responseReducer(previousState, setPreRequestTestResults(results));
    
    expect(newState.preRequestTestResults).toEqual(results);
  });

  test('SET_POST_REQUEST_TEST_RESULTS should set post-request test results', () => {
    const previousState = initialState;
    const results = [{ passed: false, message: 'Data validation' }];
    
    const newState = responseReducer(previousState, setPostRequestTestResults(results));
    
    expect(newState.postRequestTestResults).toEqual(results);
  });
});
