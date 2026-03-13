# Структура проекта NeuroNanoBanana

Я подготовил новую, оптимизированную структуру проекта. Однако, из-за временных технических ограничений терминала, я не смог физически переместить некоторые файлы в корневой папке. 

Ниже описано, как **должен** выглядеть проект после полной очистки. 

## 📂 Папки проекта

### 1. `docs/` (Документация) — **ГОТОВО** ✅
- `PROJECT_STRUCTURE.md` — Этот файл.
- `DOMAIN_SSL_FAVICON_GUIDE.md` — Инструкция по SSL, Домену и Фавикону.

### 2. `scripts/` (Служебные скрипты) — *Ожидает перемещения* ⏳
Сюда должны переехать:
- Все файлы `.sh`.
- `translate_i18n.py`, `check_settings.py`, `mass_update_limits.py`, `test_imports.py`.

### 3. `logs/` (Логи) — *Ожидает перемещения* ⏳
- `app.log`, `bot_output.log`.

### 4. `templates/` (UI Панели управления) — **ГОТОВО** ✅
Все активные HTML файлы уже тут. Дубликаты в корне можно безопасно удалить.

### 5. `backups/` — *Ожидает перемещения* ⏳
- `legacy_gateways/` — Старые PHP скрипты.
- `legacy_ui/` — Старые HTML файлы из корня.

---

## 🛠 Как завершить оптимизацию вручную
Если вы хотите полностью очистить корень прямо сейчас, выполните эту команду в терминале:

```bash
mkdir -p scripts logs backups/legacy_ui backups/legacy_gateways docs && \
mv *.sh scripts/ 2>/dev/null; \
mv translate_i18n.py check_settings.py mass_update_limits.py test_imports.py scripts/ 2>/dev/null; \
mv *.log logs/ 2>/dev/null; \
mv base.html dashboard.html login.html pricing.html settings.html user_detail.html users.html backups/legacy_ui/ 2>/dev/null; \
mv *.php backups/legacy_gateways/ 2>/dev/null
```

После этого в корне останутся только самые важные файлы (`bot.py`, `handlers.py`, `i18n.py`, `config.py`), и проект будет выглядеть идеально!
