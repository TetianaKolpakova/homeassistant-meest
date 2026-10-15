# Публікація на GitHub

Папка проєкту вже має структуру репозиторію. Публікація ще не виконувалася.

## 1. Заповніть адресу репозиторію

Після вибору власника й назви виконайте (замініть приклад своїми значеннями):

```powershell
python scripts/configure_repository.py YOUR_LOGIN/ha-meest
```

Якщо власник є організацією, додайте `--maintainer YOUR_LOGIN`. Скрипт оновить
`documentation`, `issue_tracker`, `codeowners` та `.github/CODEOWNERS`.
До цього моменту manifest містить явні `OWNER/REPOSITORY` і не готовий до HACS.
Скрипт нічого не надсилає на GitHub і не додає remote.

## 2. Перевірте локально

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python scripts/check_repository.py --release
python scripts/build_release.py
```

Архів `dist/meest-0.1.0.zip` містить `custom_components/meest/` для ручного
встановлення. Він не містить тестів, локальних звітів чи облікових даних.
HACS використовує звичайну структуру репозиторію, не цей ZIP (`zip_release=false`).

## 3. Створіть порожній публічний репозиторій на GitHub

Не генеруйте README чи ліцензію на сайті: вони вже є локально. Увімкніть Issues.
Рекомендований опис: `Meest parcel tracking for Home Assistant: two aggregate sensors.`
Теми: `home-assistant`, `hacs`, `custom-integration`, `meest`, `parcel-tracking`.

Після створення репозиторію та вибору адреси:

```powershell
git add .
git diff --cached --stat
git commit -m "Initial Meest Home Assistant integration"
git remote add origin https://github.com/YOUR_LOGIN/ha-meest.git
git push -u origin main
```

Автор Git береться з ваших власних налаштувань; проєкт не вигадує identity і не
змінює глобальну конфігурацію Git. До push перевірте список staged-файлів.

## 4. Перевірте GitHub Actions

Дочекайтеся успішних Tests, hassfest і HACS. Частина HACS-перевірок потребує вже
наявного публічного репозиторію, опису й тем. Локальна перевірка їх не замінює.

## 5. Випустіть першу версію

Версія тега, Release й `manifest.json` повинні збігатися (`v0.1.0` / `0.1.0`).
Створіть GitHub Release з тегом `v0.1.0`, додайте опис із CHANGELOG і за бажанням
`dist/meest-0.1.0.zip`. HACS не вимагає ZIP чи окремого Release для custom repository.

## 6. Додавання через HACS

HACS → меню → Custom repositories → URL вашого GitHub-репозиторію → Integration.
Потім встановіть Meest, перезапустіть HA й додайте інтеграцію через налаштування.
Для вже встановленої вручну інтеграції використовується той самий domain `meest`;
збережені записи й unique_id не змінюються.

Проєкт не додається автоматично до загального каталогу HACS. Це окремий процес.
