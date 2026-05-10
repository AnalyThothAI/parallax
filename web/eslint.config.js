// web/eslint.config.js
// Flat config — ESLint 9+
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import importPlugin from "eslint-plugin-import";
import jsxA11y from "eslint-plugin-jsx-a11y";
import globals from "globals";

export default [
  {
    ignores: ["dist/**", "node_modules/**", "src/api/types.ts"],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react: reactPlugin,
      "react-hooks": reactHooks,
      import: importPlugin,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      // Base
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-unused-vars": "off",
      // TypeScript
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/consistent-type-imports": "error",
      // React
      "react/jsx-uses-react": "off",
      "react/react-in-jsx-scope": "off",
      "react/jsx-key": "error",
      // React hooks
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Import
      "import/no-duplicates": "error",
      "import/order": [
        "warn",
        {
          groups: ["builtin", "external", "internal", "parent", "sibling", "index"],
          "newlines-between": "always",
          alphabetize: { order: "asc" },
        },
      ],
      // a11y
      "jsx-a11y/alt-text": "warn",
    },
    settings: {
      react: { version: "detect" },
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}", "src/test/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/consistent-type-imports": "off", // vi.importActual type parameter is not a type import
      "no-console": "off",
    },
  },
];
