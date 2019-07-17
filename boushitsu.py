#!/usr/bin/env python3

import os
import sys
import json
import time
import socket
import subprocess
import datetime
import sqlite3
import twitter
import paho.mqtt.client as mqtt

from dotenv import load_dotenv
load_dotenv()

import light_sensor
import access_db

# Twitter API
SCREEN_NAME     = os.environ['SCREEN_NAME']
CONSUMER_KEY    = os.environ['CONSUMER_KEY']
CONSUMER_SECRET = os.environ['CONSUMER_SECRET']
ACCESS_KEY      = os.environ['ACCESS_KEY']
ACCESS_SECRET   = os.environ['ACCESS_SECRET']

# Beebotte
BEEBOTTE_HOST   = os.environ['BEEBOTTE_HOST']
BEEBOTTE_PORT   = int(os.environ['BEEBOTTE_PORT'])
BEEBOTTE_CACERT = os.environ['BEEBOTTE_CACERT']
BEEBOTTE_TOPIC  = os.environ['BEEBOTTE_TOPIC']
BEEBOTTE_TOKEN  = os.environ['BEEBOTTE_TOKEN']

AUTHORIZED_PERSONNEL = os.environ['AUTHORIZED_PERSONNEL'].split(',')

COMMAND_HELP_TEXT = '''\
Command format: cmd arg1 arg2 ...   // comment

Available Commands:

help: show the available commands and the corresponding usage

speakJa TEXT: speak Japanese text

ITS.isOpen: check if the room is open by using a light sensor

ITS.getLoggedInMembers: get logged in members with student IDs; all the members will automatically get logged out once `ITS.isOpen` returns False

account.register STUDENT_ID ACCOUNT_NAME: register ACCOUNT_NAME associated with STUDENT_ID

account.unregister STUDENT_ID: AUTHORIZED PERSONNEL ONLY

account.getAll: AUTHORIZED PERSONNEL ONLY

ping: return "pong" to tell you the service is up

checkRateLimit: check the rate limit status for the current endpoint

checkServiceStatus: show the current service status; AUTHORIZED PERSONNEL ONLY

getLocalAddress: AUTHORIZED PERSONNEL ONLY

getAddressInfo: AUTHORIZED PERSONNEL ONLY

update: AUTHORIZED PERSONNEL ONLY

stop: AUTHORIZED PERSONNEL ONLY

restart: AUTHORIZED PERSONNEL ONLY\
'''

UNKNOWN_CMD_RESPONSE = '''\
400 Bad Request, RTFM
Command format: cmd arg1 arg2 ...
e.g. "ITS.isOpen"
Type "help" for more details\
'''

api = twitter.Api(
        CONSUMER_KEY,
        CONSUMER_SECRET,
        ACCESS_KEY,
        ACCESS_SECRET,
        sleep_on_rate_limit=True)


def post_update(text):
    try:
        status = api.PostUpdate(text)
    except twitter.error.TwitterError as e:
        print("[-] Error: PostUpdate: {}".format(e))
        status = None
    else:
        print("[*] Posted update: {}".format(status.text))
    finally:
        print("---------------------------")
    return status


def post_dm(text, username):
    try:
        status = api.PostDirectMessage(screen_name=username, text=text)
    except twitter.error.TwitterError as e:
        print("[-] Error: PostDirectMessage: {}".format(e))
        status = None
    else:
        print("[*] Posted DM: {}".format(status.text))
    finally:
        print("---------------------------")
    return status


# post a message
# if not dm post a tweet with 'mention' and a link to the request post
def post_msg(text, username, link=None, dm=True):
    return post_dm(text, username) if dm else post_update("@{} {} {}".format(username, text, link))


def post_forbidden(username, link=None, dm=True):
    post_msg("403 Forbidden", username, link, dm)


def post_wrong_num_of_args(username, link, dm):
    return post_msg("400 Wrong Number of Arguments", username, link, dm)


def respond_to_help(args, username, link, dm):
    post_msg("200 usage:\n" + COMMAND_HELP_TEXT, username, link, dm)


def its_is_open():
    def sampling():
        time.sleep(0.5)
        return light_sensor.isOpen()

    samples = [sampling() for _ in range(9)]
    print("[*] Light sensor: {}".format(samples))
    return samples.count(True) > 4


def respond_to_its_is_open(args, username, link, dm):
    is_open = its_is_open()
    post_msg("200 {}".format(is_open), username, link, dm)


# always send as DMs
def respond_to_its_get_logged_in_members(args, username):
    if not its_is_open():
        access_db.logout_all_members()

    accounts = access_db.get_logged_in_accounts()
    if not accounts:
        post_dm("404 No one logged in", username)
    else:
        post_dm("200 {}".format(" ".join(accounts)), username)


def respond_to_ping(args, username, link, dm):
    post_msg("200 pong", username, link=link, dm=dm)


