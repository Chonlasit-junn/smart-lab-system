import { Box, Typography } from '@mui/material';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import { passwordPolicyRequirements } from '../utils/passwordPolicy.js';

export default function PasswordRequirements({ value, translations }) {
  const requirements = passwordPolicyRequirements(value);
  const items = [
    ['minLength', translations.passwordMinLength],
    ['uppercase', translations.passwordUppercase],
    ['number', translations.passwordNumber],
    ['allowedCharacters', translations.passwordCharacters],
    ['maxLength', translations.passwordMaxLength],
  ];

  return (
    <Box component="ul" sx={{ listStyle: 'none', p: 0, m: 0, display: 'grid', gap: 0.5 }}>
      {items.map(([requirement, label]) => {
        const satisfied = requirements[requirement];
        return (
          <Box component="li" key={requirement} sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75,
            color: satisfied ? 'var(--success-color)' : 'var(--text-muted)' }}>
            {satisfied ? <CheckIcon fontSize="small" /> : <CloseIcon fontSize="small" />}
            <Typography component="span" variant="caption" sx={{ lineHeight: 1.4 }}>{label}</Typography>
          </Box>
        );
      })}
    </Box>
  );
}
