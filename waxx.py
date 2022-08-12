#! /usr/bin/python3.7

import asyncio
import gc
import hashlib
import json
import logging
import math
import mysql.connector
import queue
import random
from random import randint
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import websockets

from glicko import glicko_wrapper

import ataxx.pgn
import ataxx.uai

# how many ms per move
tpm = 5000
time_buffer_soft = 200 # be aware of ping times
time_buffer_hard = 1000
# output
pgn_file = None
# opening book, a list of FENs
book = 'openings.txt'
# gauntlet?
gauntlet = True

# this user needs a GRANT ALL
db_host = '192.168.64.1'
db_user = 'waxx'
db_pass = 'waxx'
db_db = 'waxx'

# web sockets
ws_port = 7624
ws_interface = '127.0.0.1'

# match history
match_history_size = 25

logfile = 'waxx.log'

###

logger = logging.getLogger('websockets.server')
logger.setLevel(logging.ERROR)
logger.addHandler(logging.FileHandler(logfile))

lock = threading.Lock()
last_activity = {}
idle_clients = []
playing_clients = []
last_change = 0
matches = []

ws_data = {}
ws_msgs = {}
ws_new_data = {}
ws_data_lock = threading.Lock()

async def ws_serve(websocket, path_in):
    global last_change
    global lock
    global matches
    global ws_data
    global ws_new_data
    global ws_data_lock

    listen_pair = None

    q = path_in.find('?')
    if q != -1:
        path = path_in[0:q]

        parts = urllib.parse.parse_qs(path_in[q+1:])
        if 'p1' in parts and 'p2' in parts:
            p1 = parts['p1'][0]
            p2 = parts['p2'][0]
            listen_pair = p1 + '|' + p2

    else:
        path = path_in

    remote_addr = str(websocket.remote_address)

    try:
        flog('%s] websocket started, %s' % (remote_addr, path))
        #flog('%s] websocket started, %s for %s' % (remote_addr, path, websocket.headers['x-forwarded-for']))

        if 'viewer' in path:
            await websocket.send('msg %f Initializing...' % time.time())

            if not listen_pair:
                flog('%s] websocket waiting for pair-request' % remote_addr)
                listen_pair = await websocket.recv()

            flog('%s] websocket is listening for %s' % (remote_addr, listen_pair))

            p_np = p_fen = p_msg = None
            p_new_data = None

            while True:
                send = send_np = send_msg = None
                send_new_data = None

                with ws_data_lock:
                    if listen_pair in ws_data and (p_fen == None or ws_data[listen_pair] != p_fen):
                        send = p_fen = ws_data[listen_pair]

                    if listen_pair in ws_new_data:
                        temp = json.dumps(ws_new_data[listen_pair])

                        if p_new_data == None or temp != p_new_data:
                            send_new_data = p_new_data = temp

                    if 'new_pair' in ws_data and (p_np == None or ws_data['new_pair'] != p_np):
                        send_np = p_np = ws_data['new_pair']

                    if listen_pair in ws_msgs and (p_msg == None or ws_msgs[listen_pair] != p_msg):
                        send_msg = p_msg = ws_msgs[listen_pair]

                if send:
                    str_ = 'fen %s %s %f' % (send[0], send[1], send[2])
                    await websocket.send(str_)

                if send_new_data:
                    await websocket.send(send_new_data)

                if send_msg:
                    str_ = 'msg %f %s' % (send_msg[1], send_msg[0])
                    await websocket.send(str_)

                if send_np:
                    str_ = 'new_pair %s %s %f' % (send_np[0], send_np[1], send_np[2])
                    await websocket.send(str_)

                #await asyncio.sleep(0.25)
                try:
                    listen_pair = await asyncio.wait_for(websocket.recv(), timeout=0.25)
                except asyncio.TimeoutError:
                    pass

        elif 'list' in path:
            plc = None

            while True:
                lc = 0

                with lock:
                    lc = last_change

                if plc != lc:
                    await websocket.send(json.dumps(get_players_idlers()))
                    plc = lc

                await asyncio.sleep(2.0)

        elif 'matches' in path:
            mp = None

            while True:
                mc = None

                with lock:
                    mc = matches

                if mc != mp:
                    js_ready = [(m[0][1], m[1][1]) for m in mc]
                    await websocket.send(json.dumps(js_ready))

                    mp = mc

                await asyncio.sleep(2.1)

    except websockets.exceptions.ConnectionClosedOK:
        flog('%s] ws_serve: socket disconnected' % remote_addr)

    except Exception as e:
        flog('%s] ws_serve: %s' % (e, remote_addr))

        fh = open(logfile, 'a')
        traceback.print_exc(file=fh)
        fh.close()

