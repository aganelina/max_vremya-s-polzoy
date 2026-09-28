export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
    this.name = 'ApiError';
  }
}

export function errorCode(e: unknown): string | null {
  if (e instanceof ApiError) return e.code;
  if (e instanceof TypeError) return 'network';
  return null;
}

export const isApiError = (e: unknown, ...codes: string[]): e is ApiError => e instanceof ApiError && (codes.length === 0 || codes.includes(e.code));
