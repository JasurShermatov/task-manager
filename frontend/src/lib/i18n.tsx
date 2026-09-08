import React, { createContext, useContext, useMemo } from 'react'
import { useLocalStorage } from './hooks'

export type Lang = 'uz' | 'ru' | 'en'

const uz = {
  app: 'SAFF', app_sub: 'VAZIFALAR', login: 'Kirish', logout: 'Chiqish', login_field: 'Login', password: 'Parol', login_btn: 'Kirish',
  login_err: 'Login yoki parol noto\'g\'ri', loading: 'Yuklanmoqda…', empty: 'Hech narsa yo\'q', error: 'Xato', retry: 'Qayta',
  save: 'Saqlash', cancel: 'Bekor', close: 'Yopish', add: 'Qo\'shish', edit: 'Tahrirlash', delete: 'O\'chirish', search: 'Qidirish…', all: 'Barchasi',
  yes: 'Ha', no: 'Yo\'q', required: 'majburiy', optional: 'ixtiyoriy', today: 'Bugun', view: 'ko\'rish', of: 'dan',
  // nav
  nav_tasks: 'Vazifalar', nav_table: 'Jadval', nav_projects: 'Loyihalar', nav_reports: 'Hisobot', nav_templates: 'Shablonlar', nav_types: 'Ish turlari',
  nav_users: 'Foydalanuvchilar', nav_telegram: 'Telegram bot', nav_bulk: 'Ommaviy yaratish', grp_work: 'Ish', grp_settings: 'Sozlash',
  sub_tasks: 'kanban · doska', sub_table: 'ro\'yxat · CSV', sub_projects: 'obyekt va joylar', sub_reports: 'KPI · kesimlar',
  sub_templates: 'tayyor vazifalar', sub_types: 'checklist · foto', sub_users: 'rollar · doiralar', sub_telegram: 'bog\'lash', sub_bulk: 'qavat ko\'chirish',
  // statuses
  st_plan: 'Rejada', st_progress: 'Jarayonda', st_review: 'Tekshiruvda', st_done: 'Bajarildi', st_blocked: 'Bloklangan', st_cancelled: 'Bekor qilingan',
  pr_low: 'Past', pr_normal: 'O\'rta', pr_high: 'Yuqori', priority: 'Muhimlik',
  // kpi
  kpi_open: 'Ochiq', kpi_overdue: 'Kechikkan', kpi_blocked: 'Bloklangan', kpi_review: 'Tekshiruvda', kpi_ontime: 'Muddatida yopilgan',
  kpi_open_sub: 'ustunda', kpi_oldest: 'eng eskisi {d} kun', kpi_month: 'jami {n} bajarildi', kpi_material: '{n} tasi material',
  // filters
  f_project: 'Loyiha', f_location: 'Joy', f_type: 'Tur', f_assignee: 'Mas\'ul', f_priority: 'Muhimlik', f_overdue: 'Kechikkan', f_blocked: 'Bloklangan', f_mine: 'Mening vazifalarim',
  f_status: 'Holat', f_reviewer: 'Tekshiruvchi', f_clear: 'Tozalash', f_export: 'CSV eksport', new_task: '+ Vazifa', board: 'Doska', table: 'Jadval',
  // card
  c_checklist: 'Checklist', c_photos: 'foto', c_overdue: '{d} kun kechikdi', c_review_days: 'Tekshiruvda {d} kun', c_returned: 'Qaytarilgan · {n}-marta',
  c_waiting: '{codes} kutilmoqda', c_accepted: 'Qabul qilindi', c_ontime: 'muddatida', c_blocked_days: '{d} kun', c_progress: 'Jarayon',
  // drawer tabs
  tab_general: 'Umumiy', tab_checklist: 'Checklist', tab_daily: 'Kunlik hisobot', tab_files: 'Foto / Fayl', tab_history: 'Tarix', tab_comments: 'Izohlar',
  d_status: 'Holat', d_type: 'Ish turi', d_assignee: 'Bajaruvchi', d_reviewer: 'Tekshiruvchi', d_plan: 'Reja', d_fact: 'Fakt', d_qty: 'Hajm', d_desc: 'Tavsif',
  d_deps: 'Bog\'liqlik', d_dependents: 'Bunga bog\'liq', d_created: 'Yaratilgan', d_days: 'kun', d_ongoing: 'davom etmoqda', d_location: 'Joy', d_crew: 'Brigada',
  d_blocked_since: 'Bloklangan', d_return_count: 'Qaytarilgan', d_no_deps: 'Bog\'liqlik yo\'q', d_add_dep: 'Bog\'liqlik qo\'shish (kod)', d_code: 'Kod',
  // actions
  a_start: 'Boshlash', a_submit: 'Tekshiruvga yuborish', a_accept: 'Qabul qilish', a_return: 'Qaytarish', a_block: 'Bloklash', a_unblock: 'Blokdan chiqarish',
  a_reopen: 'Qayta ochish', a_cancel: 'Bekor qilish', a_delete: 'O\'chirish', a_edit: 'Tahrirlash', a_comment: 'Izoh', a_upload: 'Fayl yuklash',
  a_add_daily: 'Hisobot qo\'shish', a_add_item: 'Band qo\'shish', a_open_web: 'Web',
  // dialogs
  dlg_block_title: 'Vazifani bloklash', dlg_reason: 'Sabab', dlg_note: 'Izoh', dlg_note_req: 'Izoh majburiy', dlg_return_title: 'Qaytarish sababi',
  dlg_date_reason: 'Muddat o\'zgarishi sababi', dlg_confirm_delete: 'Vazifa o\'chirilsinmi? (arxivga o\'tadi)', dlg_confirm_cancel: 'Vazifa bekor qilinsinmi?',
  dlg_reopen_note: 'Qayta ochish izohi (ixtiyoriy)',
  br_material_yoq: 'Material yo\'q', br_hujjat_kutilmoqda: 'Hujjat/chizma kutilmoqda', br_texnika_band: 'Texnika band', br_ishchi_yetmadi: 'Ishchi kuchi yetmadi',
  br_oldingi_ish: 'Oldingi ish tugamagan', br_obhavo: 'Ob-havo', br_qaror_kutilmoqda: 'Qaror kutilmoqda', br_boshqa: 'Boshqa',
  // checklist
  ck_required_missing: 'Majburiy bandlar bajarilmagan', ck_done_of: '{a}/{b} bajarildi', ck_new: 'Yangi band nomi',
  // daily
  dl_date: 'Sana', dl_qty: 'Hajm', dl_workers: 'Ishchilar', dl_hours: 'Soat', dl_note: 'Izoh', dl_by: 'Kim', dl_dup: 'takror', dl_total: 'Jami {a} / {b} {u} · rejadan {p}%',
  dl_over: 'rejadan oshdi', dl_empty: 'Hali hisobot yo\'q',
  // files
  fl_kind: 'Turi', fl_before: 'Oldin', fl_during: 'Jarayon', fl_after: 'Keyin', fl_document: 'Hujjat', fl_required: 'Majburiy: {k}', fl_missing: 'yo\'q', fl_empty: 'Fayl yo\'q',
  fl_drop: 'Rasm yoki hujjat tanlang', fl_by: 'Yukladi',
  // history
  h_create: 'Yaratildi', h_update: 'O\'zgartirildi', h_start: 'Boshlandi', h_submit_review: 'Tekshiruvga yuborildi', h_accept: 'Qabul qilindi', h_return: 'Qaytarildi',
  h_block: 'Bloklandi', h_unblock: 'Blokdan chiqdi', h_reopen: 'Qayta ochildi', h_cancel: 'Bekor qilindi', h_delete: 'O\'chirildi', h_checklist: 'Checklist',
  h_checklist_add: 'Band qo\'shildi', h_daily_progress: 'Kunlik hisobot', h_attach: 'Fayl yuklandi', h_attachment_delete: 'Fayl o\'chirildi', h_comment: 'Izoh',
  h_dependency_add: 'Bog\'liqlik qo\'shildi', h_dependency_remove: 'Bog\'liqlik olib tashlandi', h_reviewer_reassigned: 'Tekshiruvchi o\'zgardi', h_source: 'manba',
  // create
  cr_title: 'Yangi vazifa', cr_template: 'Shablon', cr_no_template: 'Shablonsiz', cr_name: 'Sarlavha', cr_type: 'Ish turi', cr_project: 'Loyiha', cr_location: 'Joy',
  cr_assignee: 'Bajaruvchi', cr_reviewer: 'Tekshiruvchi', cr_start: 'Boshlanish', cr_end: 'Tugash', cr_qty: 'Reja hajmi', cr_unit: 'Birlik', cr_desc: 'Tavsif',
  cr_checklist: 'Checklist', cr_deps: 'Bog\'liq vazifalar (kodlar, vergul bilan)', cr_create: 'Yaratish', cr_voice: 'Ovoz bilan', cr_voice_stop: 'To\'xtatish',
  cr_voice_hint: 'Gapiring: kimga, nima, qachongacha. Tugagach To\'xtatish.', cr_voice_processing: 'Tahlil qilinyapti…', cr_voice_off: 'Ovozli kiritish sozlanmagan',
  cr_voice_result: 'Ovozdan tanildi', cr_pick_assignee: 'Bajaruvchini tanlang', cr_self_review: 'Bajaruvchi va tekshiruvchi bir odam bo\'lishi mumkin emas',
  cr_crew: 'Brigada (kishi)', cr_type_hint: 'Ish turi checklist va majburiy fotolarni belgilaydi',
  // table
  t_code: 'Kod', t_title: 'Sarlavha', t_location: 'Joy', t_status: 'Holat', t_assignee: 'Mas\'ul', t_end: 'Muddat', t_progress: 'Progress', t_priority: 'Muhimlik', t_reviewer: 'Tekshiruvchi',
  t_page: '{a}–{b} / {n}', t_prev: 'Oldingi', t_next: 'Keyingi',
  // reports
  r_title: 'Hisobot', r_period: 'Davr', r_from: 'dan', r_to: 'gacha', r_by_status: 'Holat bo\'yicha', r_block_reasons: 'Bloklash sabablari', r_staff: 'Xodimlar kesimi',
  r_daily: 'Oxirgi 14 kunda bajarilgan', r_name: 'Xodim', r_total: 'Jami', r_done: 'Bajarildi', r_ontime: 'Muddatida %', r_return: 'Qaytarish %', r_overdue: 'Kechikkan', r_open: 'Ochiq',
  r_avg: 'O\'rtacha bajarish', r_days: 'kun', r_reviewers: 'Tekshiruvchilar', r_queue: 'Navbat', r_count: 'soni', r_block_days: 'kun', r_hist: 'jami holatlar',
  r_overdue_assignee: 'bajaruvchi', r_overdue_reviewer: 'tekshiruvchi',
  // settings: types
  ty_title: 'Ish turlari', ty_name: 'Nom', ty_group: 'Guruh', ty_days: 'Davomiylik (kun)', ty_evidence: 'Majburiy foto', ty_checklist: 'Standart checklist', ty_new: 'Yangi ish turi',
  ty_archive: 'Arxivlash', ty_restore: 'Tiklash', ty_archived: 'arxivda', ty_hint: 'Ish turi o\'chirilmaydi — arxivga o\'tadi. Yaratilgan vazifalarga ta\'sir qilmaydi.',
  // templates
  tp_title: 'Shablonlar', tp_name: 'Nom', tp_pattern: 'Sarlavha shabloni', tp_pattern_hint: '{joy} — joy nomi, {sana} — sana', tp_new: 'Yangi shablon', tp_use: 'Vazifa yaratish',
  tp_recurring: 'Takroriy qoidalar', tp_rrule: 'Qoida', tp_daily: 'Har kuni (yakshanbadan tashqari)', tp_weekly: 'Haftalik', tp_days: 'Kunlar', tp_next: 'Keyingi', tp_active: 'Faol',
  // users
  us_title: 'Foydalanuvchilar', us_name: 'F.I.Sh.', us_login: 'Login', us_role: 'Rol', us_scope: 'Doira', us_tg: 'Telegram', us_active: 'Faol', us_blocked: 'Bloklangan',
  us_new: 'Yangi foydalanuvchi', us_phone: 'Telefon', us_lang: 'Til', us_block: 'Bloklash', us_unblock: 'Blokdan chiqarish', us_pw: 'Parol (kamida {n} belgi)', us_scope_system: 'Butun tizim',
  us_scope_project: 'Loyiha', us_scope_location: 'Uchastka (blok)', us_linked: 'ulangan', us_not_linked: 'ulanmagan', us_roles: 'Rollar va ruxsatlar', us_perm: 'Ruxsat',
  us_block_hint: 'Bloklangan xodim o\'chirilmaydi — vazifalari va tarixi qoladi; tekshiruv navbati rahbarga o\'tadi.',
  // telegram
  tg_title: 'Telegram bot', tg_desc: 'Hisobni botga bog\'lang — bildirishnomalar, kunlik hisobot va ovozli vazifalar Telegram orqali ishlaydi.',
  tg_get_code: 'Kod olish', tg_code_hint: 'Botga /start yozing va shu kodni yuboring. Kod 10 daqiqa amal qiladi.', tg_linked: 'Telegram ulangan', tg_unlink: 'Uzish', tg_not_linked: 'Ulanmagan',
  tg_since: 'ulangan', tg_bot: 'Bot',
  // bulk
  bk_title: 'Ommaviy yaratish — qavatni ko\'chirish', bk_source: 'Manba joy', bk_targets: 'Maqsad joylar', bk_step: 'Sana qadami (kun)', bk_assignee: 'Bajaruvchi siyosati',
  bk_keep: 'Manbadagidek', bk_set: 'Hammasiga bitta', bk_deps: 'Bog\'liqlik', bk_deps_none: 'Manbadagidek', bk_deps_chain: 'Ketma-ket zanjir', bk_preview: 'Oldindan ko\'rish',
  bk_run: 'Yaratish ({n})', bk_result: 'Yaratildi: {n} ta', bk_hint: 'Avval oldindan ko\'rish majburiy. 1000 tadan ko\'p bo\'lsa rad etiladi.',
  // projects
  pj_title: 'Loyihalar va joylar', pj_code: 'Kod', pj_name: 'Nom', pj_new: 'Yangi loyiha', pj_locations: 'Joylar (blok → qavat → zona)', pj_add_block: '+ Blok', pj_add_floor: '+ Qavat',
  pj_add_zone: '+ Zona', pj_loc_name: 'Nom',
  // misc
  notif: 'Bildirishnomalar', notif_empty: 'Bildirishnoma yo\'q', mark_read: 'Barchasini o\'qilgan qilish', lang: 'Til', me: 'Men', role: 'Rol',
  err_version: 'Vazifa boshqa foydalanuvchi tomonidan o\'zgartirilgan — yangilandi, qaytadan urinib ko\'ring.',
  err_generic: 'Xato yuz berdi', updated: 'Saqlandi', created_ok: 'Yaratildi', sources: { web: 'web', mobile: 'mobil', bot: 'bot', system: 'tizim' } as Record<string, string>,
  perm_view_only: 'faqat ko\'rish huquqi',
  nav_profile: 'Profil', sub_profile: 'parol · til',
  pf_title: 'Mening profilim', pf_name: 'F.I.Sh.', pf_phone: 'Telefon', pf_lang: 'Interfeys tili',
  pf_login: 'Login', pf_role: 'Rol', pf_scope: 'Doira',
  pf_pw: 'Parolni almashtirish', pf_pw_new: 'Yangi parol (kamida {n} belgi)', pf_pw_confirm: 'Yangi parolni takrorlang',
  pf_pw_mismatch: 'Parollar mos kelmadi', pf_pw_short: 'Kamida {n} belgi', pf_pw_hint: 'Bo\'sh qoldirsangiz parol o\'zgarmaydi',
  pf_saved: 'Profil saqlandi', pf_pw_saved: 'Parol almashtirildi',
  nav_staff: 'Xodimlar', sub_staff: 'jamoa royxati', nav_admin: 'Administratsiya', sub_admin: 'kirish huquqlari - bot',
  grp_admin: 'Boshqaruv',
  sf_title: 'Xodimlar', sf_search: 'Ism yoki rol boyicha...', sf_none: 'Xodim topilmadi',
  sf_open: 'Ochiq', sf_overdue: 'Kechikkan', sf_done: 'Bajarildi', sf_ontime: 'Muddatida',
  sf_contact: 'Aloqa', sf_no_phone: 'telefon kiritilmagan', sf_since: 'Tizimda', sf_last_login: 'Oxirgi kirish',
  sf_never: 'hech qachon', sf_hint: 'Bu yerda faqat jamoa malumoti. Kirish huquqlari - Administratsiya bolimida.',
  sf_pick: 'Xodimni tanlang',
  ad_title: 'Administratsiya', ad_tab_users: 'Kirish huquqlari', ad_tab_roles: 'Rollar', ad_tab_bot: 'Bot',
  ad_tab_panels: 'Rol panellari',
  ad_new_user: '+ Yangi xodim', ad_reset_pw: 'Parolni yangilash', ad_pw_set: 'Yangi parol ornatildi',
  ad_pw_for: '{name} uchun yangi parol', ad_pw_copy: 'Parolni xodimga ayting - u keyin ozi almashtira oladi.',
  ad_bot_title: 'Telegram bot manzili', ad_bot_hint: 'Bot ishga tushganda oz manzilini avtomatik yozadi. Bu yerdan qolda ham ozgartirsa boladi - kodga tegish shart emas.',
  ad_bot_username: 'Bot username (@ siz)', ad_bot_open: 'Botga otish', ad_bot_saved: 'Bot manzili saqlandi',
  ad_bot_empty: 'Hali aniqlanmagan',
  ad_roles_hint: 'Katakchani bosib ruxsatni yoqing yoki ochiring - osha zahoti kuchga kiradi. Administrator roli ozgarmaydi.',
  ad_panels_hint: 'Har rol tizimga oz login-paroli bilan kiradi va shu bolimlarni koradi. Alohida ilova yoq - panel roldan kelib chiqadi.',
  ad_sees: 'koradi', ad_hidden: 'korinmaydi', ad_login_pw: 'Login va parol',
  pg_tasks: 'Vazifalar', pg_flow: 'Ish oqimi', pg_content: 'Checklist, foto, izoh', pg_reports: 'Hisobot', pg_admin: 'Boshqaruv',
  pj_search: 'Obyekt qidirish...', pj_tasks: 'vazifa', pj_open: 'ochiq', pj_late: 'kechikkan', pj_archived: 'Arxivda',
  pj_active: 'Faol', pj_empty_locs: 'Hali joy qoshilmagan', pj_pick: 'Chapdan obyekt tanlang',
  pj_blocks: 'blok', pj_floors: 'qavat', pj_zones: 'zona', pj_add_first: 'Birinchi blokni qoshing',
}

