const scrollbarStyles = {
  scrollbarColor: "var(--text-muted) var(--surface-subtle)",
  scrollbarWidth: "thin",
  "&:focus-visible": { outline: "3px solid var(--focus-ring)", outlineOffset: -3 },
  "&::-webkit-scrollbar": { width: 10, height: 10 },
  "&::-webkit-scrollbar-track": { backgroundColor: "var(--surface-subtle)" },
  "&::-webkit-scrollbar-thumb": {
    backgroundColor: "var(--text-muted)",
    border: "2px solid var(--surface-subtle)",
    borderRadius: 999,
  },
};

export const verticalScrollAreaSx = {
  maxHeight: "min(60vh, 520px)",
  overflowY: "auto",
  overscrollBehavior: "contain",
  ...scrollbarStyles,
};
