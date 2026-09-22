beforeEach(() => {
  jest.spyOn(global, "fetch").mockImplementation(() => {
    throw new Error("Network requests are forbidden in mobile unit tests");
  });
});
afterEach(() => jest.restoreAllMocks());
