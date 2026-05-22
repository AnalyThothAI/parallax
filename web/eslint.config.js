// web/eslint.config.js
// Flat config — ESLint 9+
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import importPlugin from "eslint-plugin-import";
import jsxA11y from "eslint-plugin-jsx-a11y";
import globals from "globals";

const jsxA11yRecommendedRules = jsxA11y.flatConfigs.recommended.rules;

export default [
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "src/api/types.ts",
      "src/api/openapi.ts",
      "src/lib/types/openapi.ts",
    ],
  },
  {
    files: ["src/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}", "*.config.ts"],
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
      "react-refresh": reactRefresh,
      import: importPlugin,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...jsxA11yRecommendedRules,
      // Base
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-unused-vars": "off",
      // TypeScript
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/consistent-type-imports": "error",
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "@features/*/api/*",
                "@features/*/model/*",
                "@features/*/state/*",
                "@features/*/ui/*",
              ],
              message: "Import from the feature public index instead of deep feature layers.",
            },
          ],
        },
      ],
      // React
      "react/jsx-uses-react": "off",
      "react/react-in-jsx-scope": "off",
      "react/jsx-key": "error",
      "react-refresh/only-export-components": [
        "error",
        { allowConstantExport: true, allowExportNames: ["useSidebar"] },
      ],
      // React hooks
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Import
      "import/no-duplicates": "error",
      "import/no-restricted-paths": [
        "error",
        {
          zones: [
            { target: "./src/lib", from: "./src/shared" },
            { target: "./src/lib", from: "./src/features" },
            { target: "./src/lib", from: "./src/routes" },
            { target: "./src/lib", from: "./src/app" },
            { target: "./src/shared", from: "./src/features" },
            { target: "./src/shared", from: "./src/routes" },
            { target: "./src/shared", from: "./src/app" },
            { target: "./src", from: "./tests" },
          ],
        },
      ],
      "import/order": [
        "warn",
        {
          groups: ["builtin", "external", "internal", "parent", "sibling", "index"],
          "newlines-between": "always",
          alphabetize: { order: "asc" },
        },
      ],
    },
    settings: {
      react: { version: "detect" },
    },
  },
  {
    files: ["tests/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/consistent-type-imports": "off", // vi.importActual type parameter is not a type import
      "import/no-restricted-paths": "off",
      "no-restricted-imports": "off",
      "no-console": "off",
      "react-refresh/only-export-components": "off",
    },
  },
  {
    files: ["*.config.ts"],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
];
