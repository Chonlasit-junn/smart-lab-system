import { Component } from 'react';
import { useLanguage } from '../context/language-context.js';

function PageError() {
  const { t } = useLanguage();
  return (
    <main role="alert" style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: 'var(--bg-color)', color: 'var(--text-dark)' }}>
      <section style={{ maxWidth: 480, textAlign: 'center' }}>
        <h1>{t('common.pageFailed')}</h1>
        <p>{t('common.pageFailedHint')}</p>
        <button type="button" style={{ font: 'inherit', padding: '10px 24px', borderRadius: 12, border: '1px solid var(--brand-color)', background: 'var(--brand-color)', color: 'var(--bg-color)', cursor: 'pointer' }} onClick={() => window.location.reload()}>{t('common.retry')}</button>
        <p><a href="/" style={{ color: 'var(--text-dark)' }}>{t('common.backToLogin')}</a></p>
      </section>
    </main>
  );
}

// A full reload also clears React.lazy's cached rejection after an old chunk
// disappears during deployment. Never reload automatically (offline loop).
export default class AppErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <PageError /> : this.props.children;
  }
}