const ru: typeof uz = {
  ...uz,
  app_sub: 'ЗАДАЧИ', login: 'Вход', logout: 'Выйти', login_field: 'Логин', password: 'Пароль', login_btn: 'Войти', login_err: 'Неверный логин или пароль',
  loading: 'Загрузка…', empty: 'Пусто', error: 'Ошибка', retry: 'Повторить', save: 'Сохранить', cancel: 'Отмена', close: 'Закрыть', add: 'Добавить', edit: 'Изменить',
  delete: 'Удалить', search: 'Поиск…', all: 'Все', yes: 'Да', no: 'Нет', required: 'обязательно', optional: 'необязательно', today: 'Сегодня', view: 'просмотр', of: 'из',
  nav_tasks: 'Задачи', nav_table: 'Таблица', nav_projects: 'Проекты', nav_reports: 'Отчёт', nav_templates: 'Шаблоны', nav_types: 'Виды работ', nav_users: 'Пользователи',
  nav_telegram: 'Telegram бот', nav_bulk: 'Массовое создание', grp_work: 'Работа', grp_settings: 'Настройки',
  sub_tasks: 'канбан · доска', sub_table: 'список · CSV', sub_projects: 'объекты и места', sub_reports: 'KPI · срезы', sub_templates: 'готовые задачи', sub_types: 'чеклист · фото',
  sub_users: 'роли · области', sub_telegram: 'привязка', sub_bulk: 'копирование этажа',
  st_plan: 'В плане', st_progress: 'В работе', st_review: 'На проверке', st_done: 'Выполнено', st_blocked: 'Заблокировано', st_cancelled: 'Отменено',
  pr_low: 'Низкий', pr_normal: 'Средний', pr_high: 'Высокий', priority: 'Приоритет',
  kpi_open: 'Открыто', kpi_overdue: 'Просрочено', kpi_blocked: 'Заблокировано', kpi_review: 'На проверке', kpi_ontime: 'Закрыто в срок', kpi_open_sub: 'в колонках',
  kpi_oldest: 'самая старая {d} дн.', kpi_month: 'всего {n} выполнено', kpi_material: '{n} по материалу',
  f_project: 'Проект', f_location: 'Место', f_type: 'Вид', f_assignee: 'Исполнитель', f_priority: 'Приоритет', f_overdue: 'Просроченные', f_blocked: 'Заблокированные',
  f_mine: 'Мои задачи', f_status: 'Статус', f_reviewer: 'Проверяющий', f_clear: 'Сбросить', f_export: 'Экспорт CSV', new_task: '+ Задача', board: 'Доска', table: 'Таблица',
  c_checklist: 'Чеклист', c_photos: 'фото', c_overdue: 'просрочено {d} дн.', c_review_days: 'На проверке {d} дн.', c_returned: 'Возврат · {n}-й раз', c_waiting: 'ожидает {codes}',
  c_accepted: 'Принято', c_ontime: 'в срок', c_blocked_days: '{d} дн.', c_progress: 'Прогресс',
  tab_general: 'Общее', tab_checklist: 'Чеклист', tab_daily: 'Дневной отчёт', tab_files: 'Фото / Файлы', tab_history: 'История', tab_comments: 'Комментарии',
  d_status: 'Статус', d_type: 'Вид работ', d_assignee: 'Исполнитель', d_reviewer: 'Проверяющий', d_plan: 'План', d_fact: 'Факт', d_qty: 'Объём', d_desc: 'Описание',
  d_deps: 'Зависит от', d_dependents: 'От неё зависят', d_created: 'Создана', d_days: 'дн.', d_ongoing: 'в работе', d_location: 'Место', d_crew: 'Бригада',
  d_blocked_since: 'Заблокирована', d_return_count: 'Возвратов', d_no_deps: 'Нет зависимостей', d_add_dep: 'Добавить зависимость (код)', d_code: 'Код',
  a_start: 'Начать', a_submit: 'На проверку', a_accept: 'Принять', a_return: 'Вернуть', a_block: 'Заблокировать', a_unblock: 'Разблокировать', a_reopen: 'Переоткрыть',
  a_cancel: 'Отменить', a_delete: 'Удалить', a_edit: 'Изменить', a_comment: 'Комментарий', a_upload: 'Загрузить файл', a_add_daily: 'Добавить отчёт', a_add_item: 'Добавить пункт', a_open_web: 'Web',
  dlg_block_title: 'Блокировка задачи', dlg_reason: 'Причина', dlg_note: 'Комментарий', dlg_note_req: 'Комментарий обязателен', dlg_return_title: 'Причина возврата',
  dlg_date_reason: 'Причина изменения срока', dlg_confirm_delete: 'Удалить задачу? (уйдёт в архив)', dlg_confirm_cancel: 'Отменить задачу?', dlg_reopen_note: 'Комментарий (необязательно)',
  br_material_yoq: 'Нет материала', br_hujjat_kutilmoqda: 'Ждём документ/чертёж', br_texnika_band: 'Техника занята', br_ishchi_yetmadi: 'Не хватает рабочих',
  br_oldingi_ish: 'Предыдущая работа не завершена', br_obhavo: 'Погода', br_qaror_kutilmoqda: 'Ждём решения', br_boshqa: 'Другое',
  ck_required_missing: 'Обязательные пункты не выполнены', ck_done_of: '{a}/{b} выполнено', ck_new: 'Название пункта',
  dl_date: 'Дата', dl_qty: 'Объём', dl_workers: 'Рабочих', dl_hours: 'Часов', dl_note: 'Комментарий', dl_by: 'Кто', dl_dup: 'дубликат', dl_total: 'Итого {a} / {b} {u} · {p}% плана',
  dl_over: 'больше плана', dl_empty: 'Отчётов пока нет',
  fl_kind: 'Тип', fl_before: 'До', fl_during: 'Процесс', fl_after: 'После', fl_document: 'Документ', fl_required: 'Обязательно: {k}', fl_missing: 'нет', fl_empty: 'Файлов нет',
  fl_drop: 'Выберите фото или документ', fl_by: 'Загрузил',
  h_create: 'Создана', h_update: 'Изменена', h_start: 'Начата', h_submit_review: 'Отправлена на проверку', h_accept: 'Принята', h_return: 'Возвращена', h_block: 'Заблокирована',
  h_unblock: 'Разблокирована', h_reopen: 'Переоткрыта', h_cancel: 'Отменена', h_delete: 'Удалена', h_checklist: 'Чеклист', h_checklist_add: 'Пункт добавлен', h_daily_progress: 'Дневной отчёт',
  h_attach: 'Файл загружен', h_attachment_delete: 'Файл удалён', h_comment: 'Комментарий', h_dependency_add: 'Зависимость добавлена', h_dependency_remove: 'Зависимость удалена',
  h_reviewer_reassigned: 'Проверяющий изменён', h_source: 'источник',
  cr_title: 'Новая задача', cr_template: 'Шаблон', cr_no_template: 'Без шаблона', cr_name: 'Название', cr_type: 'Вид работ', cr_project: 'Проект', cr_location: 'Место',
  cr_assignee: 'Исполнитель', cr_reviewer: 'Проверяющий', cr_start: 'Начало', cr_end: 'Срок', cr_qty: 'План объёма', cr_unit: 'Ед.', cr_desc: 'Описание', cr_checklist: 'Чеклист',
  cr_deps: 'Зависит от задач (коды через запятую)', cr_create: 'Создать', cr_voice: 'Голосом', cr_voice_stop: 'Стоп', cr_voice_hint: 'Скажите: кому, что, до какого срока. Затем Стоп.',
  cr_voice_processing: 'Распознаю…', cr_voice_off: 'Голосовой ввод не настроен', cr_voice_result: 'Распознано', cr_pick_assignee: 'Выберите исполнителя',
  cr_self_review: 'Исполнитель и проверяющий не могут совпадать', cr_crew: 'Бригада (чел.)', cr_type_hint: 'Вид работ задаёт чеклист и обязательные фото',
  t_code: 'Код', t_title: 'Название', t_location: 'Место', t_status: 'Статус', t_assignee: 'Исполнитель', t_end: 'Срок', t_progress: 'Прогресс', t_priority: 'Приоритет', t_reviewer: 'Проверяющий',
  t_page: '{a}–{b} / {n}', t_prev: 'Назад', t_next: 'Далее',
  r_title: 'Отчёт', r_period: 'Период', r_from: 'с', r_to: 'по', r_by_status: 'По статусу', r_block_reasons: 'Причины блокировок', r_staff: 'Срез по сотрудникам',
  r_daily: 'Выполнено за 14 дней', r_name: 'Сотрудник', r_total: 'Всего', r_done: 'Выполнено', r_ontime: 'В срок %', r_return: 'Возвраты %', r_overdue: 'Просрочено', r_open: 'Открыто',
  r_avg: 'Средняя длительность', r_days: 'дн.', r_reviewers: 'Проверяющие', r_queue: 'Очередь', r_count: 'кол-во', r_block_days: 'дн.', r_hist: 'всего случаев',
  r_overdue_assignee: 'исполнитель', r_overdue_reviewer: 'проверяющий',
  ty_title: 'Виды работ', ty_name: 'Название', ty_group: 'Группа', ty_days: 'Длительность (дн.)', ty_evidence: 'Обязательные фото', ty_checklist: 'Стандартный чеклист', ty_new: 'Новый вид работ',
  ty_archive: 'В архив', ty_restore: 'Восстановить', ty_archived: 'в архиве', ty_hint: 'Вид работ не удаляется — уходит в архив. На созданные задачи не влияет.',
  tp_title: 'Шаблоны', tp_name: 'Название', tp_pattern: 'Шаблон названия', tp_pattern_hint: '{joy} — место, {sana} — дата', tp_new: 'Новый шаблон', tp_use: 'Создать задачу',
  tp_recurring: 'Повторяющиеся правила', tp_rrule: 'Правило', tp_daily: 'Ежедневно (кроме вс)', tp_weekly: 'Еженедельно', tp_days: 'Дни', tp_next: 'Следующий', tp_active: 'Активно',
  us_title: 'Пользователи', us_name: 'Ф.И.О.', us_login: 'Логин', us_role: 'Роль', us_scope: 'Область', us_tg: 'Telegram', us_active: 'Активен', us_blocked: 'Заблокирован',
  us_new: 'Новый пользователь', us_phone: 'Телефон', us_lang: 'Язык', us_block: 'Заблокировать', us_unblock: 'Разблокировать', us_pw: 'Пароль (мин. {n} симв.)', us_scope_system: 'Вся система',
  us_scope_project: 'Проект', us_scope_location: 'Участок (блок)', us_linked: 'привязан', us_not_linked: 'не привязан', us_roles: 'Роли и права', us_perm: 'Право',
  us_block_hint: 'Заблокированный сотрудник не удаляется — задачи и история остаются; очередь проверки переходит руководителю.',
  tg_title: 'Telegram бот', tg_desc: 'Привяжите аккаунт к боту — уведомления, дневной отчёт и голосовые задачи работают через Telegram.', tg_get_code: 'Получить код',
  tg_code_hint: 'Напишите боту /start и отправьте этот код. Код действует 10 минут.', tg_linked: 'Telegram привязан', tg_unlink: 'Отвязать', tg_not_linked: 'Не привязан', tg_since: 'привязан', tg_bot: 'Бот',
  bk_title: 'Массовое создание — копирование этажа', bk_source: 'Исходное место', bk_targets: 'Целевые места', bk_step: 'Шаг дат (дн.)', bk_assignee: 'Исполнитель', bk_keep: 'Как в исходном',
  bk_set: 'Один для всех', bk_deps: 'Зависимости', bk_deps_none: 'Как в исходном', bk_deps_chain: 'Последовательная цепочка', bk_preview: 'Предпросмотр', bk_run: 'Создать ({n})',
  bk_result: 'Создано: {n}', bk_hint: 'Сначала обязателен предпросмотр. Больше 1000 — отклоняется.',
  pj_title: 'Проекты и места', pj_code: 'Код', pj_name: 'Название', pj_new: 'Новый проект', pj_locations: 'Места (блок → этаж → зона)', pj_add_block: '+ Блок', pj_add_floor: '+ Этаж', pj_add_zone: '+ Зона', pj_loc_name: 'Название',
  notif: 'Уведомления', notif_empty: 'Уведомлений нет', mark_read: 'Отметить все прочитанными', lang: 'Язык', me: 'Я', role: 'Роль',
  err_version: 'Задача изменена другим пользователем — обновлено, повторите.', err_generic: 'Произошла ошибка', updated: 'Сохранено', created_ok: 'Создано',
  sources: { web: 'web', mobile: 'мобильный', bot: 'бот', system: 'система' }, perm_view_only: 'только просмотр',
  nav_profile: 'Профиль', sub_profile: 'пароль · язык',
  pf_title: 'Мой профиль', pf_name: 'Ф.И.О.', pf_phone: 'Телефон', pf_lang: 'Язык интерфейса',
  pf_login: 'Логин', pf_role: 'Роль', pf_scope: 'Область',
  pf_pw: 'Смена пароля', pf_pw_new: 'Новый пароль (мин. {n} символов)', pf_pw_confirm: 'Повторите новый пароль',
  pf_pw_mismatch: 'Пароли не совпадают', pf_pw_short: 'Минимум {n} символов', pf_pw_hint: 'Оставьте пустым - пароль не изменится',
  pf_saved: 'Профиль сохранён', pf_pw_saved: 'Пароль изменён',
  nav_staff: 'Сотрудники', sub_staff: 'список команды', nav_admin: 'Администрирование', sub_admin: 'доступы - бот',
  grp_admin: 'Управление',
  sf_title: 'Сотрудники', sf_search: 'По имени или роли...', sf_none: 'Сотрудник не найден',
  sf_open: 'Открыто', sf_overdue: 'Просрочено', sf_done: 'Выполнено', sf_ontime: 'В срок',
  sf_contact: 'Контакты', sf_no_phone: 'телефон не указан', sf_since: 'В системе', sf_last_login: 'Последний вход',
  sf_never: 'никогда', sf_hint: 'Здесь только данные команды. Доступы - в разделе Администрирование.',
  sf_pick: 'Выберите сотрудника',
  ad_title: 'Администрирование', ad_tab_users: 'Доступы', ad_tab_roles: 'Роли', ad_tab_bot: 'Бот',
  ad_tab_panels: 'Панели ролей',
  ad_new_user: '+ Новый сотрудник', ad_reset_pw: 'Сменить пароль', ad_pw_set: 'Новый пароль установлен',
  ad_pw_for: 'Новый пароль для {name}', ad_pw_copy: 'Передайте пароль сотруднику - он сможет сменить его сам.',
  ad_bot_title: 'Адрес Telegram бота', ad_bot_hint: 'Бот записывает свой адрес сам при запуске. Здесь можно изменить вручную - код трогать не нужно.',
  ad_bot_username: 'Username бота (без @)', ad_bot_open: 'Перейти к боту', ad_bot_saved: 'Адрес бота сохранён',
  ad_bot_empty: 'Пока не определён',
  ad_roles_hint: 'Нажмите на ячейку, чтобы включить или выключить право - применяется сразу. Роль администратора неизменяема.',
  ad_panels_hint: 'Каждая роль входит под своим логином и видит эти разделы. Отдельного приложения нет - панель определяется ролью.',
  ad_sees: 'видит', ad_hidden: 'не видит', ad_login_pw: 'Логин и пароль',
  pg_tasks: 'Задачи', pg_flow: 'Рабочий процесс', pg_content: 'Чеклист, фото, комментарии', pg_reports: 'Отчёты', pg_admin: 'Управление',
  pj_search: 'Поиск объекта...', pj_tasks: 'задач', pj_open: 'открыто', pj_late: 'просрочено', pj_archived: 'В архиве',
  pj_active: 'Активен', pj_empty_locs: 'Места ещё не добавлены', pj_pick: 'Выберите объект слева',
  pj_blocks: 'блок', pj_floors: 'этаж', pj_zones: 'зона', pj_add_first: 'Добавьте первый блок',
}

