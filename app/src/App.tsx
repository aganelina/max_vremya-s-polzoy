import { createContext, lazy, Suspense, useContext, useEffect, useState } from 'react';
import { createHashRouter, Navigate, Outlet, RouterProvider, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, DEMO_ACTIVE, exitDemo, hasApiSession, isApiError, USE_MOCKS } from '@/api';
import { useGoBack } from '@/lib/nav';
import { backButton } from '@/max/bridge';
import { ErrorState, Loading, Screen } from '@/ui';
import { AppNavigation } from '@/ui/AppNavigation';
import { EntryScreen } from '@/screens/onboarding/Entry';

import { CompanyScreen } from '@/screens/participant/Company';
import { DealScreen } from '@/screens/participant/Deal';
import { MyDealsScreen } from '@/screens/participant/MyDeals';
import { CalendarScreen } from '@/screens/participant/Calendar';
import { HomeScreen } from '@/screens/participant/Home';
import { CheckInScreen } from '@/screens/participant/CheckIn';
import { SearchScreen } from '@/screens/participant/Search';
import { ProfileScreen } from '@/screens/participant/Profile';
import { WindowsScreen } from '@/screens/participant/Windows';
import { MicroTaskScreen } from '@/screens/participant/MicroTask';
import { HourBankScreen } from '@/screens/participant/HourBank';
import { MentorshipScreen } from '@/screens/participant/Mentorship';
import { RouteScreen } from '@/screens/participant/Route';
import { TransferScreen } from '@/screens/participant/Transfer';
import { CertificateScreen } from '@/screens/participant/Certificate';
import { PrivacyScreen } from '@/screens/participant/Privacy';
import { ConsentScreen } from '@/screens/onboarding/Consent';
import { PlaceScreen } from '@/screens/onboarding/Place';
import { CoordHomeScreen } from '@/screens/coordinator/CoordHome';
import { AttendanceScreen } from '@/screens/coordinator/Attendance';
import { NewShiftScreen } from '@/screens/coordinator/NewShift';
import { UrgentScreen } from '@/screens/coordinator/Urgent';
import { ReviewsScreen } from '@/screens/coordinator/Reviews';
import { MetricsScreen } from '@/screens/coordinator/Metrics';
import { AccessScreen } from '@/screens/coordinator/Access';
import { MessageScreen } from '@/screens/coordinator/Message';
import { MicroTasksScreen } from '@/screens/coordinator/MicroTasks';
import { NewMicroTaskScreen } from '@/screens/coordinator/NewMicroTask';
import { FriendInviteScreen } from '@/screens/participant/FriendInvite';
import { CompanyJoinScreen } from '@/screens/participant/CompanyJoin';
import { OrgInviteScreen } from '@/screens/participant/OrgInvite';
import { OrgApplyScreen } from '@/screens/participant/OrgApply';
import { OperatorOrgsScreen } from '@/screens/operator/OperatorOrgs';

interface StartState {
  route: string | null;
  used: boolean;
}
const StartContext = createContext<StartState>({ route: null, used: true });
const takeStart = (start: StartState) => (start.used ? null : start.route);

function MaxBackButton() {
  const onBack = useGoBack();
  const { pathname } = useLocation();
  useEffect(() => {
    if (pathname === '/' || pathname === '/welcome') backButton.hide();
    else backButton.show();
    backButton.onClick(onBack);
    return () => backButton.offClick(onBack);
  }, [pathname, onBack]);
  return null;
}

function Gate() {
  const { pathname, search } = useLocation();
  const start = useContext(StartContext);
  const session = hasApiSession();
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, enabled: session });
  if (!session) return pathname === '/privacy' ? <Outlet /> : <EntryScreen startRoute={takeStart(start) ?? pathname} />;
  if (me.isPending) return <Screen><Loading /></Screen>;
  if (me.isError) {
    const relaunch = isApiError(me.error, 'init_data_invalid', 'init_data_expired');
    if (relaunch) return <EntryScreen expired startRoute={takeStart(start) ?? pathname} />;
    return (
      <Screen>
        <ErrorState error={me.error} onRetry={() => me.refetch()} />
      </Screen>
    );
  }
  const free = pathname.startsWith('/welcome') || pathname === '/privacy' || pathname.startsWith('/demo') || pathname.startsWith('/org/');
  if (!me.data.onboarded && !free) {
    const next = takeStart(start) ?? pathname + search;
    return <Navigate to={`/welcome?next=${encodeURIComponent(next)}`} replace />;
  }
  if (!me.data.onboarded || pathname.startsWith('/welcome')) return <Outlet />;
  return <div className="app-shell"><AppNavigation me={me.data} /><div className="app-content"><Outlet /></div></div>;
}

