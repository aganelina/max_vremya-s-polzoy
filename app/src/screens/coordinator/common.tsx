import QRCode from 'qrcode';
import { useNavigate } from 'react-router-dom';
import { DemoBadge } from '@/ui';
import '@/styles/coordinator.css';

export function CoordBadge() {
  return <DemoBadge role="КООРДИНАТОР" />;
}

export function useCabinetNav() {
  const navigate = useNavigate();
  return { label: '‹ Кабинет', onClick: () => navigate('/coord') };
}

export { clean } from '@/lib/format';

const DATIVE = ['', 'Одному', 'Двоим', 'Троим', 'Четверым', 'Пятерым', 'Шестерым', 'Семерым', 'Восьмерым', 'Девятерым', 'Десятерым'];

export const toBooked = (n: number) => (n >= 1 && n <= 10 ? `${DATIVE[n]} записавшимся` : `Всем записавшимся (${n})`);

export { downloadBlob } from '@/lib/download';

export function QrMark({ payload, size = 200 }: { payload: string; size?: number }) {
  const qr = QRCode.create(payload, { errorCorrectionLevel: 'M' });
  const n = qr.modules.size;
  const cells: [number, number][] = [];
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (qr.modules.get(x, y)) cells.push([x, y]);
  return (
    <svg width={size} height={size} viewBox={`-2 -2 ${n + 4} ${n + 4}`} role="img" aria-label="QR-код смены" style={{ background: '#fff', borderRadius: 16 }}>
      <path fill="var(--ink)" d={cells.map(([x, y]) => `M${x} ${y}h1v1h-1z`).join('')} />
    </svg>
  );
}
