import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", ".expo/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["*.cjs"],
    languageOptions: { globals: { module: "readonly", require: "readonly" } },
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
  {
    files: ["tests/**/*.cjs"],
    languageOptions: {
      globals: {
        beforeEach: "readonly",
        afterEach: "readonly",
        jest: "readonly",
        global: "readonly",
      },
    },
  },
);
