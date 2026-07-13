/**
 * OfficeAgent 前端 ESLint 根配置
 * TypeScript strict + React Hooks + React Refresh
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  plugins: ["@typescript-eslint", "react-refresh"],
  rules: {
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/no-explicit-any": "warn",
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    "no-empty": ["error", { allowEmptyCatch: true }],
  },
  ignorePatterns: ["dist", "build", "node_modules", "*.config.ts", "*.config.js"],
};
