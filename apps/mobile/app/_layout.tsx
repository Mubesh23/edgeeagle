import { Stack } from "expo-router/stack";
import { StatusBar } from "expo-status-bar";

export default function RootLayout() {
  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: "#101820" },
          headerTintColor: "#e6edf3",
          contentStyle: { backgroundColor: "#101820" },
        }}
      >
        <Stack.Screen name="index" options={{ title: "EdgeEagle" }} />
      </Stack>
    </>
  );
}
