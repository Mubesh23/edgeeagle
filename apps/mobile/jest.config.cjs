module.exports = {
  preset: "jest-expo",
  testMatch: ["<rootDir>/tests/**/*.test.tsx"],
  setupFilesAfterEnv: ["<rootDir>/tests/setup.cjs"],
  watchman: false,
};