const en: typeof uz = {
  ...uz,
  app_sub: 'TASKS', login: 'Sign in', logout: 'Sign out', login_field: 'Login', password: 'Password', login_btn: 'Sign in', login_err: 'Wrong login or password',
  loading: 'Loading…', empty: 'Nothing here', error: 'Error', retry: 'Retry', save: 'Save', cancel: 'Cancel', close: 'Close', add: 'Add', edit: 'Edit', delete: 'Delete',
  search: 'Search…', all: 'All', yes: 'Yes', no: 'No', required: 'required', optional: 'optional', today: 'Today', view: 'view', of: 'of',
  nav_tasks: 'Tasks', nav_table: 'Table', nav_projects: 'Projects', nav_reports: 'Reports', nav_templates: 'Templates', nav_types: 'Work types', nav_users: 'Users',
  nav_telegram: 'Telegram bot', nav_bulk: 'Bulk create', grp_work: 'Work', grp_settings: 'Settings',
  sub_tasks: 'kanban · board', sub_table: 'list · CSV', sub_projects: 'sites & locations', sub_reports: 'KPI · breakdowns', sub_templates: 'ready tasks', sub_types: 'checklist · photos',
  sub_users: 'roles · scopes', sub_telegram: 'linking', sub_bulk: 'copy a floor',
  st_plan: 'Planned', st_progress: 'In progress', st_review: 'In review', st_done: 'Done', st_blocked: 'Blocked', st_cancelled: 'Cancelled',
  pr_low: 'Low', pr_normal: 'Normal', pr_high: 'High', priority: 'Priority',
  kpi_open: 'Open', kpi_overdue: 'Overdue', kpi_blocked: 'Blocked', kpi_review: 'In review', kpi_ontime: 'Closed on time', kpi_open_sub: 'in columns', kpi_oldest: 'oldest {d} d',
  kpi_month: '{n} done total', kpi_material: '{n} material',
  f_project: 'Project', f_location: 'Location', f_type: 'Type', f_assignee: 'Assignee', f_priority: 'Priority', f_overdue: 'Overdue', f_blocked: 'Blocked', f_mine: 'My tasks',
  f_status: 'Status', f_reviewer: 'Reviewer', f_clear: 'Clear', f_export: 'Export CSV', new_task: '+ Task', board: 'Board', table: 'Table',
  c_checklist: 'Checklist', c_photos: 'photos', c_overdue: '{d} d overdue', c_review_days: 'In review {d} d', c_returned: 'Returned · {n}x', c_waiting: 'waiting {codes}',
  c_accepted: 'Accepted', c_ontime: 'on time', c_blocked_days: '{d} d', c_progress: 'Progress',
  tab_general: 'General', tab_checklist: 'Checklist', tab_daily: 'Daily report', tab_files: 'Photos / Files', tab_history: 'History', tab_comments: 'Comments',
  d_status: 'Status', d_type: 'Work type', d_assignee: 'Assignee', d_reviewer: 'Reviewer', d_plan: 'Plan', d_fact: 'Actual', d_qty: 'Quantity', d_desc: 'Description',
  d_deps: 'Depends on', d_dependents: 'Dependents', d_created: 'Created', d_days: 'd', d_ongoing: 'ongoing', d_location: 'Location', d_crew: 'Crew',
  d_blocked_since: 'Blocked', d_return_count: 'Returns', d_no_deps: 'No dependencies', d_add_dep: 'Add dependency (code)', d_code: 'Code',
  a_start: 'Start', a_submit: 'Submit for review', a_accept: 'Accept', a_return: 'Return', a_block: 'Block', a_unblock: 'Unblock', a_reopen: 'Reopen', a_cancel: 'Cancel task',
  a_delete: 'Delete', a_edit: 'Edit', a_comment: 'Comment', a_upload: 'Upload file', a_add_daily: 'Add report', a_add_item: 'Add item', a_open_web: 'Web',
  dlg_block_title: 'Block task', dlg_reason: 'Reason', dlg_note: 'Note', dlg_note_req: 'Note is required', dlg_return_title: 'Return reason', dlg_date_reason: 'Reason for date change',
  dlg_confirm_delete: 'Delete task? (moves to archive)', dlg_confirm_cancel: 'Cancel the task?', dlg_reopen_note: 'Reopen note (optional)',
  br_material_yoq: 'No material', br_hujjat_kutilmoqda: 'Waiting for document', br_texnika_band: 'Equipment busy', br_ishchi_yetmadi: 'Not enough workers',
  br_oldingi_ish: 'Previous work not done', br_obhavo: 'Weather', br_qaror_kutilmoqda: 'Waiting for decision', br_boshqa: 'Other',
  ck_required_missing: 'Required items not done', ck_done_of: '{a}/{b} done', ck_new: 'New item title',
  dl_date: 'Date', dl_qty: 'Qty', dl_workers: 'Workers', dl_hours: 'Hours', dl_note: 'Note', dl_by: 'By', dl_dup: 'duplicate', dl_total: 'Total {a} / {b} {u} · {p}% of plan',
  dl_over: 'over plan', dl_empty: 'No reports yet',
  fl_kind: 'Kind', fl_before: 'Before', fl_during: 'During', fl_after: 'After', fl_document: 'Document', fl_required: 'Required: {k}', fl_missing: 'missing', fl_empty: 'No files',
  fl_drop: 'Choose a photo or document', fl_by: 'Uploaded by',
  h_create: 'Created', h_update: 'Updated', h_start: 'Started', h_submit_review: 'Submitted for review', h_accept: 'Accepted', h_return: 'Returned', h_block: 'Blocked',
  h_unblock: 'Unblocked', h_reopen: 'Reopened', h_cancel: 'Cancelled', h_delete: 'Deleted', h_checklist: 'Checklist', h_checklist_add: 'Item added', h_daily_progress: 'Daily report',
  h_attach: 'File uploaded', h_attachment_delete: 'File deleted', h_comment: 'Comment', h_dependency_add: 'Dependency added', h_dependency_remove: 'Dependency removed',
  h_reviewer_reassigned: 'Reviewer reassigned', h_source: 'source',
  cr_title: 'New task', cr_template: 'Template', cr_no_template: 'No template', cr_name: 'Title', cr_type: 'Work type', cr_project: 'Project', cr_location: 'Location', cr_assignee: 'Assignee',
  cr_reviewer: 'Reviewer', cr_start: 'Start', cr_end: 'Due', cr_qty: 'Planned qty', cr_unit: 'Unit', cr_desc: 'Description', cr_checklist: 'Checklist', cr_deps: 'Depends on tasks (codes, comma separated)',
  cr_create: 'Create', cr_voice: 'By voice', cr_voice_stop: 'Stop', cr_voice_hint: 'Say: who, what, by when. Then Stop.', cr_voice_processing: 'Transcribing…', cr_voice_off: 'Voice input not configured',
  cr_voice_result: 'Recognized', cr_pick_assignee: 'Pick an assignee', cr_self_review: 'Assignee and reviewer cannot be the same person', cr_crew: 'Crew size', cr_type_hint: 'Work type defines checklist and required photos',
  t_code: 'Code', t_title: 'Title', t_location: 'Location', t_status: 'Status', t_assignee: 'Assignee', t_end: 'Due', t_progress: 'Progress', t_priority: 'Priority', t_reviewer: 'Reviewer',
  t_page: '{a}–{b} / {n}', t_prev: 'Prev', t_next: 'Next',
  r_title: 'Reports', r_period: 'Period', r_from: 'from', r_to: 'to', r_by_status: 'By status', r_block_reasons: 'Block reasons', r_staff: 'Staff breakdown', r_daily: 'Done in last 14 days',
  r_name: 'Person', r_total: 'Total', r_done: 'Done', r_ontime: 'On time %', r_return: 'Returns %', r_overdue: 'Overdue', r_open: 'Open', r_avg: 'Avg duration', r_days: 'd',
  r_reviewers: 'Reviewers', r_queue: 'Queue', r_count: 'count', r_block_days: 'd', r_hist: 'total cases', r_overdue_assignee: 'assignee', r_overdue_reviewer: 'reviewer',
  ty_title: 'Work types', ty_name: 'Name', ty_group: 'Group', ty_days: 'Duration (d)', ty_evidence: 'Required photos', ty_checklist: 'Default checklist', ty_new: 'New work type',
  ty_archive: 'Archive', ty_restore: 'Restore', ty_archived: 'archived', ty_hint: 'Work types are never deleted — only archived. Existing tasks are not affected.',
  tp_title: 'Templates', tp_name: 'Name', tp_pattern: 'Title pattern', tp_pattern_hint: '{joy} — location, {sana} — date', tp_new: 'New template', tp_use: 'Create task',
  tp_recurring: 'Recurring rules', tp_rrule: 'Rule', tp_daily: 'Daily (except Sunday)', tp_weekly: 'Weekly', tp_days: 'Days', tp_next: 'Next', tp_active: 'Active',
  us_title: 'Users', us_name: 'Full name', us_login: 'Login', us_role: 'Role', us_scope: 'Scope', us_tg: 'Telegram', us_active: 'Active', us_blocked: 'Blocked', us_new: 'New user',
  us_phone: 'Phone', us_lang: 'Language', us_block: 'Block', us_unblock: 'Unblock', us_pw: 'Password (min {n} chars)', us_scope_system: 'Whole system', us_scope_project: 'Project',
  us_scope_location: 'Section (block)', us_linked: 'linked', us_not_linked: 'not linked', us_roles: 'Roles & permissions', us_perm: 'Permission',
  us_block_hint: 'A blocked employee is never deleted — tasks and history stay; their review queue goes to a manager.',
  tg_title: 'Telegram bot', tg_desc: 'Link your account to the bot — notifications, daily reports and voice tasks work via Telegram.', tg_get_code: 'Get code',
  tg_code_hint: 'Send /start to the bot and then this code. Valid for 10 minutes.', tg_linked: 'Telegram linked', tg_unlink: 'Unlink', tg_not_linked: 'Not linked', tg_since: 'linked', tg_bot: 'Bot',
  bk_title: 'Bulk create — copy a floor', bk_source: 'Source location', bk_targets: 'Target locations', bk_step: 'Date step (days)', bk_assignee: 'Assignee policy', bk_keep: 'Keep as source',
  bk_set: 'One for all', bk_deps: 'Dependencies', bk_deps_none: 'As in source', bk_deps_chain: 'Sequential chain', bk_preview: 'Preview', bk_run: 'Create ({n})', bk_result: 'Created: {n}',
  bk_hint: 'Preview is required first. More than 1000 is rejected.',
  pj_title: 'Projects & locations', pj_code: 'Code', pj_name: 'Name', pj_new: 'New project', pj_locations: 'Locations (block → floor → zone)', pj_add_block: '+ Block', pj_add_floor: '+ Floor',
  pj_add_zone: '+ Zone', pj_loc_name: 'Name',
  notif: 'Notifications', notif_empty: 'No notifications', mark_read: 'Mark all read', lang: 'Language', me: 'Me', role: 'Role',
  err_version: 'Task was changed by another user — refreshed, please retry.', err_generic: 'Something went wrong', updated: 'Saved', created_ok: 'Created',
  sources: { web: 'web', mobile: 'mobile', bot: 'bot', system: 'system' }, perm_view_only: 'view only',
  nav_profile: 'Profile', sub_profile: 'password · language',
  pf_title: 'My profile', pf_name: 'Full name', pf_phone: 'Phone', pf_lang: 'Interface language',
  pf_login: 'Login', pf_role: 'Role', pf_scope: 'Scope',
  pf_pw: 'Change password', pf_pw_new: 'New password (min {n} characters)', pf_pw_confirm: 'Repeat the new password',
  pf_pw_mismatch: 'Passwords do not match', pf_pw_short: 'At least {n} characters', pf_pw_hint: 'Leave empty to keep the current password',
  pf_saved: 'Profile saved', pf_pw_saved: 'Password changed',
  nav_staff: 'Staff', sub_staff: 'team list', nav_admin: 'Administration', sub_admin: 'access - bot',
  grp_admin: 'Management',
  sf_title: 'Staff', sf_search: 'By name or role...', sf_none: 'No one found',
  sf_open: 'Open', sf_overdue: 'Overdue', sf_done: 'Done', sf_ontime: 'On time',
  sf_contact: 'Contact', sf_no_phone: 'no phone', sf_since: 'In the system', sf_last_login: 'Last login',
  sf_never: 'never', sf_hint: 'Team data only. Access rights live in Administration.',
  sf_pick: 'Pick a person',
  ad_title: 'Administration', ad_tab_users: 'Access', ad_tab_roles: 'Roles', ad_tab_bot: 'Bot',
  ad_tab_panels: 'Role panels',
  ad_new_user: '+ New person', ad_reset_pw: 'Reset password', ad_pw_set: 'New password set',
  ad_pw_for: 'New password for {name}', ad_pw_copy: 'Give the password to the person - they can change it themselves.',
  ad_bot_title: 'Telegram bot address', ad_bot_hint: 'The bot registers its own address on start. You can also set it here - no code change needed.',
  ad_bot_username: 'Bot username (no @)', ad_bot_open: 'Open the bot', ad_bot_saved: 'Bot address saved',
  ad_bot_empty: 'Not detected yet',
  ad_roles_hint: 'Click a cell to grant or revoke a permission - it takes effect immediately. The Administrator role is fixed.',
  ad_panels_hint: 'Every role signs in with its own login and sees these sections. There is no separate app - the panel follows the role.',
  ad_sees: 'sees', ad_hidden: 'hidden', ad_login_pw: 'Login and password',
  pg_tasks: 'Tasks', pg_flow: 'Workflow', pg_content: 'Checklist, photos, comments', pg_reports: 'Reports', pg_admin: 'Management',
  pj_search: 'Find a site...', pj_tasks: 'tasks', pj_open: 'open', pj_late: 'overdue', pj_archived: 'Archived',
  pj_active: 'Active', pj_empty_locs: 'No locations yet', pj_pick: 'Pick a site on the left',
  pj_blocks: 'block', pj_floors: 'floor', pj_zones: 'zone', pj_add_first: 'Add the first block',
}

