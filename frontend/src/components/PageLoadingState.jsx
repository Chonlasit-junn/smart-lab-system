import { useLocation } from 'react-router-dom';
import { useLanguage } from '../context/language-context.js';

const pageViews = {
  '/booking': ['common.labReserve', 'cards'],
  '/reserved': ['common.reserved', 'table'],
  '/history': ['common.history', 'table'],
  '/my-tickets': ['common.myTickets', 'table'],
  '/profile': ['common.profile', 'profile'],
  '/admin': ['admin.dashboard', 'dashboard'],
  '/admin/points': ['admin.userPoints', 'table'],
  '/admin/points/policy': ['admin.pointCriteria', 'table'],
  '/admin/roles': ['admin.roleManagement', 'table'],
  '/manage-labs': ['admin.manageLabs', 'cards'],
  '/admin/devices': ['admin.labDevices', 'table'],
  '/admin/reports': ['admin.usageReports', 'table'],
  '/verify-users': ['admin.verifyUsers', 'cards'],
  '/blacklist': ['admin.blacklist', 'table'],
  '/ticket': ['admin.ticket', 'table'],
};

function Placeholder({ className = '' }) {
  return <span className={`loading-placeholder ${className}`} />;
}

function Brand() {
  return <div className="loading-brand"><span className="loading-brand-mark" />Smart Lab</div>;
}

function CardPlaceholder() {
  return <div className="loading-card">
    <Placeholder className="loading-card-image" />
    <div className="loading-card-body">
      <Placeholder className="loading-line-title" />
      <Placeholder />
      <Placeholder className="loading-line-short" />
      <div className="loading-card-footer"><Placeholder /><Placeholder /></div>
    </div>
  </div>;
}

function TablePlaceholder() {
  return <div className="loading-table">
    <div className="loading-table-toolbar"><Placeholder className="loading-line-title" /><Placeholder className="loading-filter" /></div>
    {Array.from({ length: 6 }, (_, index) => (
      <div className="loading-table-row" key={index}>
        <Placeholder /><Placeholder /><Placeholder /><Placeholder />
      </div>
    ))}
  </div>;
}

export default function PageLoadingState() {
  const { pathname } = useLocation();
  const { t } = useLanguage();
  const view = pageViews[pathname.replace(/\/$/, '')];

  return <div className="page-loading" role="status" aria-live="polite">
    <span className="loading-sr-only">{t('common.loading')}</span>
    {!view ? (
      <div className="loading-auth" aria-hidden="true">
        <div className="loading-auth-banner"><Brand /><h1>{t('common.brandTagline')}</h1></div>
        <div className="loading-auth-panel">
          <div className="loading-auth-form">
            <Placeholder className="loading-line-title" />
            <p className="loading-caption">{t('common.loading')}</p>
            <Placeholder className="loading-input" /><Placeholder className="loading-input" />
            <Placeholder className="loading-submit" /><Placeholder className="loading-line-short" />
          </div>
        </div>
      </div>
    ) : (
      <div className="loading-app" aria-hidden="true">
        <aside className="loading-sidebar">
          <Brand />
          <div className="loading-nav">{Array.from({ length: 6 }, (_, index) => <Placeholder className="loading-nav-item" key={index} />)}</div>
          <Placeholder className="loading-nav-bottom" />
        </aside>
        <div className="loading-main">
          <header className="loading-header">
            <div className="loading-mobile-brand"><Brand /></div>
            <span className="loading-page-title">{t(view[0])}</span>
            <Placeholder className="loading-search" />
            <Placeholder className="loading-avatar" />
          </header>
          <div className="loading-content">
            <div className="loading-heading"><Placeholder className="loading-line-title" /><span className="loading-caption">{t('common.loading')}</span></div>
            {view[1] === 'cards' && <div className="loading-card-grid">{[0, 1, 2].map(index => <CardPlaceholder key={index} />)}</div>}
            {view[1] === 'dashboard' && <>
              <div className="loading-stats">{[0, 1, 2, 3].map(index => <div className="loading-stat" key={index}><Placeholder className="loading-avatar" /><Placeholder /></div>)}</div>
              <TablePlaceholder />
            </>}
            {view[1] === 'profile' && <div className="loading-profile"><CardPlaceholder /><div><TablePlaceholder /><TablePlaceholder /></div></div>}
            {view[1] === 'table' && <TablePlaceholder />}
          </div>
        </div>
      </div>
    )}
  </div>;
}
