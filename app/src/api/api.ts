import type * as T from './types';

export interface Api {
  me(): Promise<T.Me>;
  dictionaries(): Promise<T.Dictionaries>;
  consent(): Promise<T.Me>;
  onboard(p: { universityId: string; districtId: string }): Promise<T.Me>;
  updateProfile(p: T.ProfilePatch): Promise<T.Me>;
  exportData(): Promise<void>;
  deleteProfile(): Promise<void>;

  setWeeklySearch(p: T.SearchParams | null): Promise<void>;
  events(date: string): Promise<T.Deal[]>;
  searchPreview(p: T.SearchParams): Promise<T.SearchPreview>;
  search(p: T.SearchParams): Promise<T.SearchResult>;
  deal(id: string, from?: T.Origin): Promise<T.Deal>;
  book(dealId: string, opts?: { companyId?: string; inviteToken?: string }): Promise<T.Booking>;
  cancelBooking(bookingId: string): Promise<void>;
  inviteLink(dealId: string): Promise<{ link: string }>;
  friendInvite(token: string): Promise<T.FriendInvite>;
  addToCalendar(dealId: string): Promise<{ icsUrl: string }>;
  transferLink(bookingId: string): Promise<{ link: string }>;
  myDeals(): Promise<T.MyDeals>;

  createCompany(date: string): Promise<T.Company>;
  joinCompany(token: string): Promise<T.Company>;
  company(id: string): Promise<T.Company>;
  setCompanyWindow(id: string, window: { from: string; to: string } | null): Promise<T.Company>;
  remind(companyId: string, memberId: string): Promise<void>;
  pickCompanyDeal(companyId: string, dealId: string | null): Promise<T.Company>;

  checkIn(bookingId: string, code: string): Promise<T.CheckInResult>;
  undoCheckIn(bookingId: string): Promise<void>;

  schedule(): Promise<T.Schedule>;
  uploadSchedule(file: File): Promise<T.Schedule>;

  nextMicroTask(skipId?: string): Promise<T.MicroTask>;
  takeMicroTask(id: string): Promise<T.MicroTask>;
  submitMicroTask(id: string, answer: string): Promise<T.MicroTask>;
  releaseMicroTask(id: string): Promise<void>;

  hourBank(): Promise<T.HourBank>;
  respondHelp(id: string, on: boolean): Promise<T.HourBank>;
  askHelp(p: { text: string; hours: number; when?: string }): Promise<T.HourBank>;
  confirmHelp(id: string): Promise<T.HourBank>;

  mentorship(): Promise<T.Mentorship>;
  setMentorAccepting(on: boolean): Promise<T.Mentorship>;
  acceptMentorRequest(id: string): Promise<T.Mentorship>;
  declineMentorRequest(id: string): Promise<T.Mentorship>;

  route(p?: T.SearchParams): Promise<T.Route>;
  bookRoute(dealIds: string[]): Promise<void>;

  seatTransfer(token: string): Promise<T.SeatTransfer>;
  claimSeat(token: string): Promise<T.Booking>;

  certificate(period: T.CertPeriod): Promise<T.Certificate>;
  certificatePdf(period: T.CertPeriod): Promise<Blob>;
  certificateLink(period: T.CertPeriod): Promise<T.FileLink>;
  shareCertificate(period: T.CertPeriod): Promise<void>;

  coordHome(): Promise<T.CoordinatorHome>;
  attendance(shiftId: string): Promise<T.ShiftAttendance>;
  markManual(shiftId: string, participantId: string, on: boolean): Promise<T.ShiftAttendance>;
  checkInCode(shiftId: string): Promise<T.CheckInCode>;
  cancelShift(shiftId: string): Promise<void>;
  createShift(p: T.NewShift): Promise<T.Shift>;
  urgentCall(p: T.UrgentCall): Promise<T.UrgentCallStatus>;
  urgentStatus(id: string): Promise<T.UrgentCallStatus>;
  reviewQueue(): Promise<{ items: T.ReviewItem[]; acceptedToday: number; returnedToday: number }>;
  review(id: string, verdict: 'accept' | 'return', note?: string): Promise<void>;
  undoReview(id: string): Promise<void>;
  metrics(): Promise<T.Metrics>;
  access(): Promise<T.OrgAccess>;
  exportAttendance(p: { from: string; to: string }): Promise<Blob>;
  attendanceLink(p: { from: string; to: string }): Promise<T.FileLink>;
  inviteCoordinator(): Promise<T.OrgAccess>;
  setCoordinatorRevoked(id: string, revoked: boolean): Promise<T.OrgAccess>;
  transferOwnership(memberId: string): Promise<T.OrgAccess>;
  audiences(shiftId: string): Promise<T.Audience[]>;
  messageParticipants(shiftId: string, p: { audience: T.MessageAudience; text: string }): Promise<{ sent: number }>;
  coordMicroTasks(): Promise<T.CoordMicroTask[]>;
  createMicroTask(p: T.NewMicroTask): Promise<T.CoordMicroTask>;
  setMicroTaskActive(id: string, active: boolean): Promise<T.CoordMicroTask>;

  applyOrg(p: T.OrgApplicationForm): Promise<T.OrgApplication>;
  myOrgs(): Promise<T.OrgApplication[]>;

  operatorOrgs(status?: T.OrgStatus): Promise<T.OperatorOrg[]>;
  operatorOrgImage(id: string, kind: 'seal' | 'signature'): Promise<Blob>;
  verifyOrg(id: string, p: T.VerifyOrg): Promise<T.OperatorOrg>;
  rejectOrg(id: string, reason: string): Promise<T.OperatorOrg>;
  operatorMetrics(): Promise<T.Metrics>;
}