def get_players_idlers():
    out = {}
    idlers = []
    players = []

    with lock:   
        for clnt in idle_clients:    
            p1 = clnt[0] 

            record = { 'name' : p1.name, 'user' : clnt[1] }

            idlers.append(record)

        for couple in playing_clients:  
            clnt1 = couple[0]   
            p1 = clnt1[0]   
            p1_name = p1.name   
            p1_user = clnt1[1]  

            la1 = last_activity[p1_name] if p1_name in last_activity else 0

            clnt2 = couple[1]   
            p2 = clnt2[0]   
            p2_name = p2.name   
            p2_user = clnt2[1]

            la2 = last_activity[p2_name] if p2_name in last_activity else 0

            players.append({ 'player_1' : { 'user' : p1_user, 'name' : p1_name, 'last_activity' : la1 }, 'player_2' : { 'user' : p2_user, 'name' : p2_name, 'last_activity' : la2 } })

    out = { 'idle' : idlers, 'playing' : players }

    return out

def run_websockets_server():
    start_server = websockets.serve(ws_serve, ws_interface, ws_port)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

def start_ws_record(pair):
    flog('%s, start new' % pair)

    with ws_data_lock:
        ws_new_data[pair] = []

def add_ws_move_record(pair, m):
    record = {}

    record['type'] = 'move'

    fen = m['fen'].split(' ')
    record['fen'] = fen[0]
    record['color'] = fen[1]
    record['half_move'] = fen[2]
    record['full_move'] = fen[3]

    record['move'] = m['move']

    record['score'] = m['score']

    record['move_took'] = math.ceil(m['took'] * 1000.0)
    record['timestamp'] = math.floor(m['ts'] * 1000.0)

    #flog('%s add %s' % (pair, json.dumps(record)))

    with ws_data_lock:
        ws_new_data[pair].append(record)

def add_ws_msg_record(pair, txt):
    record = {}

    record['type'] = 'msg'
    record['msg'] = txt
    record['timestamp'] = math.floor(time.time() * 1000.0)

    #flog('%s add %s' % (pair, json.dumps(record)))

    with ws_data_lock:
        ws_new_data[pair].append(record)

def flog(what):
    if not logfile:
        return

    try:
        ts = time.asctime()

        print(ts, what)

        fh = open(logfile, 'a')
        fh.write('%s %s\n' % (ts, what))
        fh.close()

    except Exception as e:
        print('Logfile failure %s' % e)

try:
    conn = mysql.connector.connect(host=db_host, user=db_user, passwd=db_pass, database=db_db)
    c = conn.cursor()
    c.execute('CREATE TABLE results(id INT(12) NOT NULL AUTO_INCREMENT, ts datetime, p1 varchar(64), e1 varchar(128), t1 double, p2 varchar(64), e2 varchar(128), t2 double, result varchar(7), adjudication varchar(128), plies int, tpm int, pgn text, md5 char(32), score int, primary key(id))')
    c.execute('CREATE TABLE players(user varchar(64), password varchar(64), author varchar(128), engine varchar(128), rating double default 1000, w int(8) default 0, d int(8) default 0, l int(8) default 0, failure_count int(8) default 0, primary key(user))')
    c.execute('create table moves(results_id int not null, move_nr int(4), fen varchar(128), move varchar(5), took double, score int, is_p1 int(1), foreign key(results_id) references results(id) )')
    conn.commit()
    conn.close()
except Exception as e:
    flog('db create: %s' % e)

temp = open(book, 'r').readlines()
book_lines = [line.rstrip('\n') for line in temp]

def purge_matches_by(who):
    with lock:
        delete_these = []

        for m in matches:
            if who == m[0][1] or who == m[1][1]:
                flog('User %s is gone, purging %s-%s' % (who, m[0][1], m[1][1]))
                delete_these.append(m)

        for d in delete_these:
            matches.remove(d)

