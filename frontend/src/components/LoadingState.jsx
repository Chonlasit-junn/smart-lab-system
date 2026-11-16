import { PageContentLoadingState } from './PageLoadingState';

export default function LoadingState({ type = 'table' }) {
  return <PageContentLoadingState type={type} />;
}
