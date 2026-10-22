import { Box, CircularProgress, Typography } from '@mui/material';
import { useLanguage } from '../context/language-context.js';

export default function LoadingState() {
  const { t } = useLanguage();
  return <Box role="status" aria-live="polite" sx={{ minHeight: 280, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
    <CircularProgress aria-hidden="true" />
    <Typography color="text.secondary">{t('common.loading')}</Typography>
  </Box>;
}
