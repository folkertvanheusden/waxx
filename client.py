#! /usr/bin/python3

import getopt
import os
import select
import socket
import subprocess
import sys
import time
import threading
import traceback

def usage():
    print('-e x  program to invoke (Ataxx "engine")')
    print('-i x  server to connect to')
    print('-p x  port to connect to (usually 28028)')
    print('-U x  username to use')
    print('-P x  password to use')

engine = None
host = 'ataxx.vanheusden.com'
port = 28028
user = None
password = None

try:
    optlist, args = getopt.getopt(sys.argv[1:], 'e:i:p:U:P:')

    for o, a in optlist:
        if o == '-e':
            engine = a
        elif o == '-i':
            host = a
        elif o == '-p':
            port = int(a)
        elif o == '-U':
            user = a
        elif o == '-P':
            password = a
        else:
            print(o, a)

except getopt.GetoptError as err:
    print(err)
    usage()
    sys.exit(1)

if user == None or password == None:
    print('No user or password given')
    usage()
    sys.exit(1)

if engine == None:
    print('No program selected')
    usage()
    sys.exit(1)

def engine_thread(sck, eng):
    try:
        while True:
            dat = eng.stdout.readline()
            if dat == None:
                break

            dat = dat.replace(b'\n', b'\r\n')
            print(time.asctime(), 'engine: ', dat)

            rc = sck.send(dat)
            print('engine rc: ', rc)
            if rc == 0:
                break

    except Exception as e:
        print('Engine_thread terminating', e)


def socket_thread(eng, sck):
    try:
        while True:
            dat = sck.recv(4096)
            if dat == None:
                break

            print(time.asctime(), 'socket: %s' % dat.decode())
            rc = eng.stdin.write(dat)
            print('socket rc: ', rc)
            if rc == 0:
                break

            eng.stdin.flush()

    except Exception as e:
        print('Socket_thread terminating', e)

while True:
    s = None
    p = None

    try:
        print('Start process')
        p = subprocess.Popen(engine, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.connect((host, port))

        s.send(bytes('user %s\n' % user, encoding='utf8'))
        s.send(bytes('pass %s\n' % password, encoding='utf8'))

        t1 = threading.Thread(target=socket_thread, args=(p, s, ))
        t1.start()

        t2 = threading.Thread(target=engine_thread, args=(s, p, ))
        t2.start()

        while t1 and t2:
            if t1:
                t1.join(0.1)
                if not t1.isAlive():
                    t1 = None
                    print('Back from socket_thread join')

            if t2:
                t2.join(0.1)
                if not t2.isAlive():
                    t2 = None
                    print('Back from engine_thread join')

    except ConnectionRefusedError as e:
        print('failure: %s' % e)
        time.sleep(2.5)

    except Exception as e:
        print('failure: %s' % e)
        traceback.print_exc(file=sys.stdout)

    finally:
        print('Close socket')
        try:
            s.shutdown(socket.SHUT_RDWR)
        except Exception as e:
            print('failure: %s' % e)
        finally:
            s.close()
        del s

        print('Terminate process')
        try:
            p.kill()
            p.wait()
        except Exception as e:
            print('failure: %s' % e)
        del p

        print('Socket closed, process terminated')
