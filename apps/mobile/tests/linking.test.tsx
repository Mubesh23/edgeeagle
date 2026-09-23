import { getStateFromPath } from "expo-router/build/react-navigation/core/getStateFromPath";

test("Expo Router decodes query parameters with the patched dependency", () => {
  const state = getStateFromPath("/?q=hello+world&emoji=%F0%9F%A6%85", {
    screens: { index: "" },
  });
  expect(state?.routes[0].name).toBe("index");
  expect(state?.routes[0].params).toEqual({ q: "hello world", emoji: "🦅" });
});