def play_game(p1_in, p2_in, t, time_buffer_soft, time_buffer_hard):
    global book_lines
    global last_change

    fail2 = fail1 = False

    p1 = p1_in[0]
    p1_user = p1_in[1]
    p2 = p2_in[0]
    p2_user = p2_in[1]

    pair = '%s|%s' % (p1_user, p2_user)

    try:
        flog(' *** Starting game between %s(%s) and %s(%s)' % (p1.name, p1_user, p2.name, p2_user))
        start_ws_record(pair)

        p1.uainewgame()
        p1.setoption('UCI_Opponent', 'none none computer %s' % p2.name)
        p2.uainewgame()
        p2.setoption('UCI_Opponent', 'none none computer %s' % p1.name)

        pos = random.choice(book_lines)

        board = ataxx.Board(pos)

        game_start = time.time()

        with ws_data_lock:
            ws_data[pair] = (board.get_fen(), 'START', game_start)
            ws_data['new_pair'] = (p1_user, p2_user, game_start)
            ws_msgs[pair] = ('Playing', game_start)

        reason = None

        n_ply = t1 = t2 = 0

        moves = []

        while not board.gameover():
            start = took = None

            who = p1.name if board.turn == ataxx.BLACK else p2.name
            side = "black" if board.turn == ataxx.BLACK else "white"

            maxwait = (t + time_buffer_hard) / 1000.0

            bestmove = ponder = None

            m = {}
            m['move_nr'] = board.fullmove_clock
            m['fen'] = board.get_fen()
            m['is_p1'] = 1 if board.turn == ataxx.BLACK else 0

            illegal_move = None

            now = None

            if board.turn == ataxx.BLACK:
                p1.position(board.get_fen())

                gc.disable()
                start = time.time()

                try:
                    bestmove, ponder = p1.go(movetime=t, maxwait=maxwait)
                except Exception as e:
                    flog('p1.go (%s) threw %s' % (p1.name, e))

                now = time.time()
                gc.enable()

                if bestmove == None:
                    fail1 = True

                    try:
                        p1.quit()
                    except:
                        pass

                took = now - start
                t1 += took

                with lock:
                    last_activity[p1.name] = now
                    last_change = now

            else:
                p2.position(board.get_fen())

                gc.disable()
                start = time.time()

                try:
                    bestmove, ponder = p2.go(movetime=t, maxwait=maxwait)
                except Exception as e:
                    flog('p2.go (%s) threw %s' % (p2.name, e))

                now = time.time()
                gc.enable()

                if bestmove == None:
                    fail2 = True

                    try:
                        p2.quit()
                    except:
                        pass

                took = now - start
                t2 += took

                with lock:
                    last_activity[p2.name] = now
                    last_change = now

            t_left = t + time_buffer_soft - took * 1000
            if t_left < 0 and reason == None:
                reason = '%s used too much time (W)' % side
                log_msg = '%s used %fms too much time (took: %f, allowed: %f)' % (who, -round(t_left, 3), took, t)
                add_ws_msg_record(pair, reason)
                flog(log_msg)

                with ws_data_lock:
                    ws_msgs[pair] = (log_msg, time.time())

                if t + time_buffer_hard - took * 1000 < 0:
                    reason = '%s used too much time (F)' % side
                    flog('%s went over the hard limit' % side)
                    add_ws_msg_record(pair, reason)
                    break

            m['ts'] = now

            if bestmove == None:
                if reason == None:
                    reason = '%s disconnected' % side
                    add_ws_msg_record(pair, reason)
                break

            else:
                m['move'] = bestmove
                m['took'] = took

            n_ply += 1

            #flog('%s) %s => %s (%f)' % (who, board.get_fen(), bestmove, took)) FIXME

            is_legal = False
            try:
                move = ataxx.Move.from_san(bestmove)
                is_legal = board.is_legal(move)

            except Exception as e:
                flog('%s) (threw) move is in invalid: %s' % (who, e))

            if not is_legal:
                illegal_move = bestmove
                who = p1.name if board.turn == ataxx.BLACK else p2.name
                reason = 'Illegal move by %s' % side
                flog('Illegal move by %s: %s' % (who, bestmove))
                add_ws_msg_record(pair, reason)

                if board.turn == ataxx.BLACK:
                    fail1 = True
                else:
                    fail2 = True

                m['score'] = -9999
                moves.append(m)
                add_ws_move_record(pair, m)
                break

            board.makemove(move)

            m['score'] = board.score()

            add_ws_move_record(pair, m)

            with ws_data_lock:
                ws_data[pair] = (board.get_fen(), bestmove, now)

            if board.fifty_move_draw():
                reason = 'fifty moves'
                add_ws_msg_record(pair, reason)
                moves.append(m)
                break

            moves.append(m)

            #if board.max_length_draw(): FIXME
            #    reason = 'max length'
            #    break

        game_took = time.time() - game_start

        try:
            p1_in[0].isready(5)
            p2_in[0].isready(5)
        except Exception as e:
            flog('(threw) isready failed: %s' % e)

        game = ataxx.pgn.Game()
        last_node = game.from_board(board)
        if illegal_move:
            last_node.comment = 'Illegal move: %s' % illegal_move
        game.set_white(p1_user)
        game.set_black(p2_user)
        if reason:
            game.set_adjudicated(reason)

        result = board.result()

        flog('%s(%s) versus %s(%s): %s (%s)' % (p1.name, p1_user, p2.name, p2_user, result, reason))

        now = time.time()

        if reason:
            with ws_data_lock:
                ws_msgs[pair] = (reason, now)

        with lock:
            # update internal structures representing who is playing or not
            playing_clients.remove((p1_in, p2_in))
            last_change = now

            conn = mysql.connector.connect(host=db_host, user=db_user, passwd=db_pass, database=db_db)
            c = conn.cursor()

            if fail1:
                c.execute("UPDATE players SET failure_count=failure_count+1 WHERE user=%s", (p1_user,))
            else:
                idle_clients.append(p1_in)

            if fail2:
                c.execute("UPDATE players SET failure_count=failure_count+1 WHERE user=%s", (p2_user,))
            else:
                idle_clients.append(p2_in)

            # update pgn file
            if pgn_file:
                fh = open(pgn_file, 'a')
                fh.write(str(game))
                fh.write('\n\n')
                fh.close()

            # put result record in results table
            pgn = str(game)
            hash_in = '%f %s %s' % (time.time(), p1.name, p2.name)
            hash_ = hashlib.md5(hash_in.encode('utf-8')).hexdigest()

            adjudication = reason if reason != None else ''

            c = conn.cursor()
            c.execute("INSERT INTO results(ts, p1, e1, t1, p2, e2, t2, result, adjudication, plies, tpm, pgn, md5, score) VALUES(NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (p1_user, p1.name, t1, p2_user, p2.name, t2, result, adjudication, n_ply, t, pgn, hash_, board.score()))
            id_ = c.lastrowid

            c = conn.cursor()

            for m in moves:
                c.execute('INSERT INTO moves(results_id, move_nr, fen, move, took, score, is_p1) VALUES(%s, %s, %s, %s, %s, %s, %s)', (id_, m['move_nr'], m['fen'], m['move'], m['took'], m['score'], m['is_p1']))

            # update rating of the user
            if not fail1 and not fail2 and result != '*':
                c = conn.cursor()

                # get
                c.execute("SELECT rating, rd, unix_timestamp(last_game) FROM players WHERE user=%s", (p1_user,))
                row = c.fetchone()
                p1_user_rating = row[0] if row[0] else 1500
                p1_user_rd = row[1] if row[1] else 350
                p1_lg = row[2] if row[2] else 0

                c.execute("SELECT rating, rd, unix_timestamp(last_game) FROM players WHERE user=%s", (p2_user,))
                row = c.fetchone()
                p2_user_rating = row[0] if row[0] else 1500
                p2_user_rd = row[1] if row[1] else 350
                p2_lg = row[2] if row[2] else 0

                # update
                new_rating_1, new_rd_1, new_rating_2, new_rd_2 = glicko_wrapper(p1_user_rating, p1_user_rd, p1_lg, p2_user_rating, p2_user_rd, p2_lg, result)

                # put
                c.execute("UPDATE players SET rating=%s, last_game=from_unixtime(%s), rd=%s WHERE user=%s", (new_rating_1, int(game_start), new_rd_1, p1_user,))
                c.execute("UPDATE players SET rating=%s, last_game=from_unixtime(%s), rd=%s WHERE user=%s", (new_rating_2, int(game_start), new_rd_2, p2_user,))

                if result == '1-0':
                    c.execute("UPDATE players SET w=w+1 WHERE user=%s", (p1_user,))
                    c.execute("UPDATE players SET l=l+1 WHERE user=%s", (p2_user,))
                elif result == '0-1':
                    c.execute("UPDATE players SET l=l+1 WHERE user=%s", (p1_user,))
                    c.execute("UPDATE players SET w=w+1 WHERE user=%s", (p2_user,))
                else:
                    c.execute("UPDATE players SET d=d+1 WHERE user=%s", (p1_user,))
                    c.execute("UPDATE players SET d=d+1 WHERE user=%s", (p2_user,))

                flog('new rating of %s: %f (%f)' % (p1_user, new_rating_1, new_rd_1))
                flog('new rating of %s: %f (%f)' % (p2_user, new_rating_2, new_rd_2))

            conn.commit()
            conn.close()

        now = time.time()
        if ws_msgs[pair][0] == 'Playing':
            txt = 'Finished (in %f seconds)' % round(game_took, 2)

            with ws_data_lock:
                ws_msgs[pair] = (txt, now)

            add_ws_msg_record(pair, txt)

    except Exception as e:
        flog('(threw) failure: %s (%s)' % (e, pair))
        fh = open(logfile, 'a')
        traceback.print_exc(file=fh)
        fh.close()

        with lock:
            playing_clients.remove((p1_in, p2_in))
            last_change = time.time()

        fail1 = fail2 = True

    try:
        if fail1:
            purge_matches_by(p1_user)

            p1_in[0].quit()
            del p1_in
    except Exception as e:
        flog('(threw) failure: %s (%s)' % (e, pair))
        fh = open(logfile, 'a')
        traceback.print_exc(file=fh)
        fh.close()

    try:
        if fail2:
            purge_matches_by(p2_user)

            p2_in[0].quit()
            del p2_in
    except Exception as e:
        flog('(threw) failure: %s (%s)' % (e, pair))
        fh = open(logfile, 'a')
        traceback.print_exc(file=fh)
        fh.close()

def find_client_idle(tuple_list, element_1):
    for t in tuple_list:
        if t[1] == element_1:
            return t

    return None

def find_client_playing(tuple_list, element_1):
    for t in tuple_list:
        if t[0][1] == element_1:
            return t[0]

        if t[1][1] == element_1:
            return t[1]

    return None

def match_scheduler():
    while True:
        with lock:
            n_idle = len(idle_clients)
            n_play = len(playing_clients)

            if len(matches) == 0 and n_idle >= 2:
                # get list of elo-ratings for idle players
                conn = mysql.connector.connect(host=db_host, user=db_user, passwd=db_pass, database=db_db)
                c = conn.cursor()

                user_names = [ic[1] for ic in idle_clients]
                format_string = ','.join(['%s'] * len(user_names))
                c.execute("SELECT user, rating FROM players WHERE user IN (%s) ORDER BY rating DESC" % format_string, tuple(user_names))

                ratings = dict()
                for row in c.fetchall():
                    ratings[row[0]] = float(row[1])

                conn.close()

                # match
                opponents = []
                for user, rating in ratings.items():
                    if len(opponents) > 0:
                        for o in opponents:
                            p1 = find_client_idle(idle_clients, user)
                            p2 = find_client_idle(idle_clients, o[0])

                            flog('scheduling game %s %s (and vice versa)' % (p1[1], p2[1]))

                            matches.append((p1, p2))
                            matches.append((p2, p1))

                    opponents.append((user, rating))
                    while len(opponents) > 2:
                        del opponents[0]

                for attempt in range(0, len(idle_clients)):
                    p1 = find_client_idle(idle_clients, random.choice(user_names))
                    p2 = find_client_idle(idle_clients, random.choice(user_names))

                    if p1 != p2:
                        if (p1, p2) not in matches:
                            flog('random pairs, scheduling game %s %s (and vice versa)' % (p1[1], p2[1]))
                            matches.append((p1, p2))

                        if (p2, p1) not in matches:
                            flog('random pairs, scheduling game %s %s (and vice versa)' % (p2[1], p1[1]))
                            matches.append((p2, p1))


            flog('idle: %d, playing: %d, matches: %d' % (n_idle, n_play * 2, len(matches)))
            flog('- idle: %s' % str([ic[1] for ic in idle_clients]))
            flog('- playing: %s' % str(['%s-%s' % (p[0][1], p[1][1]) for p in playing_clients]))
            flog('- matches: %s' % str(['%s-%s' % (m[0][1], m[1][1]) for m in matches]))

            delete_these = []
            for m in matches:
                if m[0] in idle_clients and m[1] in idle_clients:
                    idle_clients.remove(m[0])
                    idle_clients.remove(m[1])

                    playing_clients.append(m)

                    delete_these.append(m)

                    t = threading.Thread(target=play_game, args=(m[0], m[1], tpm, time_buffer_soft, time_buffer_hard, ))
                    t.start()

            for d in delete_these:
                matches.remove(d)

        time.sleep(1.5)

def schedule_matches_for_new_player(player):
    flog('Scheduling new player %s' % player[1])

    with lock:
        for clnt in idle_clients:
            if clnt == player:
                continue

            flog('Scheduling new player %s against %s' % (player[1], clnt[1]))
            matches.append((player, clnt))
            matches.append((clnt, player))

        for clients in playing_clients:
            if clients[0][1] != player[1]:
                flog('Scheduling new player %s against %s' % (player[1], clients[0][1]))
                matches.append((player, clients[0]))
                matches.append((clients[0], player))

            if clients[1][1] != player[1]:
                flog('Scheduling new player %s against %s' % (player[1], clients[1][1]))
                matches.append((player, clients[1]))
                matches.append((clients[1], player))

def add_client(sck, addr):
    global last_change

    try:
        sck.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sck.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        buf = ''
        while not '\n' in buf or not 'user ' in buf:
            data = sck.recv(1024)
            if not data or data == '':
                sck.close()
                return

            buf += data.decode()

        lf = buf.find('\n')
        user = buf[5:lf].lower().strip()

        if user == '':
            sck.close()
            return

        buf = buf[lf + 1:]
        while not '\n' in buf or not 'pass ' in buf:
            data = sck.recv(1024)
            if not data or data == '':
                sck.close()
                return

            buf += data.decode()

        lf = buf.find('\n')
        password = buf[5:lf].strip()

        if password == '':
            sck.close()
            return

        conn = mysql.connector.connect(host=db_host, user=db_user, passwd=db_pass, database=db_db)
        c = conn.cursor()
        c.execute('SELECT password FROM players WHERE user=%s', (user,))
        row = c.fetchone()
        conn.close()

        if row == None:
            conn = mysql.connector.connect(host=db_host, user=db_user, passwd=db_pass, database=db_db)
            c = conn.cursor()
            c.execute('INSERT INTO players(user, password, rating, rd) VALUES(%s, %s, 1500, 350)', (user, password,))
            conn.commit()
            conn.close()

        elif row[0] != password:
            sck.send(bytes('Invalid password\n', encoding='utf8'))
            sck.close()
            return

        e = ataxx.uai.Engine(sck, True)
        e.uai()
        e.isready()

        flog('Connected with %s (%s) running %s (by %s)' % (addr, user, e.name, e.author))

        conn = mysql.connector.connect(host=db_host, user=db_user, passwd=db_pass, database=db_db)
        c = conn.cursor()
        c.execute('UPDATE players SET author=%s, engine=%s WHERE user=%s', (e.author, e.name, user,))
        conn.commit()
        conn.close()

        new_client = (e, user)

        with lock:
            for clnt in idle_clients:
                if clnt[1] == user:
                    flog('Removing duplicate user %s' % user)
                    idle_clients.remove(clnt)
                    clnt[0].quit()

            idle_clients.append(new_client)

            last_change = time.time()

        schedule_matches_for_new_player(new_client)

    except Exception as e:
        flog('(threw) Fail: %s' % e)
        sck.close()
        traceback.print_exc(file=sys.stdout)

def client_listener():
    HOST = ''
    PORT = 28028
    ss = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ss.bind((HOST, PORT))
    ss.listen(128)

    while True:
        cs, addr = ss.accept()
        flog('tcp connection with %s %s ' % (cs, addr))

        t = threading.Thread(target=add_client, args=(cs,addr,))
        t.start()


t = threading.Thread(target=match_scheduler)
t.start()

t = threading.Thread(target=client_listener)
t.start()

run_websockets_server()
