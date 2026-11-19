#!/bin/zsh
# usage: ./snap.sh <label>   -> saves shots/<n>_<label>.png (full res) + a small copy for review
# long labels are truncated in the filename; the full label is kept in shots/notes.txt (git-ignored)
cd "${0:A:h}/shots"
shots=( *.png(N) ); shots=( ${shots:#*_small.png} )
n=$(printf "%03d" $(( ${#shots} + 1 )))
label="${1:-screen}"
f="${n}_${label[1,60]}"
adb exec-out screencap -p > "$f.png" && sips -Z 1280 "$f.png" --out "${f}_small.png" >/dev/null
echo "$n: $label" >> notes.txt
if [[ -n "$SGM_PLAYER_NAME" || -f .player_name ]]; then ../.venv/bin/python ../tools/blur_name.py "$f.png"; fi
echo "saved $PWD/$f.png"
