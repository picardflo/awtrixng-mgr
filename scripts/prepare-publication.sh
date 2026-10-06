#!/usr/bin/env bash
#
# Prépare un clone destiné à GitHub, en réécrivant l'adresse des commits.
#
#   ./scripts/prepare-publication.sh 12345678+monpseudo@users.noreply.github.com
#
# Pourquoi un clone et pas ce dépôt-ci : réécrire l'historique change chaque
# empreinte de commit. Fait ici, le `git pull` de la VM de déploiement tombe
# en rejet et le dépôt Gogs devient incohérent avec ce qui tourne. Le clone
# est jetable ; ce dépôt ne bouge pas.
#
# L'adresse à passer est celle que GitHub fournit dans Settings > Emails,
# « Keep my email addresses private ». Elle redirige vers votre vraie boîte
# sans jamais l'exposer.
set -euo pipefail

NEW_EMAIL="${1:-}"
[[ "$NEW_EMAIL" == *@*.* ]] || {
  echo "usage : $0 <ID+pseudo@users.noreply.github.com>" >&2
  echo "        (Settings > Emails > Keep my email addresses private)" >&2
  exit 1
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${2:-/tmp/awtrixng-mgr-public}"

OLD_EMAILS=$(cd "$ROOT" && git log --format='%ae%n%ce' | sort -u)
echo "Adresses présentes dans l'historique :"
echo "$OLD_EMAILS" | sed 's/^/  /'
echo
echo "Toutes seront remplacées par : $NEW_EMAIL"
read -rp "Continuer ? [o/N] " reponse
[[ "$reponse" == [oO] ]] || { echo "abandon"; exit 1; }

rm -rf "$OUT"
git clone --no-local "$ROOT" "$OUT"
cd "$OUT"

if command -v git-filter-repo >/dev/null 2>&1; then
  printf 'literal:%s==>%s\n' "$(echo "$OLD_EMAILS" | head -1)" "$NEW_EMAIL" > /tmp/mailmap-ignore
  git filter-repo --force --email-callback "return b\"$NEW_EMAIL\""
else
  # filter-branch est déprécié et bruyant, mais il est partout. Une centaine
  # de commits passent en quelques secondes.
  echo "git-filter-repo absent, repli sur filter-branch" >&2
  FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --env-filter "
    export GIT_AUTHOR_EMAIL='$NEW_EMAIL'
    export GIT_COMMITTER_EMAIL='$NEW_EMAIL'
  " --tag-name-filter cat -- --all
  rm -rf .git/refs/original
  git reflog expire --expire=now --all
  git gc --prune=now --quiet
fi

echo
echo "Adresses après réécriture :"
git log --format='%ae%n%ce' | sort -u | sed 's/^/  /'
echo
echo "Clone prêt : $OUT"
echo
echo "Il reste à :"
echo "  1. poser la licence :"
echo "     curl -o $OUT/LICENSE https://www.gnu.org/licenses/agpl-3.0.txt"
echo "  2. vérifier qu'elle commence bien par « GNU AFFERO GENERAL PUBLIC LICENSE »"
echo "  3. git -C $OUT add LICENSE && git -C $OUT commit -m 'docs: AGPL-3.0'"
echo "  4. git -C $OUT remote set-url origin git@github.com:<vous>/awtrixng-mgr.git"
echo "  5. git -C $OUT push -u origin master"
