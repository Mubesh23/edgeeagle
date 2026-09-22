import { ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

export default function FoundationScreen() {
  const insets = useSafeAreaInsets();
  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      style={{ flex: 1, backgroundColor: "#101820" }}
      contentContainerStyle={{
        paddingTop: 32,
        paddingBottom: Math.max(insets.bottom, 24),
        paddingLeft: Math.max(insets.left, 24),
        paddingRight: Math.max(insets.right, 24),
        gap: 24,
      }}
    >
      <Text selectable style={{ color: "#76d9ba", fontSize: 14 }}>
        MOBILE FOUNDATION
      </Text>
      <Text
        selectable
        accessibilityRole="header"
        style={{ color: "#e6edf3", fontSize: 32, fontWeight: "700" }}
      >
        Price, not picks.
      </Text>
      <Text
        selectable
        style={{ color: "#e6edf3", fontSize: 17, lineHeight: 26 }}
      >
        Sports-market research, built around probability, price, and measured
        risk.
      </Text>
      <View
        style={{
          padding: 20,
          gap: 12,
          backgroundColor: "#17232e",
          borderRadius: 12,
          borderCurve: "continuous",
        }}
      >
        <Text
          selectable
          accessibilityRole="header"
          style={{ color: "#e6edf3", fontSize: 20, fontWeight: "600" }}
        >
          An offline starting point
        </Text>
        <Text
          selectable
          style={{ color: "#b8c7d4", fontSize: 17, lineHeight: 26 }}
        >
          This shell makes no API or provider requests. Events, watchlists,
          alerts, and portfolio workflows are not connected yet.
        </Text>
      </View>
      <Text
        selectable
        style={{ color: "#b8c7d4", fontSize: 15, lineHeight: 24 }}
      >
        No predictions, paper positions, or real-money execution are available
        in this foundation build.
      </Text>
    </ScrollView>
  );
}
