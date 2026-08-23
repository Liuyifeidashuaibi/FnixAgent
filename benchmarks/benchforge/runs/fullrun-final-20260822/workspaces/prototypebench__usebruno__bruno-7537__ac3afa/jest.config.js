module.exports = {
  testEnvironment: 'node',
  roots: ['<rootDir>/src/utils/__tests__'],
  testMatch: ['**/*.test.js'],
  moduleFileExtensions: ['js', 'json', 'jsx', 'ts', 'tsx', 'node'],
  collectCoverageFrom: [
    'src/utils/**/*.js',
    '!src/utils/__tests__/**',
  ],
  coverageDirectory: 'coverage',
  coverageReporters: ['text', 'lcov'],
};