#!/usr/bin/env bash
#
# Change le numéro de version partout où il est écrit.
#
#   ./scripts/bump-version.sh 0.2.0
#
# Des fichiers séparés peuvent diverger sans que personne s'en aperçoive ;
# un test les compare, et ce script est ce qui les garde d'accord.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NEW="${1:-}"

[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "usage : $0 <majeur.mineur.correctif>   ex. 0.2.0"; exit 1;
}

OLD=$(sed -nE 's/^__version__ = "(.+)"$/\1/p' "$ROOT/backend/app/__init__.py")
[ "$OLD" != "$NEW" ] || { echo "déjà en $NEW"; exit 0; }

sed -i -E "s/^__version__ = \".*\"$/__version__ = \"$NEW\"/" "$ROOT/backend/app/__init__.py"
sed -i -E "0,/^version = \".*\"$/s//version = \"$NEW\"/" "$ROOT/backend/pyproject.toml"
sed -i -E "0,/\"version\": \".*\",/s//\"version\": \"$NEW\",/" "$ROOT/frontend/package.json"

echo "$OLD -> $NEW"
grep -nH -m1 -E "^__version__|^version = |\"version\":" \
  "$ROOT/backend/app/__init__.py" "$ROOT/backend/pyproject.toml" \
  "$ROOT/frontend/package.json"

cat <<REMINDER

Il reste à :
  - décrire le changement dans CHANGELOG.md, sous la nouvelle version ;
  - mettre le wiki à jour si un comportement documenté a changé.
REMINDER
