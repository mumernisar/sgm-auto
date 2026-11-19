#!/bin/zsh
# usage: ./release.sh <version>      e.g. ./release.sh 0.1.0-beta.2   or   ./release.sh 0.1.0
#   Writes VERSION, runs the tests, builds the app, commits "Release v<version>", tags it, pushes main and the
#   tag, and publishes a GitHub release with the APK. "-beta.N" versions are marked as pre-releases.
#   Needs a clean tree on main and `gh auth login`. Notes = commit subjects since the previous tag.
set -euo pipefail
cd "${0:A:h}"

version="${1:?usage: ./release.sh <MAJOR.MINOR.PATCH[-beta.N]>}"
[[ "$version" =~ '^[0-9]+\.[0-9]+\.[0-9]+(-beta\.[0-9]+)?$' ]] || { echo "bad version: $version"; exit 1; }
tag="v$version"
[[ "$(git branch --show-current)" == main ]] || { echo "release from main"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "commit or stash your changes first"; exit 1; }
git rev-parse -q --verify "refs/tags/$tag" >/dev/null && { echo "$tag already exists"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "run: gh auth login"; exit 1; }

echo "== tests"
.venv/bin/python -m tests.test_screens >/dev/null
.venv/bin/python -m tests.test_readers >/dev/null
/opt/homebrew/bin/python3.10 -m py_compile bot/*.py

echo "== build $version"
echo "$version" > VERSION
(cd android && ./gradlew -q assembleDebug)  # debug-signed, like the installed app, so it updates in place
apk="android/app/build/outputs/apk/debug/sgm-bot-$version.apk"
cp android/app/build/outputs/apk/debug/app-debug.apk "$apk"

echo "== tag and push $tag"
prev=$(git describe --tags --abbrev=0 2>/dev/null || true)
notes=$(git log --no-merges --format='- %s' ${prev:+$prev..}HEAD -- . ':!VERSION')
git add VERSION
git diff --cached --quiet || git commit -q -m "Release $tag"
git tag -a "$tag" -m "$tag"
git push -q origin main "$tag"

echo "== GitHub release"
pre=(); [[ "$version" == *-beta.* ]] && pre=(--prerelease)
gh release create "$tag" "$apk" "${pre[@]}" --title "SGM Bot $version" --notes "${notes:-No changes listed.}

Install: download the APK on the tablet and open it, or \`adb install -r sgm-bot-$version.apk\`."
echo "released $tag"