def respond_to_account_register(args, username, link, dm):
    if len(args) != 2:
        post_wrong_num_of_args(username, link, dm=True)
        return

    student_id = args[0]
    account = args[1]

    if len(student_id) != 8:
        post_dm("400 The Length of a Student ID Must Be 8", username)
        return

    try:
        access_db.register_account(student_id, account)
        post_dm("200 OK", username)
    except sqlite3.Error as e:
        post_dm("500 {}".format(e), username)


def respond_to_account_unregister(args, username, link, dm):
    if len(args) != 1:
        post_wrong_num_of_args(username, link, dm)
        return

    if username in AUTHORIZED_PERSONNEL:
        student_id = args[0]

        try:
            access_db.unregister_account(student_id)
            post_dm("200 OK", username)
        except sqlite3.Error as e:
            post_dm("500 {}".format(e), username)
    else:
        post_forbidden(username, link, dm)


def respond_to_account_get_all(args, username, link, dm):
    if username in AUTHORIZED_PERSONNEL:
        try:
            accounts = access_db.get_accounts()
            post_dm("200 {}".format(accounts), username)
        except sqlite3.Error as e:
            post_dm("500 {}".format(e), username)
    else:
        post_forbidden(username, link, dm)


def respond_to_check_rate_limit(args, username, link, dm):
    url = ("https://api.twitter.com/1.1/direct_messages/events/new.json"
            if dm else "https://api.twitter.com/1.1/statuses/update.json")
    rate_limit = api.CheckRateLimit(url)
    response = "limit={} ramaining={} reset={}".format(
        rate_limit.limit, rate_limit.remaining, rate_limit.reset)

    post_msg("200 " + response, username, link, dm)


def respond_to_check_service_status(args, username, link, dm):
    if username in AUTHORIZED_PERSONNEL:
        proc = subprocess.run(["systemctl", "status", "boushitsu"], stdout=subprocess.PIPE)
        proc_stdout = proc.stdout.decode("utf-8")

        post_dm("200\n{}".format(proc_stdout), username)
    else:
        post_forbidden(username, dm=True)


