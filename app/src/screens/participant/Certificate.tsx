import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api';
import { errorText } from '@/lib/errors';
import type { CertPeriod } from '@/api/types';
import { MaxDownloadError, SAVED_LABEL, saveFile } from '@/lib/download';
import { DEALS, ddmm, hoursStr, plural } from '@/lib/format';
import { DemoBadge, ErrorState, Footer, Hero, HeroBig, LinkButton, Loading, PrimaryButton, Screen, Segmented, Strip } from '@/ui';

const COLS = '48px minmax(0,1fr) 36px';

export function CertificateScreen() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<CertPeriod>('semester');
  const q = useQuery({ queryKey: ['certificate', period], queryFn: () => api.certificate(period) });

  const pdf = useMutation({
    mutationFn: () =>
      saveFile({
        name: `spravka-${c?.verifyCode ?? period}.pdf`,
        fetchLink: () => api.certificateLink(period),
        fetchBlob: () => api.certificatePdf(period),
      }),
  });
  const share = useMutation({ mutationFn: () => api.shareCertificate(period) });

  const changePeriod = (p: CertPeriod) => {
    setPeriod(p);
    pdf.reset();
    share.reset();
  };

  const c = q.data;
  const n = c?.rows.length ?? 0;

  return (
    <Screen>
      <Hero
        nav={{ label: '‹ Профиль', onClick: () => navigate('/profile') }}
        right={<DemoBadge />}
        caption={`Справка о часах · ${c?.periodLabel ?? '…'}`}
        strip={<Strip items={[c ? `${n} ${plural(n, DEALS)}` : '…', 'каждое подтверждено QR на месте']} />}
      >
        <HeroBig value={c ? hoursStr(c.total) : '…'} unit="ч" />
      </Hero>

      <div className="body body--tight">
        <Segmented<CertPeriod>
          label="Период"
          options={[
            { value: 'semester', label: 'Этот семестр' },
            { value: 'all', label: 'Всё время' },
          ]}
          value={period}
          onChange={changePeriod}
        />

        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <article
            style={{
              background: 'var(--white)',
              border: '2px solid var(--ink)',
              borderRadius: 4,
              padding: '20px 16px',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              boxShadow: '4px 4px 0 var(--ink)',
            }}
          >
            <div className="row row--between" style={{ fontSize: 12, lineHeight: '16px', color: 'var(--muted)', gap: 8 }}>
              <span>Время с пользой</span>
              <span>сформирована {new Date(c!.generatedAt).toLocaleDateString('ru-RU')}</span>
            </div>
            <div className="text">
              Участник: <b>{c!.participant.firstName}</b>, {c!.participant.university}
            </div>
            <div role="table" aria-label="Засчитанные дела">
              <div
                role="row"
                style={{
                  display: 'grid',
                  gridTemplateColumns: COLS,
                  gap: 8,
                  padding: '8px 0',
                  borderBottom: '2px solid var(--ink)',
                  fontSize: 12,
                  lineHeight: '16px',
                  fontWeight: 700,
                  letterSpacing: 1,
                  textTransform: 'uppercase',
                }}
              >
                <span role="columnheader">Дата</span>
                <span role="columnheader">Дело</span>
                <span role="columnheader" style={{ textAlign: 'right' }}>
                  Ч
                </span>
              </div>
              {c!.rows.map((r, i) => (
                <div
                  key={i}
                  role="row"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: COLS,
                    gap: 8,
                    padding: '8px 0',
                    borderBottom: '1.5px solid var(--line)',
                    fontSize: 14,
                    lineHeight: '20px',
                    alignItems: 'baseline',
                  }}
                >
                  <span role="cell" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {ddmm(r.date)}
                  </span>
                  <span role="cell" style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontWeight: 600, textWrap: 'pretty' }}>{r.title}</span>
                    <span style={{ color: 'var(--muted)' }}>{r.org}</span>
                  </span>
                  <span role="cell" style={{ textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                    {hoursStr(r.hours)}
                  </span>
                </div>
              ))}
              {n === 0 && <div className="meta" style={{ padding: '8px 0' }}>За этот период засчитанных дел пока нет.</div>}
            </div>
            <div className="row row--between">
              <span style={{ fontSize: 16, fontWeight: 600 }}>Итого</span>
              <span style={{ font: '800 24px/28px var(--font-display)' }}>{hoursStr(c!.total)} ч</span>
            </div>
            <div style={{ fontSize: 12, lineHeight: '16px', color: 'var(--muted)' }}>
              Подлинность: {c!.verifyUrl} · код {c!.verifyCode}
            </div>
          </article>
        )}
        <div className="meta">В справку попадают только засчитанные часы. Банк часов и микро-дела на проверке сюда не входят.</div>
      </div>

      <div className="spacer" />
      <Footer>
        <PrimaryButton disabled={!c || pdf.isPending} onClick={() => pdf.mutate()}>
          {pdf.isPending ? 'Готовлю PDF…' : pdf.isSuccess ? SAVED_LABEL[pdf.data] : 'Скачать PDF'}
        </PrimaryButton>
        {pdf.isSuccess && <div className="meta center">Файла не видно? Отправь справку в чат MAX — кнопка ниже.</div>}
        {pdf.isError && (
          <div className="error-text center">
            {pdf.error instanceof MaxDownloadError
              ? 'MAX не смог скачать файл. Отправь PDF в чат MAX — так надёжнее.'
              : errorText(pdf.error, 'Не получилось собрать PDF. Попробуй ещё раз или отправь справку в чат MAX.')}
          </div>
        )}
        <LinkButton disabled={!c || share.isPending || share.isSuccess} onClick={() => share.mutate()}>
          {share.isSuccess ? 'Отправлено в чат ✓' : 'Отправить в чат MAX'}
        </LinkButton>
        {share.isError && <div className="error-text center">{errorText(share.error, 'Не получилось отправить. Попробуй ещё раз.')}</div>}
      </Footer>
    </Screen>
  );
}
