import { Alert, Button } from '@mui/material';
import { useLanguage } from '../context/language-context.js';

export default function LoadError({ onRetry }) {
  const { t } = useLanguage();
  return <Alert severity="error" sx={{ mb: 3 }} action={
    <Button color="inherit" size="small" onClick={onRetry}>{t('common.retry')}</Button>
  }>{t('common.loadFailed')}</Alert>;
}
