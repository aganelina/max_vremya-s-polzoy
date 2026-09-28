import { DEMO_ACTIVE } from '@/api';

export function UniversityNotice({ universityId }: { universityId: string | null }) {
  if (universityId !== 'u6') return null;
  return <div className="meta" role="status">
    Твой вуз пока не поддерживается. Для расчёта дороги используем координаты центра Казани, поэтому время в пути приблизительное.
    {DEMO_ACTIVE && ' В демо время в пути задано для примера.'}
  </div>;
}
