import { registerLocales } from './locales.js';
import { isValidNewPassword } from './passwordPolicy.js';

export const passwordResetLocales = {
  en: {
    ...registerLocales.en,
    title: 'Reset password', tabTitle: 'Reset password | Smart Lab',
    intro: 'Enter the email address used for your account.',
    notice: 'If this email has an account, we will send a reset code. Check your inbox and spam folder.',
    newPassword: 'New password', confirmPassword: 'Confirm new password',
    passwordHint: 'Use at least 8 characters, with no more than 72 UTF-8 bytes.',
    passwordInvalid: 'Use at least 8 characters and no more than 72 UTF-8 bytes.',
    passwordMismatch: 'Passwords do not match.',
    reset: 'Save new password', success: 'Password changed. Please log in with your new password.',
    failed: 'Unable to reset your password. Please try again.',
    showPassword: 'Show passwords', hidePassword: 'Hide passwords',
  },
  th: {
    ...registerLocales.th,
    title: 'ตั้งรหัสผ่านใหม่', tabTitle: 'ลืมรหัสผ่าน | Smart Lab',
    intro: 'กรอกอีเมลที่ใช้สมัครสมาชิก',
    notice: 'หากอีเมลนี้มีบัญชี ระบบจะส่งรหัสให้ กรุณาตรวจกล่องจดหมายและอีเมลขยะ',
    newPassword: 'รหัสผ่านใหม่', confirmPassword: 'ยืนยันรหัสผ่านใหม่',
    passwordHint: 'ใช้รหัสผ่านอย่างน้อย 8 ตัวอักษร และไม่เกิน 72 ไบต์ UTF-8',
    passwordInvalid: 'ใช้รหัสผ่านอย่างน้อย 8 ตัวอักษร และไม่เกิน 72 ไบต์ UTF-8',
    passwordMismatch: 'รหัสผ่านทั้งสองช่องไม่ตรงกัน',
    reset: 'บันทึกรหัสผ่านใหม่', success: 'เปลี่ยนรหัสผ่านแล้ว กรุณาเข้าสู่ระบบด้วยรหัสผ่านใหม่',
    failed: 'ตั้งรหัสผ่านใหม่ไม่สำเร็จ กรุณาลองอีกครั้ง',
    showPassword: 'แสดงรหัสผ่าน', hidePassword: 'ซ่อนรหัสผ่าน',
  },
};

export function passwordResetError(password, confirmation, t) {
  if (!isValidNewPassword(password)) {
    return t.passwordInvalid;
  }
  return password === confirmation ? '' : t.passwordMismatch;
}
