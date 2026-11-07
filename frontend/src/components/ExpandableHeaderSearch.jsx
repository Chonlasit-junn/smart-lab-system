import { Children, cloneElement, useEffect, useRef } from "react";
import { Close, Search } from "@mui/icons-material";
import { Box, IconButton } from "@mui/material";
import { useLanguage } from "../context/language-context.js";

export default function ExpandableHeaderSearch({
  children,
  disabled = false,
  id,
  isOpen,
  label,
  onExpandedChange,
}) {
  const controlRef = useRef(null);
  const { t } = useLanguage();
  const searchControl = Children.only(children);

  useEffect(() => {
    if (!isOpen) return;
    const input = controlRef.current?.querySelector("input");
    if (input && !input.disabled) input.focus();
  }, [isOpen]);

  const handleKeyDown = (event) => {
    if (event.key === "Escape" && isOpen) {
      event.stopPropagation();
      onExpandedChange(false);
    }
  };

  return (
    <Box
      ref={controlRef}
      className={`expandable-header-search${isOpen ? " is-open" : ""}`}
      onKeyDownCapture={handleKeyDown}
    >
      {cloneElement(searchControl, {
        id,
        className: `${searchControl.props.className || ""} expandable-header-search-field`.trim(),
      })}
      <IconButton
        className="expandable-header-search-toggle"
        aria-label={isOpen ? t("common.close") : label}
        aria-expanded={isOpen}
        aria-controls={id}
        disabled={disabled}
        onClick={() => onExpandedChange(!isOpen)}
        size="small"
      >
        {isOpen ? <Close /> : <Search />}
      </IconButton>
    </Box>
  );
}
