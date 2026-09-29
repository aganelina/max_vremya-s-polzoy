import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api';
import type { OrgApplication, OrgApplicationForm } from '@/api/types';
import { errorCode } from '@/api/errors';
import { errorText } from '@/lib/errors';
import { dayMonth } from '@/lib/format';
import { Chips, DemoBadge, ErrorState, FieldGroup, Footer, Hero, HeroTitle, LinkButton, Loading, PrimaryButton, Screen, Section, Sticker, Strip, TextField } from '@/ui';

type Field = 'name' | 'inn' | 'address' | 'contactName' | 'contactPhone' | 'signName' | 'signPosition' | 'seal' | 'signature';
type Draft = Omit<OrgApplicationForm, 'seal' | 'signature'> & { seal: File | null; signature: File | null };

const EMPTY: Draft = { name: '', inn: '', address: '', districtId: undefined, contactName: '', contactPhone: '', signName: '', signPosition: '', seal: null, signature: null };
const MAX_IMAGE = 1024 * 1024;
const INN = /^\d{10}(\d{2})?$/;
const PHONE = /^\+?[\d\s()-]{5,20}$/;

const FIELD_OF: Record<string, Field> = {
  invalid_name: 'name',
  invalid_inn: 'inn',
  invalid_address: 'address',
  invalid_contact_name: 'contactName',
  invalid_phone: 'contactPhone',
  invalid_sign_name: 'signName',
  invalid_sign_position: 'signPosition',
  seal_too_large: 'seal',
  seal_not_png: 'seal',
  signature_too_large: 'signature',
  signature_not_png: 'signature',
};

function validate(d: Draft): Partial<Record<Field, string>> {
  const e: Partial<Record<Field, string>> = {};
  if (!d.name.trim()) e.name = 'Добавь название: его увидят студенты.';
  if (d.inn?.trim() && !INN.test(d.inn.trim())) e.inn = 'ИНН — 10 или 12 цифр.';
  if (!d.address.trim()) e.address = 'Добавь адрес: от него считаем дорогу.';
  if (!d.contactName.trim()) e.contactName = 'Кто ответит оператору?';
  if (!PHONE.test(d.contactPhone.trim())) e.contactPhone = 'Проверь телефон: цифры, пробелы, скобки и дефисы.';
  for (const k of ['seal', 'signature'] as const) {
    const f = d[k];
    if (f && f.size > MAX_IMAGE) e[k] = 'Файл больше 1 МБ.';
    else if (f && f.type && f.type !== 'image/png') e[k] = 'Нужен PNG.';
  }
  return e;
}

export function OrgApplyScreen() {
  const navigate = useNavigate();
  const mine = useQuery({ queryKey: ['orgs-mine'], queryFn: api.myOrgs });
  const dict = useQuery({ queryKey: ['dictionaries'], queryFn: api.dictionaries, staleTime: Infinity });
  const [again, setAgain] = useState(false);

  const back = { label: '‹ Профиль', onClick: () => navigate('/profile') };
  if (mine.isPending) return <Screen><Hero nav={back} /><Loading /></Screen>;
  if (mine.isError) return <Screen><Hero nav={back} /><ErrorState error={mine.error} onRetry={() => mine.refetch()} /></Screen>;

  const own = mine.data.filter((o) => o.role === 'owner');
  const pending = own.find((o) => o.status === 'pending');
  const verified = mine.data.find((o) => o.status === 'verified');
  const rejected = own.find((o) => o.status === 'rejected');

  if (pending) return <Status org={pending} back={back} />;
  if (verified && !again) return <Status org={verified} back={back} onAgain={() => setAgain(true)} />;
  if (rejected && !again) return <Status org={rejected} back={back} onAgain={() => setAgain(true)} />;
  return <ApplyForm back={back} districts={dict.data?.districts ?? []} from={rejected} />;
}

