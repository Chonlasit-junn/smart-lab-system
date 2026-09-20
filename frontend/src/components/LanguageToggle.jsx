import LanguageIcon from "@mui/icons-material/Language";
import { Button, Tooltip } from "@mui/material";
import { useLanguage } from "../context/language-context.js";

export default function LanguageToggle({ className = "" }) {
  const { t, toggleLanguage } = useLanguage();

  return (
    <Tooltip title={t("language.aria")} arrow>
      <Button
        className={className}
        onClick={toggleLanguage}
        startIcon={<LanguageIcon />}
        size="small"
        variant="outlined"
        aria-label={t("language.aria")}
      >
        <span className="font-baseline-text">{t("language.switchTo")}</span>
      </Button>
    </Tooltip>
  );
}