function Root() {
  const start = useContext(StartContext);
  const { pathname } = useLocation();
  useEffect(() => {
    if (pathname === start.route || pathname.startsWith('/welcome')) start.used = true;
  }, [pathname, start]);
  return (
    <>
      <MaxBackButton />
      {DEMO_ACTIVE && <div className="demo-session"><button type="button" onClick={exitDemo}>Выйти из демо</button></div>}
      <Gate />
    </>
  );
}

function Index() {
  const start = useContext(StartContext);
  const [to] = useState(() => takeStart(start));
  useEffect(() => {
    start.used = true;
  }, []);
  if (to) return <Navigate to={to} replace />;
  return <HomeScreen />;
}

const DemoIndex = USE_MOCKS || import.meta.env.DEV ? lazy(() => import('@/screens/DemoIndex').then((m) => ({ default: m.DemoIndex }))) : null;

const router = createHashRouter([
  {
    element: <Root />,
    children: [
      { path: '/', element: <Index /> },
      { path: '/welcome', element: <ConsentScreen /> },
      { path: '/welcome/place', element: <PlaceScreen /> },
      { path: '/calendar', element: <CalendarScreen /> },
      { path: '/search', element: <SearchScreen /> },
      { path: '/company/:id', element: <CompanyScreen /> },
      { path: '/deals/:id', element: <DealScreen /> },
      { path: '/deals/:id/check-in', element: <CheckInScreen /> },
      { path: '/my', element: <MyDealsScreen /> },
      { path: '/profile', element: <ProfileScreen /> },
      { path: '/windows', element: <WindowsScreen /> },
      { path: '/micro', element: <MicroTaskScreen /> },
      { path: '/bank', element: <HourBankScreen /> },
      { path: '/mentor', element: <MentorshipScreen /> },
      { path: '/route', element: <RouteScreen /> },
      { path: '/t/:token', element: <TransferScreen /> },
      { path: '/i/:token', element: <FriendInviteScreen /> },
      { path: '/co/:token', element: <CompanyJoinScreen /> },
      { path: '/org/:token', element: <OrgInviteScreen /> },
      { path: '/orgs/apply', element: <OrgApplyScreen /> },
      { path: '/certificate', element: <CertificateScreen /> },
      { path: '/privacy', element: <PrivacyScreen /> },
      { path: '/coord', element: <CoordHomeScreen /> },
      { path: '/coord/shifts/new', element: <NewShiftScreen /> },
      { path: '/coord/shifts/:id', element: <AttendanceScreen /> },
      { path: '/coord/shifts/:id/message', element: <MessageScreen /> },
      { path: '/coord/urgent', element: <UrgentScreen /> },
      { path: '/coord/reviews', element: <ReviewsScreen /> },
      { path: '/coord/metrics', element: <MetricsScreen /> },
      { path: '/coord/access', element: <AccessScreen /> },
      { path: '/coord/micro', element: <MicroTasksScreen /> },
      { path: '/coord/micro/new', element: <NewMicroTaskScreen /> },
      { path: '/operator/orgs', element: <OperatorOrgsScreen /> },
      { path: '/operator/metrics', element: <MetricsScreen operator /> },
      ...(DemoIndex ? [{ path: '/demo', element: <Suspense fallback={<Screen><Loading /></Screen>}><DemoIndex /></Suspense> }] : []),
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);

export function App({ startRoute }: { startRoute: string | null }) {
  const [start] = useState<StartState>(() => ({ route: startRoute, used: false }));
  return (
    <StartContext.Provider value={start}>
      <RouterProvider router={router} />
    </StartContext.Provider>
  );
}
