#!/bin/sh

xrdb -merge ~/.Xresources

xmodmap ~/.Xmodmap

slstatus &

feh --bg-fill ~/Desktop/wallpaper.png &

exec dwm
