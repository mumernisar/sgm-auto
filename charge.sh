#!/bin/zsh
# usage: ./charge.sh off | on | status   — tablet battery charging (the setting re-enables itself over time)
node=/sys/class/qcom-battery/batt_charge_en
case "$1" in
  off) adb shell "su -c 'echo 0 > $node'" ;;
  on)  adb shell "su -c 'echo 1 > $node'" ;;
esac
adb shell "cat /sys/class/power_supply/battery/status /sys/class/power_supply/battery/capacity" | paste -sd' ' - | sed 's/$/%/'
