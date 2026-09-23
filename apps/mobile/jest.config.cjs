module.exports = {
  preset: "jest-expo",
  testMatch: ["<rootDir>/tests/**/*.test.tsx"],
  setupFilesAfterEnv: ["<rootDir>/tests/setup.cjs"],
  watchman: false,
  // Transform the patched decoder's ESM export just as Metro does.
  transformIgnorePatterns:
    require("jest-expo/jest-preset").transformIgnorePatterns.map((pattern) =>
      pattern.replace("(?!(.pnpm|", "(?!(decode-uri-component|.pnpm|"),
    ),
};
