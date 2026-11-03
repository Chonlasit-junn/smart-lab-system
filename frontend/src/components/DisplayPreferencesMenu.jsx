import { useState } from "react";
import { DarkMode, Language, LightMode, Tune } from "@mui/icons-material";
import { IconButton, ListItemIcon, ListItemText, Menu, MenuItem, Tooltip } from "@mui/material";
import { useLanguage } from "../context/language-context.js";
import { useTheme } from "../context/theme-context.js";

export default function DisplayPreferencesMenu() {
  const [anchorEl, setAnchorEl] = useState(null);
  const { t, toggleLanguage } = useLanguage();
  const { isDark, toggleTheme } = useTheme();
  const open = Boolean(anchorEl);
  const themeAction = isDark ? t("common.switchToLightTheme") : t("common.switchToDarkTheme");

  const handleLanguageChange = () => {
    setAnchorEl(null);
    toggleLanguage();
  };

  const handleThemeChange = () => {
    setAnchorEl(null);
    toggleTheme();
  };

  return (
    <>
      <Tooltip title={t("common.displayOptions")} arrow>
        <IconButton
          className="global-display-preferences"
          onClick={(event) => setAnchorEl(event.currentTarget)}
          aria-label={t("common.displayOptions")}
          aria-haspopup="menu"
          aria-expanded={open ? "true" : undefined}
          aria-controls={open ? "display-preferences-menu" : undefined}
        >
          <Tune />
        </IconButton>
      </Tooltip>
      <Menu
        id="display-preferences-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <MenuItem onClick={handleLanguageChange}>
          <ListItemIcon><Language fontSize="small" /></ListItemIcon>
          <ListItemText primary={t("language.aria")} />
        </MenuItem>
        <MenuItem onClick={handleThemeChange} aria-pressed={isDark}>
          <ListItemIcon>{isDark ? <LightMode fontSize="small" /> : <DarkMode fontSize="small" />}</ListItemIcon>
          <ListItemText primary={themeAction} />
        </MenuItem>
      </Menu>
    </>
  );
}
