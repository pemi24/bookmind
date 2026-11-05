import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";
import { defineConfig } from "eslint/config";

export default defineConfig(
  { ignores: ["dist", "node_modules"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      // The classic hook rules; the React Compiler rules in the plugin's newer presets aren't used here.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // tsc already reports unused locals/parameters (noUnusedLocals); keep "_"-prefixed ones allowed.
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" }],
      // `cond ? a() : b()` as a statement is used deliberately in a few event handlers.
      "@typescript-eslint/no-unused-expressions": ["error", { allowTernary: true, allowShortCircuit: true }],
    },
  },
  {
    files: ["**/*.test.{ts,tsx}"],
    rules: { "@typescript-eslint/no-explicit-any": "off", "@typescript-eslint/no-non-null-assertion": "off" },
  },
);
