import { useLocation } from 'react-router-dom';
import { TableCell, TableRow } from '@mui/material';
import { useLanguage } from '../context/language-context.js';

const pageViews = {
  '/booking': ['common.labReserve', 'booking'],
  '/reserved': ['common.reserved', 'reserved'],
  '/history': ['common.history', 'history'],
  '/my-tickets': ['common.myTickets', 'myTickets'],
  '/profile': ['common.profile', 'profile'],
  '/admin': ['admin.dashboard', 'dashboard'],
  '/admin/points': ['admin.userPoints', 'points'],
  '/admin/points/policy': ['admin.pointCriteria', 'policy'],
  '/admin/roles': ['admin.roleManagement', 'roles'],
  '/manage-labs': ['admin.manageLabs', 'labs'],
  '/admin/devices': ['admin.labDevices', 'devices'],
  '/admin/reports': ['admin.usageReports', 'reports'],
  '/verify-users': ['admin.verifyUsers', 'verifyUsers'],
  '/blacklist': ['admin.blacklist', 'blacklist'],
  '/ticket': ['admin.ticket', 'ticketManager'],
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

function MobileRecordPlaceholder() {
  return <div className="loading-mobile-record">
    <div className="loading-mobile-record-heading"><Placeholder className="loading-line-title" /><Placeholder className="loading-filter" /></div>
    <Placeholder />
    <Placeholder className="loading-line-short" />
    <Placeholder />
  </div>;
}

function TablePlaceholder({ columns = ['1.6fr', '1fr', '1fr', '0.7fr'], rows = 6, mobileCards = true }) {
  return <div className={`loading-table${mobileCards ? ' loading-table--mobile-cards' : ''}`}>
    <div className="loading-table-toolbar"><Placeholder className="loading-line-title" /><Placeholder className="loading-filter" /></div>
    {Array.from({ length: rows }, (_, row) => (
      <div className="loading-table-row" key={row} style={{ '--loading-columns': columns.join(' ') }}>
        {columns.map((_, column) => <Placeholder key={column} />)}
      </div>
    ))}
    {mobileCards && <div className="loading-mobile-records">{Array.from({ length: Math.min(rows, 4) }, (_, row) => <MobileRecordPlaceholder key={row} />)}</div>}
  </div>;
}

function StatsPlaceholder({ count = 4 }) {
  return <div className="loading-stats">{Array.from({ length: count }, (_, index) => (
    <div className="loading-stat" key={index}><Placeholder className="loading-avatar" /><Placeholder /></div>
  ))}</div>;
}

function FieldPlaceholder() {
  return <div className="loading-field">
    <Placeholder className="loading-field-label" />
    <Placeholder className="loading-field-input" />
  </div>;
}

function FormPanelPlaceholder({ fields = 4, className = '' }) {
  return <div className={`loading-form-panel ${className}`}>
    <div className="loading-panel-heading"><Placeholder className="loading-line-title" /><Placeholder className="loading-filter" /></div>
    <div className="loading-fields">{Array.from({ length: fields }, (_, index) => <FieldPlaceholder key={index} />)}</div>
  </div>;
}

function FilterPanelPlaceholder({ fields = 3 }) {
  return <div className="loading-filter-panel">
    {Array.from({ length: fields }, (_, index) => <FieldPlaceholder key={index} />)}
    <Placeholder className="loading-filter-submit" />
  </div>;
}

function BookingPlaceholder() {
  return <>
    <div className="loading-card-grid">{[0, 1, 2].map(index => <CardPlaceholder key={index} />)}</div>
    <div className="loading-booking-grid">
      <div className="loading-calendar-panel">
        <div className="loading-calendar-heading"><Placeholder className="loading-line-title" /><Placeholder className="loading-calendar-control" /></div>
        <div className="loading-calendar-days">
          {Array.from({ length: 42 }, (_, index) => <Placeholder className={index < 7 ? 'loading-weekday' : 'loading-date'} key={index} />)}
        </div>
      </div>
      <div className="loading-time-panel">
        <Placeholder className="loading-line-title" />
        <Placeholder className="loading-line-short" />
        <div className="loading-time-slots">{Array.from({ length: 8 }, (_, index) => <Placeholder key={index} />)}</div>
      </div>
    </div>
  </>;
}

function ProfilePlaceholder() {
  return <div className="loading-profile">
    <div className="loading-profile-card">
      <Placeholder className="loading-profile-cover" />
      <Placeholder className="loading-profile-avatar-large" />
      <Placeholder className="loading-line-title" />
      <Placeholder className="loading-line-short" />
      <Placeholder />
    </div>
    <div className="loading-profile-main">
      <FormPanelPlaceholder fields={3} />
      <div className="loading-form-panel">
        <div className="loading-panel-heading"><Placeholder className="loading-line-title" /><Placeholder className="loading-field-label" /></div>
        <Placeholder className="loading-progress" />
        <Placeholder className="loading-line-short" />
        <TablePlaceholder columns={['1.6fr', '0.6fr']} rows={3} />
      </div>
    </div>
  </div>;
}

function AdminProfilePlaceholder() {
  return <div className="loading-admin-profile loading-form-panel">
    <div className="loading-admin-profile-heading"><Placeholder className="loading-admin-profile-avatar" /><div><Placeholder className="loading-line-title" /><Placeholder className="loading-line-short" /></div></div>
    <Placeholder className="loading-field-label" />
    <Placeholder className="loading-field-input" />
  </div>;
}

function PolicyPlaceholder() {
  return <div className="loading-panel-stack">
    <FormPanelPlaceholder fields={4} />
    <FormPanelPlaceholder fields={3} />
    <FormPanelPlaceholder fields={2} />
    <div className="loading-policy-actions"><Placeholder className="loading-policy-save" /></div>
  </div>;
}

function RolesPlaceholder() {
  return <>
    <StatsPlaceholder count={3} />
    <div className="loading-tabs"><Placeholder /><Placeholder /><Placeholder /></div>
    <TablePlaceholder columns={['1.4fr', '1.2fr', '1fr', '0.8fr']} />
  </>;
}

function LabsPlaceholder() {
  return <div className="loading-card-grid">{[0, 1, 2].map(index => <CardPlaceholder key={index} />)}</div>;
}

function ReportsPlaceholder() {
  return <>
    <FilterPanelPlaceholder fields={4} />
    <div className="loading-chart-grid">{[0, 1].map(index => (
      <div className="loading-chart-panel" key={index}>
        <Placeholder className="loading-line-title" />
        <div className="loading-chart-bars">{Array.from({ length: 8 }, (_, bar) => <Placeholder key={bar} />)}</div>
      </div>
    ))}</div>
    <TablePlaceholder columns={['1.5fr', '1fr', '1fr', '1fr']} />
  </>;
}

function BlacklistPlaceholder() {
  return <>
    <div className="loading-summary-action"><Placeholder className="loading-line-title" /><Placeholder className="loading-summary-button" /></div>
    <TablePlaceholder columns={['0.6fr', '1.5fr', '2fr', '1fr', '0.8fr']} rows={5} />
  </>;
}

function PageShape({ type }) {
  if (type === 'booking') return <BookingPlaceholder />;
  if (type === 'cards' || type === 'labs' || type === 'devices') return <LabsPlaceholder />;
  if (type === 'verifyUsers') return <div className="loading-user-card-grid">{[0, 1, 2].map(index => (
    <div className="loading-user-card" key={index}>
      <div className="loading-user-card-heading"><Placeholder className="loading-avatar" /><div><Placeholder className="loading-line-title" /><Placeholder className="loading-line-short" /></div></div>
      <div className="loading-user-card-fields"><Placeholder /><Placeholder /><Placeholder /></div>
      <div className="loading-user-card-actions"><Placeholder /><Placeholder /></div>
    </div>
  ))}</div>;
  if (type === 'dashboard') return <><StatsPlaceholder /><TablePlaceholder columns={['1.4fr', '1fr', '1fr', '0.8fr']} /></>;
  if (type === 'profile') return <ProfilePlaceholder />;
  if (type === 'adminProfile') return <AdminProfilePlaceholder />;
  if (type === 'points') return <><StatsPlaceholder count={3} /><FilterPanelPlaceholder fields={4} /><TablePlaceholder columns={['1.4fr', '1.2fr', '0.9fr', '0.8fr', '0.7fr']} /></>;
  if (type === 'pointsTable') return <TablePlaceholder columns={['1.4fr', '1.2fr', '0.9fr', '0.8fr', '0.7fr']} />;
  if (type === 'reserved' || type === 'history') return <TablePlaceholder columns={['0.7fr', '1.2fr', '1fr', '1fr', '0.6fr']} rows={5} />;
  if (type === 'myTickets') return <TablePlaceholder columns={['1.1fr', '1.5fr', '1fr', '0.8fr', '1.4fr', '0.8fr']} rows={5} />;
  if (type === 'ticketManager') return <TablePlaceholder columns={['0.6fr', '1fr', '1.8fr', '1.2fr', '0.9fr', '1fr']} rows={5} />;
  if (type === 'policy') return <PolicyPlaceholder />;
  if (type === 'roles') return <RolesPlaceholder />;
  if (type === 'rolesTable') return <><div className="loading-tabs"><Placeholder /><Placeholder /><Placeholder /></div><TablePlaceholder columns={['1.4fr', '1.2fr', '1fr', '0.8fr']} /></>;
  if (type === 'reports') return <ReportsPlaceholder />;
  if (type === 'blacklist') return <BlacklistPlaceholder />;
  if (type === 'userDetails') return <div className="loading-user-details">
    <div className="loading-user-detail-panels">
      {[0, 1].map(index => <div className="loading-form-panel" key={index}>
        <Placeholder className="loading-line-title" />
        <div className="loading-fields">{Array.from({ length: index === 0 ? 6 : 4 }, (_, field) => <FieldPlaceholder key={field} />)}</div>
      </div>)}
    </div>
    <div className="loading-form-panel"><div className="loading-tabs">{[0, 1, 2, 3, 4].map(index => <Placeholder key={index} />)}</div><TablePlaceholder columns={['1.2fr', '1.2fr', '1fr', '0.8fr']} rows={4} /></div>
  </div>;
  if (type === 'tableRows') return <div className="loading-inline-table-rows" aria-hidden="true">{Array.from({ length: 4 }, (_, row) => <div className="loading-inline-table-row" key={row}>{Array.from({ length: 5 }, (_, column) => <Placeholder key={column} />)}</div>)}</div>;
  return <TablePlaceholder />;
}

export function PageContentLoadingState({ type = 'table' }) {
  const { t } = useLanguage();

  return <div className="loading-inline" role="status" aria-live="polite">
    <span className="loading-sr-only">{t('common.loading')}</span>
    <PageShape type={type} />
  </div>;
}

export function LoadingTableRows({ columns = 5, rows = 4, label }) {
  return Array.from({ length: rows }, (_, row) => (
    <TableRow key={row} aria-label={row === 0 ? label : undefined} aria-hidden={row > 0 ? 'true' : undefined}>
      {Array.from({ length: columns }, (_, column) => (
        <TableCell key={column}><Placeholder className="loading-table-cell-placeholder" /></TableCell>
      ))}
    </TableRow>
  ));
}

export default function PageLoadingState({ viewOverride }) {
  const { pathname } = useLocation();
  const { t } = useLanguage();
  const routeView = pageViews[pathname.replace(/\/$/, '')];
  const view = viewOverride ? [routeView?.[0] || 'common.profile', viewOverride] : routeView;

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
          <div className={`loading-content loading-view-${view[1]}`}>
            <div className="loading-heading"><Placeholder className="loading-line-title" /><span className="loading-caption">{t('common.loading')}</span></div>
            <PageShape type={view[1]} />
          </div>
        </div>
      </div>
    )}
  </div>;
}
