import { useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
} from "@mui/material";
import WarningAmber from "@mui/icons-material/WarningAmber";
import { useLanguage } from "../context/language-context.js";

export default function ConfirmActionDialog({
  open,
  title,
  message,
  confirmLabel,
  onCancel,
  onConfirm,
}) {
  const { t } = useLanguage();
  const [confirming, setConfirming] = useState(false);

  const handleConfirm = async () => {
    if (confirming) return;
    setConfirming(true);
    try {
      await onConfirm();
      onCancel();
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={confirming ? undefined : onCancel}
      maxWidth="xs"
      fullWidth
      aria-labelledby="confirm-action-dialog-title"
      aria-describedby="confirm-action-dialog-message"
    >
      <DialogTitle
        id="confirm-action-dialog-title"
        sx={{ display: "flex", alignItems: "center", gap: 1, color: "error.main" }}
      >
        <WarningAmber color="error" />
        {title}
      </DialogTitle>
      <DialogContent>
        <Alert
          id="confirm-action-dialog-message"
          severity="error"
          sx={{ "& .MuiAlert-message": { whiteSpace: "pre-line" } }}
        >
          {message}
        </Alert>
      </DialogContent>
      <DialogActions sx={{ p: 2, gap: 1 }}>
        <Button color="error" disabled={confirming} onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={confirming}
          onClick={handleConfirm}
        >
          {confirming ? t("common.loading") : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
