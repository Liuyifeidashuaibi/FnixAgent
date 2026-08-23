import {
  CLEAR_RESPONSE,
  SET_RESPONSE,
  SET_ASSERTION_RESULTS,
  SET_PRE_REQUEST_TEST_RESULTS,
  SET_POST_REQUEST_TEST_RESULTS
} from '../constants/responseConstants';

export const clearResponse = () => ({
  type: CLEAR_RESPONSE
});

export const setResponse = (response) => ({
  type: SET_RESPONSE,
  payload: response
});

export const setAssertionResults = (results) => ({
  type: SET_ASSERTION_RESULTS,
  payload: results
});

export const setPreRequestTestResults = (results) => ({
  type: SET_PRE_REQUEST_TEST_RESULTS,
  payload: results
});

export const setPostRequestTestResults = (results) => ({
  type: SET_POST_REQUEST_TEST_RESULTS,
  payload: results
});