function Status({ org, back, onAgain }: { org: OrgApplication; back: { label: string; onClick: () => void }; onAgain?: () => void }) {
  const navigate = useNavigate();
  const view = {
    pending: { tone: 'orange' as const, caption: `Заявка от ${dayMonth(org.createdAt)} · на проверке`, sticker: 'ждём' },
    verified: { tone: 'blue' as const, caption: 'Организация подключена', sticker: '✓' },
    rejected: { tone: 'ink' as const, caption: 'Заявку отклонили', sticker: '✕' },
  }[org.status];

  return (
    <Screen>
      <Hero
        nav={back}
        tone={view.tone}
        right={<DemoBadge />}
        caption={view.caption}
        strip={<Strip items={[org.address, org.role === 'owner' ? 'ты владелец' : 'ты координатор']} />}
      >
        <HeroTitle text={org.name} sticker={<Sticker white={org.status === 'pending'}>{view.sticker}</Sticker>} />
      </Hero>
      <div className="body">
        {org.status === 'pending' && (
          <Section title="Что дальше" gap={8}>
            <div className="text">Оператор платформы проверит данные вручную, обычно за 1–2 рабочих дня. Результат пришлю в чат MAX.</div>
            <div className="meta">Пока заявка на проверке, публиковать смены и микро-дела нельзя.</div>
          </Section>
        )}
        {org.status === 'verified' && (
          <Section title="Что дальше" gap={8}>
            <div className="text">Можно публиковать смены и микро-дела. У студентов организация отмечена как «проверено».</div>
          </Section>
        )}
        {org.status === 'rejected' && (
          <div className="card card--danger">
            <span className="caps">Причина</span>
            <div className="text">{org.rejectReason || 'Оператор не указал причину.'}</div>
          </div>
        )}
        <Section title="Данные заявки" gap={4}>
          <div>
            {[
              ['Контакт', `${org.contactName} · ${org.contactPhone}`],
              ['ИНН', org.inn ?? 'не указан'],
              ['Подписант', org.signName ? `${org.signName}${org.signPosition ? `, ${org.signPosition}` : ''}` : 'не указан'],
              ['Подпись и печать', [org.hasSignature && 'подпись', org.hasSeal && 'печать'].filter(Boolean).join(', ') || 'не загружены'],
            ].map(([k, v]) => (
              <div key={k} className="list-row" style={{ alignItems: 'baseline' }}>
                <span className="meta">{k}</span>
                <span style={{ textAlign: 'right', fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
      <div className="spacer" />
      <Footer>
        {org.status === 'verified' && <PrimaryButton onClick={() => navigate('/coord')}>Открыть кабинет</PrimaryButton>}
        {org.status === 'rejected' && onAgain && <PrimaryButton onClick={onAgain}>Подать заново</PrimaryButton>}
        {org.status === 'verified' && onAgain && <LinkButton onClick={onAgain}>Подключить ещё одну организацию</LinkButton>}
      </Footer>
    </Screen>
  );
}

function ImageField({ label, file, error, onChange }: { label: string; file: File | null; error?: string; onChange: (f: File | null) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="stack stack--4">
      <div className="list-row" style={{ padding: '4px 0' }}>
        <span className="stack" style={{ gap: 2, minWidth: 0 }}>
          <span className="list-row__title">{label}</span>
          <span className="meta" style={{ overflowWrap: 'anywhere' }}>{file ? file.name : 'PNG до 1 МБ, необязательно'}</span>
        </span>
        {file ? (
          <LinkButton tone="danger" style={{ fontSize: 14 }} onClick={() => onChange(null)}>
            Убрать
          </LinkButton>
        ) : (
          <LinkButton style={{ fontSize: 14 }} onClick={() => ref.current?.click()}>
            Загрузить
          </LinkButton>
        )}
        <input
          ref={ref}
          type="file"
          accept="image/png"
          hidden
          onChange={(e) => {
            onChange(e.target.files?.[0] ?? null);
            e.target.value = '';
          }}
        />
      </div>
      {error && (
        <div className="error-text" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

function ApplyForm({ back, districts, from }: { back: { label: string; onClick: () => void }; districts: { id: string; name: string }[]; from?: OrgApplication }) {
  const qc = useQueryClient();
  const [d, setD] = useState<Draft>(() =>
    from
      ? {
          ...EMPTY,
          name: from.name,
          inn: from.inn ?? '',
          address: from.address,
          districtId: from.districtId ?? undefined,
          contactName: from.contactName,
          contactPhone: from.contactPhone,
          signName: from.signName ?? '',
          signPosition: from.signPosition ?? '',
        }
      : EMPTY,
  );
  const [errs, setErrs] = useState<Partial<Record<Field, string>>>({});
  const apply = useMutation({
    mutationFn: () =>
      api.applyOrg({
        ...d,
        name: d.name.trim(),
        inn: d.inn?.trim() || undefined,
        address: d.address.trim(),
        contactName: d.contactName.trim(),
        contactPhone: d.contactPhone.trim(),
        signName: d.signName?.trim() || undefined,
        signPosition: d.signPosition?.trim() || undefined,
        seal: d.seal ?? undefined,
        signature: d.signature ?? undefined,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['orgs-mine'] }),
    onError: (e) => {
      const field = FIELD_OF[errorCode(e) ?? ''];
      if (field) setErrs({ [field]: errorText(e, 'Проверь поле.') });
    },
  });
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => {
    setD((s) => ({ ...s, [k]: v }));
    setErrs((e) => ({ ...e, [k]: undefined }));
    apply.reset();
  };
  const submit = () => {
    const e = validate(d);
    setErrs(e);
    if (Object.keys(e).length === 0) apply.mutate();
  };
  const fieldErr = FIELD_OF[errorCode(apply.error) ?? ''];

  return (
    <Screen>
      <Hero nav={back} right={<DemoBadge />} caption="Заявка организации" strip={<Strip items={['Проверка вручную', 'обычно 1–2 дня']} />}>
        <div style={{ opacity: d.name ? 1 : 0.5 }}>
          <HeroTitle text={d.name || 'Название организации'} />
        </div>
      </Hero>

      <div className="body body--tight">
        <div className="text">Подключи фонд, приют или библиотеку: после проверки сможешь публиковать смены и микро-дела, а часы студентов попадут в справку с подписью организации.</div>
        <TextField label="Название" value={d.name} onChange={(v) => set('name', v)} maxLength={200} placeholder="Как вас знают в городе" error={errs.name} />
        <TextField label="ИНН" hint="необязательно" type="text" value={d.inn ?? ''} onChange={(v) => set('inn', v.replace(/\D/g, '').slice(0, 12))} placeholder="10 или 12 цифр" error={errs.inn} />
        <TextField label="Адрес" value={d.address} onChange={(v) => set('address', v)} maxLength={300} placeholder="Улица, дом — сюда придут студенты" error={errs.address} />
        {districts.length > 0 && (
          <FieldGroup label="Район" hint="для подбора рядом с домом">
            <Chips<string>
              label="Район"
              allowNone
              options={districts.map((x) => ({ value: x.id, label: x.name }))}
              value={d.districtId ?? null}
              onChange={(v) => set('districtId', v ?? undefined)}
            />
          </FieldGroup>
        )}
        <div className="grid-2">
          <TextField label="Контактное лицо" value={d.contactName} onChange={(v) => set('contactName', v)} maxLength={200} error={errs.contactName} />
          <TextField label="Телефон" type="tel" value={d.contactPhone} onChange={(v) => set('contactPhone', v)} placeholder="+7 …" error={errs.contactPhone} />
        </div>
        <div className="meta" style={{ marginTop: -16 }}>
          Контакты доступны оператору платформы и членам вашей организации. Остальным участникам их не показываем.
        </div>

        <Section title="Для справок студентов" gap={8}>
          <div className="meta">Строка «организация, должность, ФИО» и изображения подписи и печати попадут в PDF-справку о часах.</div>
          <div className="grid-2">
            <TextField label="ФИО подписанта" value={d.signName ?? ''} onChange={(v) => set('signName', v)} maxLength={200} error={errs.signName} />
            <TextField label="Должность" value={d.signPosition ?? ''} onChange={(v) => set('signPosition', v)} maxLength={200} error={errs.signPosition} />
          </div>
          <ImageField label="Подпись" file={d.signature} error={errs.signature} onChange={(f) => set('signature', f)} />
          <ImageField label="Печать" file={d.seal} error={errs.seal} onChange={(f) => set('seal', f)} />
        </Section>
      </div>

      <div className="spacer" />
      <Footer>
        {apply.isError && !fieldErr && <div className="error-text center">{errorText(apply.error, 'Не получилось отправить заявку. Попробуй ещё раз.')}</div>}
        {Object.values(errs).some(Boolean) && <div className="error-text center">Проверь отмеченные поля.</div>}
        <PrimaryButton disabled={apply.isPending} onClick={submit}>
          {apply.isPending ? 'Отправляю…' : 'Отправить на проверку'}
        </PrimaryButton>
      </Footer>
    </Screen>
  );
}
