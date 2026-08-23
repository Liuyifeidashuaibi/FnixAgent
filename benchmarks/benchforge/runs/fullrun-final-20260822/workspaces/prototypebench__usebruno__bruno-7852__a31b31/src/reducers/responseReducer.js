import { createReducer } from '@reduxjs/toolkit';
import {
  CLEAR_RESPONSE,
  SET_RESPONSE,
  SET_ASSERTION_RESULTS,
  SET_PRE_REQUEST_TEST_RESULTS,
  SET_POST_REQUEST_TEST_RESULTS
} from '../constants/responseConstants';

const initialState = {
  response: null,
  assertionResults: [],
  preRequestTestResults: [],
  postRequestTestResults: []
};

const responseReducer = createReducer(initialState, {
  // Action to clear response and associated test results
  [CLEAR_RESPONSE]: (state, action) => {
    return {
      ...state,
      response: null,
      assertionResults: [],
      preRequestTestResults: [],
      postRequestTestResults: []
    };
  },
  
  // Action to set response
  [SET_RESPONSE]: (state, action) => {
    return {
      ...state,
      response: action.payload
    };
  },
  
  // Action to set assertion results
  [SET_ASSERTION_RESULTS]: (state, action) => {
    return {
      ...state,
      assertionResults: action.payload
    };
  },
  
  // Action to set pre-request test results
  [SET_PRE_REQUEST_TEST_RESULTS]: (state, action) => {
    return {
      ...state,
      preRequestTestResults: action.payload
    };
  },
  
  // Action to set post-request test results
  [SET_POST_REQUEST_TEST_RESULTS]: (state, action) => {
    return {
      ...state,
      postRequestTestResults: action.payload
    };
  }
});

export default responseReducer;
