import { DarkMode, LightMode } from "@mui/icons-material";
import { IconButton, Tooltip } from "@mui/material";
import { useTheme } from "../context/theme-context.js";

export default function ThemeToggle({ className = "" }) {
  const { isDark, toggleTheme } = useTheme();
  const nextModeLabel = isDark ? "สลับเป็น Light Theme" : "สลับเป็น Dark Theme";

  return (
    <Tooltip title={nextModeLabel} arrow>
      <IconButton
        className={className}
        onClick={toggleTheme}
        aria-label={nextModeLabel}
        aria-pressed={isDark}
      >
        {isDark ? <LightMode /> : <DarkMode />}
      </IconButton>
    </Tooltip>
  );
}
