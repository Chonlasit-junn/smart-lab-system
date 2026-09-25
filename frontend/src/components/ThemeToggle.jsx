import { DarkMode, LightMode } from "@mui/icons-material";
import { IconButton, Tooltip } from "@mui/material";
import { useTheme } from "../context/theme-context.js";
import { useLanguage } from "../context/language-context.js";

export default function ThemeToggle({ className = "" }) {
  const { isDark, toggleTheme } = useTheme();
  const { t } = useLanguage();
  const nextModeLabel = isDark ? t("common.switchToLightTheme") : t("common.switchToDarkTheme");

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
