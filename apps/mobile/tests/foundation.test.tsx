import { render, screen } from "@testing-library/react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import FoundationScreen from "../src/foundation-screen";

test("renders the offline foundation without suggesting live product capabilities", () => {
  render(
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 390, height: 844 },
        insets: { top: 47, bottom: 34, left: 0, right: 0 },
      }}
    >
      <FoundationScreen />
    </SafeAreaProvider>,
  );
  expect(
    screen.getByRole("header", { name: "Price, not picks." }),
  ).toBeOnTheScreen();
  expect(
    screen.getByText(/makes no API or provider requests/),
  ).toBeOnTheScreen();
  expect(screen.getByText(/No predictions, paper positions/)).toBeOnTheScreen();
  expect(globalThis.fetch).not.toHaveBeenCalled();
});
