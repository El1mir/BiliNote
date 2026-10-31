set -e
cd /c/Users/Administrator/Desktop/prjs/BiliNote/BillNote_frontend

# useI18n now lives in the context module; MessageKey in strings; translate in locale.
files=$(grep -rl "@/ember/i18n'" src || true)
for f in $files; do
	sed -i "s|import { useI18n } from '@/ember/i18n'|import { useI18n } from '@/ember/i18n/context'|" "$f"
	sed -i "s|import { translate } from '@/ember/i18n'|import { translate } from '@/ember/i18n/locale'|" "$f"
	sed -i "s|import type { MessageKey } from '@/ember/i18n'|import type { MessageKey } from '@/ember/i18n/strings'|" "$f"
	sed -i "s|import { useI18n, type MessageKey } from '@/ember/i18n'|import { useI18n } from '@/ember/i18n/context'\nimport type { MessageKey } from '@/ember/i18n/strings'|" "$f"
	sed -i "s|import { translate, type MessageKey } from '@/ember/i18n'|import { translate } from '@/ember/i18n/locale'\nimport type { MessageKey } from '@/ember/i18n/strings'|" "$f"
done

echo '--- leftover @/ember/i18n imports ---'
grep -rn "from '@/ember/i18n'" src || echo none
echo '--- index.tsx ---'
cat -n src/ember/i18n/index.tsx
