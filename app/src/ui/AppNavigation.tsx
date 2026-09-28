import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import type { Me } from '@/api/types';
import { DEMO_ACTIVE } from '@/api';

export function AppNavigation({ me }: { me: Me }) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [pathname]);
  const link = (to: string, label: string) => <NavLink key={to} to={to} end>{label}</NavLink>;
  return <nav className="app-nav" aria-label="Разделы приложения">
    <div className="app-nav__brand">Время<br />с пользой</div>
    <div className="app-nav__primary">
      {link('/', 'Главная')}{link('/my', 'Мои дела')}{link('/profile', 'Профиль')}
    </div>
    {DEMO_ACTIVE && <>
      <button className="app-nav__toggle" type="button" aria-expanded={open} aria-controls="app-sections" onClick={() => setOpen(!open)}>
        {open ? 'Скрыть разделы ↑' : 'Все разделы ↓'}
      </button>
      <div id="app-sections" className={`app-nav__more${open ? ' app-nav__more--open' : ''}`}>
        {link('/demo', 'Обзор разделов')}
        <div className="app-nav__group" role="group" aria-label="Участник">
          <span className="caps app-nav__group-label">Участник</span>
          {link('/search', 'Подобрать дело')}{link('/calendar', 'Афиша на 6 недель')}
          {link('/micro', 'Помочь из дома')}{link('/windows', 'Свободные окна')}
          {link('/route', 'Маршрут из дел')}{link('/bank', 'Банк часов')}
          {link('/mentor', 'Наставничество')}{link('/certificate', 'Справка о часах')}
          {link('/orgs/apply', 'Подключить организацию')}{link('/privacy', 'Политика данных')}
        </div>
        {me.roles.coordinator && <div className="app-nav__group" role="group" aria-label="Куратор">
          <span className="caps app-nav__group-label">Куратор</span>
          {link('/coord', 'Мои смены')}{link('/coord/shifts/new', 'Новая смена')}
          {link('/coord/urgent', 'Срочный сбор')}{link('/coord/reviews', 'Проверка ответов')}
          {link('/coord/micro', 'Микро-дела')}{link('/coord/metrics', 'Метрики')}{link('/coord/access', 'Доступы')}
        </div>}
        {me.roles.operator && <div className="app-nav__group" role="group" aria-label="Оператор">
          <span className="caps app-nav__group-label">Оператор</span>
          {link('/operator/orgs', 'Заявки организаций')}{link('/operator/metrics', 'Метрики пилота')}
        </div>}
      </div>
    </>}
  </nav>;
}
