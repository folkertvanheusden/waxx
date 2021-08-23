#! /bin/sh

cd /usr/local/waxx

while true
do
	su - waxx -c ./waxx.py
	sleep 1
done
