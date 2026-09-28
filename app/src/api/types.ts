export type Category = 'people' | 'animals' | 'ecology' | 'books' | 'things' | 'online';
export type Transport = 'walk' | 'transit' | 'scooter';
export type NotifyMode = 'all' | 'mine' | 'pause';
export type Origin = 'campus' | 'home';
export type WhenSlot = 'now' | 'tonight' | 'tomorrow' | 'weekend';

export interface Dict {
  id: string;
  name: string;
}


export interface Me {
  id: string;
  firstName: string;
  onboarded: boolean;
  consentAt: string | null;
  university: Dict | null;
  district: Dict | null;
  interests: Category[];
  transport: Transport;
  notify: NotifyMode;
  pauseUntil: string | null;
  weeklySearch: SearchParams | null;
  stats: {
    hoursYear: number;
    hoursMonth: number;
    deals: number;
    streakWeeks: number;
    bankBalance: number;
  };
  roles: {
    coordinator: boolean;
    mentorEligible: boolean;
    operator?: boolean;
  };
}

export type ProfilePatch = Partial<Pick<Me, 'interests' | 'transport' | 'notify'>> & {
  universityId?: string;
  districtId?: string;
};

export interface Dictionaries {
  universities: Dict[];
  districts: Dict[];
}


export interface Org {
  id: string;
  name: string;
  verified: boolean;
}

export interface Deal {
  id: string;
  title: string;
  org: Org;
  category: Category;
  startsAt: string;
  endsAt: string;
  hours: number;
  address: string;
  addressNote?: string;
  description: string;
  travelMin: number | null;
  capacity: number;
  quorum: boolean;
  taken: number;
  goingInitials: string[];
  checkInFrom: string;
  checkInTo: string;
  cancelUntil: string;
  instructionsAt: string;
  myBooking: Booking | null;
  impact?: string;
}

export interface SearchParams {
  durationMin: 30 | 60 | 120 | 180;
  when: WhenSlot;
  from: Origin;
  window?: { from: string; to: string };
  companyId?: string;
}

export interface SearchResultItem {
  deal: Deal;
  slackMin: number;
  fit: 'ok' | 'tight';
}

export interface TimeWindow {
  from: string;
  to: string;
}

export type WindowSource = 'explicit' | 'company' | 'schedule' | 'fallback' | 'none';

export interface SearchResult {
  window: TimeWindow | null;
  windowSource: WindowSource;
  nextWindow: TimeWindow | null;
  items: SearchResultItem[];
  counts: Partial<Record<Category, number>> & { all: number; near: number };
}

export interface SearchPreview {
  count: number;
  windowSource?: WindowSource;
}

export interface Booking {
  id: string;
  dealId: string;
  status: 'going' | 'checked_in' | 'manual' | 'done' | 'cancelled' | 'no_show';
  checkedInAt: string | null;
}

export interface HistoryItem {
  id: string;
  title: string;
  date: string;
  place: string;
  hours: number;
}

export interface MyDeals {
  past: { id: string; dealId: string; title: string; startsAt: string; status: Booking['status']; canContact: boolean }[];
  upcoming: Deal[];
  history: HistoryItem[];
}

export interface FriendInvite {
  status: 'ok' | 'full' | 'expired';
  inviterName: string | null;
  deal: Deal | null;
}


export interface CompanyMember {
  id: string;
  firstName: string;
  initial: string;
  isMe: boolean;
  window: { from: string; to: string } | null;
  remindedAt: string | null;
}

export interface Company {
  id: string;
  date: string;
  commonWindow: { from: string; to: string } | null;
  members: CompanyMember[];
  inviteLink: string;
  deals: { deal: Deal; votes: string[] }[];
  pickedDealId: string | null;
}


export interface CheckInResult {
  ok: boolean;
  checkedInAt?: string;
  error?: 'expired' | 'wrong_code' | 'too_early' | 'too_late';
  late?: boolean;
}


export interface FreeWindow {
  id: string;
  day: string;
  from: string;
  to: string;
  startsAt: string;
  endsAt: string;
  after: string;
  place: string;
}

export interface Schedule {
  fileName: string | null;
  windows: FreeWindow[];
}


export interface MicroTask {
  id: string;
  title: string;
  org: Org;
  minutes: number;
  text: string;
  status: 'free' | 'taken' | 'sent' | 'accepted' | 'returned';
  deadline: string | null;
  answer: string;
  reviewNote?: string;
}


export interface HelpRequest {
  id: string;
  text: string;
  hours: number;
  when: string;
  district: string;
  mine: boolean;
  responded: boolean;
  helperName: string | null;
  status: 'open' | 'matched' | 'closed';
}