export const DICT: Record<Lang, typeof uz> = { uz, ru, en }
export type Keys = keyof typeof uz

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: Keys | string, vars?: Record<string, any>) => string; d: typeof uz }
const I18nCtx = createContext<Ctx>(null as any)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangLS] = useLocalStorage<Lang>('saff.lang', (navigator.language || 'uz').startsWith('ru') ? 'ru' : (navigator.language || '').startsWith('en') ? 'en' : 'uz')
  const value = useMemo<Ctx>(() => {
    const d = DICT[lang] || uz
    const t = (k: string, vars?: Record<string, any>) => {
      let s: any = (d as any)[k] ?? (uz as any)[k] ?? k
      if (typeof s !== 'string') return String(s)
      if (vars) for (const [kk, v] of Object.entries(vars)) s = s.replace(new RegExp(`\\{${kk}\\}`, 'g'), String(v))
      return s
    }
    return { lang, setLang: (l: Lang) => { setLangLS(l); document.documentElement.lang = l }, t, d }
  }, [lang])
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>
}

export const useT = () => useContext(I18nCtx)

export const STATUS_ORDER = ['plan', 'progress', 'review', 'blocked', 'done'] as const
export const STATUS_COLOR: Record<string, string> = { plan: '#7d8da6', progress: '#2f81f7', review: '#d29922', done: '#2ea043', blocked: '#f85149', cancelled: '#a371f7' }

export function fmtDate(s?: string | null, lang: Lang = 'uz', withYear = false) {
  if (!s) return '—'
  const d = new Date(s.length <= 10 ? s + 'T00:00:00' : s)
  if (isNaN(d.getTime())) return s
  const loc = lang === 'ru' ? 'ru-RU' : lang === 'en' ? 'en-GB' : 'uz-Latn-UZ'
  try { return d.toLocaleDateString(loc, withYear ? { day: '2-digit', month: 'short', year: 'numeric' } : { day: '2-digit', month: 'short' }) } catch { return s.slice(0, 10) }
}
export function fmtDateTime(s?: string | null, lang: Lang = 'uz') {
  if (!s) return '—'
  const d = new Date(s.endsWith('Z') || s.includes('+') ? s : s + 'Z')
  const loc = lang === 'ru' ? 'ru-RU' : lang === 'en' ? 'en-GB' : 'uz-Latn-UZ'
  try { return d.toLocaleString(loc, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tashkent' }) } catch { return s }
}
