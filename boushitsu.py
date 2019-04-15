#!/usr/bin/env python3

import os
import sys
import json
import time
import datetime
import twitter
import paho.mqtt.client as mqtt

import light_sensor
import access_db

from dotenv import load_dotenv
load_dotenv()

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
ITS.isOpen(): check if the room is open by using a light sensor
checkRateLimit(): check the rate limit status for the current endpoint
ping(): return "pong" to tell you the service is up
help(): show the available commands and the corresponding usage
stop(): AUTHORIZED PERSONNEL ONLY
restart(): AUTHORIZED PERSONNEL ONLY\
'''

api = twitter.Api(
        CONSUMER_KEY,
        CONSUMER_SECRET,
        ACCESS_KEY,
        ACCESS_SECRET,
        sleep_on_rate_limit=True)


def its_is_open():
    def sampling():
        time.sleep(0.5)
        return light_sensor.isOpen()

    samples = [sampling() for _ in range(9)]
    print("[*] Light sensor: {}".format(samples))
    return samples.count(True) > 4


def post_update(text):
    try:
        status = api.PostUpdate(text)
    except twitter.error.TwitterError as e:
        print("[-] PostUpdate error: {}".format(e))
    else:
        print("[*] Posted update: {}".format(status.text))
    finally:
        print("---------------------------")
    return status


def post_dm(username, text):
    try:
        status = api.PostDirectMessage(screen_name=username, text=text)
    except twitter.error.TwitterError as e:
        print("[-] PostUpdate error: {}".format(e))
    else:
        print("[*] Posted DM: {}".format(status.text))
    finally:
        print("---------------------------")
    return status


def response_its_is_open(username, link, dm):
    is_open = its_is_open()
    if dm:
        post_dm(username, "200 {}".format(is_open))
    else:
        post_update("@{} 200 {} {}".format(username, is_open, link))


def response_get_logged_in_members(username, link, dm):
    # Always send as DMs
    accounts = access_db.get_logged_in_accounts()
    if not accounts:
        post_dm(username, "404 No one logged-in")
    else:
        post_dm(username, "200 {}".format(" ".join(accounts)))


def response_check_rate_limit(username, link, dm):
    url = ('https://api.twitter.com/1.1/direct_messages/events/new.json'
            if dm else 'https://api.twitter.com/1.1/statuses/update.json')
    rate_limit = api.CheckRateLimit(url)
    response = "limit={} ramaining={} reset={}".format(
        rate_limit.limit, rate_limit.remaining, rate_limit.reset)

    if dm:
        post_dm(username, "200 {}".format(response))
    else:
        post_update("@{} 200 {} {}".format(username, response, link))


def response_ping(username, link, dm):
    if dm:
        post_dm(username, "200 pong")
    else:
        post_update("@{} 200 pong {}".format(username, link))


def response_help(username, link, dm):
    if dm:
        post_dm(username, "200 usage:\n" + COMMAND_HELP_TEXT)
    else:
        post_update("@{} 200 usage:\n{} {}".format(username, COMMAND_HELP_TEXT, link))


def response_forbidden(username, link, dm):
    if dm:
        post_dm(username, "403 Forbidden")
    else:
        post_update("@{} 403 Forbidden {}".format(username, link))


def response_stop(username, link, dm):
    if username in AUTHORIZED_PERSONNEL:
        if dm:
            post_dm(username, "200 Bye (^^)/")

        # it's important to tell everyone the service is stopping
        post_update("200 Bye (^^)/ [{}] ({}) {}".format(username, datetime.datetime.now(), link))
        print("[!] Stop due to a 'stop' command")

        sys.exit(0)
    else:
        response_forbidden(username, link, dm)


def response_restart(username, link, dm):
    if username in AUTHORIZED_PERSONNEL:
        if dm:
            post_dm(username, "200 Restarting")

        post_update("200 Restarting [{}] ({}) {}".format(username, datetime.datetime.now(), link))
        print("[!] Restart due to a 'restart' command")

        os.execv("/usr/bin/env", ["/usr/bin/env", "python3"] + sys.argv)
    else:
        response_forbidden(username, link, dm)


def response_unknown_cmd(username, cmd, link, dm):
    print("[!] Bad Request: {}".format(cmd))
    if dm:
        post_dm(username, "400 Bad Request")
    else:
        post_update("@{} 400 Bad Request {}".format(username, link))


def parse_its_cmd(body):
    body = body.replace('@boushitsu', '').strip()
    comment_pos = body.find("//")
    return body if comment_pos == -1 else body[:comment_pos].strip()


def handle_its_cmd(username, body, link, dm):
    print("[*] Request info: username={} body={} link={}".format(username, body, link))

    cmd = parse_its_cmd(body)
    print("[*] Command: {}".format(cmd))

    if cmd == "ITS.isOpen()":
        response_its_is_open(username, link, dm)
    elif cmd == "getLoggedInMembers()":
        response_get_logged_in_members(username, link, dm)
    elif cmd == "checkRateLimit()":
        response_check_rate_limit(username, link, dm)
    elif cmd == "ping()":
        response_ping(username, link, dm)
    elif cmd == "help()":
        response_help(username, link, dm)
    elif cmd == "stop()":
        response_stop(username, link, dm)
    elif cmd == "restart()":
        response_restart(username, link, dm)
    else:
        response_unknown_cmd(username, cmd, link, dm)


def handle_tweet_create_events(event):
    for tce in event['tweet_create_events']:
        if tce['in_reply_to_screen_name'] == SCREEN_NAME:
            username = tce['user']['screen_name']

            # ignore replies from myself to myself
            if username == SCREEN_NAME:
                return

            body = tce['text']
            link = 'https://twitter.com/' + username + '/status/' + tce['id_str']
            handle_its_cmd(username, body, link, dm=False)


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
            handle_its_cmd(username, body, "DM", dm=True)


def handle_account_activity_event(event):
    if 'tweet_create_events' in event:
        handle_tweet_create_events(event)
    elif 'direct_message_events' in event:
        handle_direct_message_events(event)
    #elif 'favorite_events' in event:


def on_connect(client, userdata, flags, respons_code):
    print("[*] Connected to Beebotte: status: {0}".format(respons_code))
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
    client.username_pw_set("token:%s" % BEEBOTTE_TOKEN)
    client.tls_set(BEEBOTTE_CACERT)
    client.connect(BEEBOTTE_HOST, port=BEEBOTTE_PORT, keepalive=60)
    return client


def boushitsu_main():
    client = setup_beebotte_mqtt()
    client.loop_forever()


if __name__ == '__main__':
    boushitsu_main()