export interface HourBank {
  balance: number;
  reserved: number;
  maxOpenRequests: number;
  others: HelpRequest[];
  mine: HelpRequest[];
}


export interface MentorRequest {
  id: string;
  newbieName: string;
  deal: Deal;
}

export interface Mentorship {
  eligible: boolean;
  dealsDone: number;
  dealsRequired: number;
  accepting: boolean;
  requests: MentorRequest[];
  pairs: { id: string; newbieName: string; dealTitle: string; startsAt: string }[];
}


export interface Route {
  window: TimeWindow | null;
  legs: { deal: Deal; walkToNextMin: number | null }[];
}


export interface SeatTransfer {
  status: 'ok' | 'taken' | 'expired';
  fromName: string | null;
  deal: Deal | null;
}


export interface FileLink {
  url: string;
  fileName: string;
  expiresAt: string;
}

export type CertPeriod = 'semester' | 'all';

export interface Certificate {
  period: CertPeriod;
  periodLabel: string;
  generatedAt: string;
  participant: { firstName: string; university: string };
  rows: { date: string; title: string; org: string; hours: number }[];
  total: number;
  verifyCode: string;
  verifyUrl: string;
}


export interface Shift {
  id: string;
  title: string;
  org: Org;
  category: Category;
  startsAt: string;
  endsAt: string;
  address: string;
  capacity: number;
  booked: number;
  quorum: boolean;
  instructions: string;
  place: 'org' | 'district' | 'online';
  status: 'open' | 'cancelled' | 'finished';
}

export interface Participant {
  id: string;
  firstName: string;
  status: 'booked' | 'came' | 'late' | 'no_show' | 'manual';
  checkedInAt: string | null;
}

export interface ShiftAttendance {
  shift: Shift;
  participants: Participant[];
}

export interface CheckInCode {
  code: string;
  qrPayload: string;
  expiresAt: string;
}

export interface NewShift {
  title: string;
  date: string;
  time: string;
  durationMin: number;
  capacity: number;
  category: Category;
  place: Shift['place'];
  instructions: string;
  quorum: boolean;
}


export interface NewMicroTask {
  title: string;
  text: string;
  minutes: number;
  answersNeeded: number;
  deadline: string | null;
}

export interface CoordMicroTask {
  id: string;
  title: string;
  text: string;
  minutes: number;
  answersNeeded: number;
  deadline: string | null;
  active: boolean;
  pending: number;
  accepted: number;
  createdAt: string;
}


export type OrgStatus = 'pending' | 'verified' | 'rejected';

export interface OrgApplicationForm {
  name: string;
  inn?: string;
  address: string;
  districtId?: string;
  contactName: string;
  contactPhone: string;
  signName?: string;
  signPosition?: string;
  seal?: File;
  signature?: File;
}

interface OrgCard {
  id: string;
  name: string;
  status: OrgStatus;
  rejectReason: string | null;
  inn: string | null;
  address: string;
  districtId: string | null;
  contactName: string;
  contactPhone: string;
  signName: string | null;
  signPosition: string | null;
  hasSeal: boolean;
  hasSignature: boolean;
  createdAt: string;
}

export interface OrgApplication extends OrgCard {
  role: 'owner' | 'coordinator';
}

export interface OperatorOrg extends OrgCard {
  createdByName: string | null;
  verifiedAt: string | null;
}

export interface VerifyOrg {
  lat: number;
  lon: number;
  districtId?: string;
}

export interface UrgentCall {
  what: string;
  where: string;
  startInMin: 15 | 30 | 45 | 60;
  people: number;
}

export interface UrgentCallStatus {
  id: string;
  shiftId: string;
  what: string;
  people: number;
  reached: number;
  responses: { name: string; at: string }[];
}

export interface ReviewItem {
  id: string;
  authorName: string;
  minutes: number;
  task: string;
  answer: string;
}

export interface Metrics {
  periodLabel: string;
  hours: number;
  participants: number;
  returnedShare: number;
  funnel: { label: string; value: number; note: string }[];
  orgs: { name: string; attendance: number; hours: number }[];
}

export interface OrgAccess {
  orgName: string;
  shiftsThisMonth: number;
  coordinators: { id: string; name: string; owner: boolean; me: boolean; revoked: boolean }[];
  invite: { link: string; expiresAt: string } | null;
}

export type MessageAudience = 'all' | 'waiting' | 'came';

export interface Audience {
  key: MessageAudience;
  names: string[];
}

export interface CoordinatorHome {
  next: { shift: Shift; going: number } | null;
  shifts: Shift[];
}