def respond_to_speak_ja(args, username, link, dm):
    if len(args) == 0:
        post_wrong_num_of_args(username, link, dm)
        return

    post_dm("200 Speaking", username)
    arg = " ".join(args)
    proc = subprocess.run(["speak-ja", arg], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        post_dm("return code: {}".format(proc.returncode), username)


def respond_to_bou(args, username, link, dm):
    if len(args) == 0:
        post_wrong_num_of_args(username, link, dm)
        return

    if username in AUTHORIZED_PERSONNEL:
        post_dm("200 Running", username)
        cmdline = " ".join(args) + " &"
        proc = subprocess.run(cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        post_dm("stdout:\n{}\nstderr:\n{}\nreturn code:{}"
            .format(proc.stdout.decode("utf8"), proc.stderr.decode("utf8"), proc.returncode), username)
    else:
        post_forbidden(username, dm=True)


def get_local_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


# always send as DMs
def respond_to_get_local_address(args, username):
    if username in AUTHORIZED_PERSONNEL:
        local_addr = get_local_address()
        post_dm("200 {}".format(local_addr), username)
    else:
        post_forbidden(username, dm=True)


def respond_to_get_address_info(args, username):
    if username in AUTHORIZED_PERSONNEL:
        proc = subprocess.run(["ip", "address", "show"], stdout=subprocess.PIPE)
        proc_stdout = proc.stdout.decode("utf-8")

        post_dm("200\n{}".format(proc_stdout), username)
    else:
        post_forbidden(username, dm=True)


def restart_process():
    #os.execv("/usr/bin/env", ["/usr/bin/env", "python3"] + sys.argv)
    os.execv("/usr/bin/sudo", ["/usr/bin/sudo", "systemctl", "restart", "boushitsu"])


def respond_to_update(args, username, link, dm):
    if username in AUTHORIZED_PERSONNEL:
        post_msg("200 updating", username, link, dm)

        print("[*] updating: git pull origin master")
        proc = subprocess.run(["git", "pull", "origin", "master"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("[*] updated: returncode={}".format(proc.returncode))
        post_dm("return code: {}".format(proc.returncode), username)
        post_dm("stdout:\n" + proc.stdout.decode("utf8"), username)
        post_dm("stderr:\n" + proc.stderr.decode("utf8"), username)

        if proc.returncode == 0:
            if dm:
                post_dm("200 Restarting", username)
            #post_update("200 Updating [{}] ({}) {}".format(username, datetime.datetime.now(), link))

            print("[!] Restarting due to an 'update' request")
            restart_process()
    else:
        post_forbidden(username, link, dm)


def respond_to_stop(args, username, link, dm):
    if username in AUTHORIZED_PERSONNEL:
        post_msg("200 Bye (^^)/", username, link, dm)

        # it's important to tell everyone the service is stopping
        post_update("200 Bye (^^)/ [{}] ({}) {}".format(username, datetime.datetime.now(), link))

        print("[!] Stopping due to a 'stop' request")
        sys.exit(0)
    else:
        post_forbidden(username, link, dm)


def respond_to_restart(args, username, link, dm):
    if username in AUTHORIZED_PERSONNEL:
        post_msg("200 Restarting", username, link, dm)

        post_update("200 Restarting [{}] ({}) {}".format(username, datetime.datetime.now(), link))

        print("[!] Restarting due to a 'restart' request")
        restart_process()
    else:
        post_forbidden(username, link, dm)


def respond_to_unknown_cmd(username, cmd, link, dm):
    print("[!] Bad Request: {}".format(cmd))
    post_msg(UNKNOWN_CMD_RESPONSE, username, link, dm)


def parse_request_body(body):
    body = body.replace('@' + SCREEN_NAME, '').strip()
    comment_pos = body.find("//")
    return body if comment_pos == -1 else body[:comment_pos].strip()


def parse_command(body):
    request_body = parse_request_body(body)
    cmd = request_body.split()
    return (None if not cmd else cmd[0], cmd[1:])


def respond_to_command(body, username, link, dm):
    print("[*] Request info: username={} body={} link={}".format(username, body, link))

    cmd, args = parse_command(body)
    print("[*] Command: cmd={} args={}".format(cmd, args))

    if cmd == "help":
        respond_to_help(args, username, link, dm)
    elif cmd == "speakJa":
        respond_to_speak_ja(args, username, link, dm)
    elif cmd == "ITS.isOpen":
        respond_to_its_is_open(args, username, link, dm)
    elif cmd == "ITS.getLoggedInMembers":
        respond_to_its_get_logged_in_members(args, username)
    elif cmd == "ping":
        respond_to_ping(args, username, link, dm)
    elif cmd == "account.register":
        respond_to_account_register(args, username, link, dm)
    elif cmd == "account.unregister":
        respond_to_account_unregister(args, username, link, dm)
    elif cmd == "account.getAll":
        respond_to_account_get_all(args, username, link, dm)
    elif cmd == "checkRateLimit":
        respond_to_check_rate_limit(args, username, link, dm)
    elif cmd == "checkServiceStatus":
        respond_to_check_service_status(args, username, link, dm)
    elif cmd == "bou":
        respond_to_bou(args, username, link, dm)
    elif cmd == "getLocalAddress":
        respond_to_get_local_address(args, username)
    elif cmd == "getAddressInfo":
        respond_to_get_address_info(args, username)
    elif cmd == "update":
        respond_to_update(args, username, link, dm)
    elif cmd == "stop":
        respond_to_stop(args, username, link, dm)
    elif cmd == "restart":
        respond_to_restart(args, username, link, dm)
    else:
        respond_to_unknown_cmd(username, cmd, link, dm)


def handle_tweet_create_events(event):
    for tce in event['tweet_create_events']:
        if tce['in_reply_to_screen_name'] == SCREEN_NAME:
            username = tce['user']['screen_name']

            # ignore replies from myself to myself
            if username == SCREEN_NAME:
                return

            body = tce['text']
            link = 'https://twitter.com/' + username + '/status/' + tce['id_str']
            respond_to_command(body, username, link, dm=False)


def handle_direct_message_events(event):
    # ignore DMs from myself to myself
    if len(event['users']) == 1:
        return

    for dme in event['direct_message_events']:
        if dme['type'] == 'message_create':
            sender_id = dme['message_create']['sender_id']
            username = event['users'][sender_id]['screen_name']

            if username == SCREEN_NAME:
                return

            body = dme['message_create']['message_data']['text']
            respond_to_command(body, username, "DM", dm=True)


def handle_account_activity_event(event):
    if 'tweet_create_events' in event:
        handle_tweet_create_events(event)
    elif 'direct_message_events' in event:
        handle_direct_message_events(event)
    #elif 'favorite_events' in event:


def on_connect(client, userdata, flags, respons_code):
    print("[*] Connected to Beebotte: status: {}".format(respons_code))
    client.subscribe(BEEBOTTE_TOPIC)


def on_message(client, userdata, msg):
    event_raw = json.loads(msg.payload.decode("utf-8"))['data'][0]['event']
    event = json.loads(event_raw)
    #print(json.dumps(event))

    handle_account_activity_event(event)


def setup_beebotte_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set("token:{}".format(BEEBOTTE_TOKEN))
    client.tls_set(BEEBOTTE_CACERT)
    client.connect(BEEBOTTE_HOST, port=BEEBOTTE_PORT, keepalive=10)
    return client


def boushitsu_main():
    client = setup_beebotte_mqtt()
    client.loop_forever()


if __name__ == '__main__':
    boushitsu_main()
