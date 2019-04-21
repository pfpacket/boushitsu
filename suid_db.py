#!/usr/bin/env python2

import sys
import nfc
import sqlite3

PASORI_S380_PATH = 'usb:054c:06c3'
MEMBERS_DB = 'members.db'

con = sqlite3.connect(MEMBERS_DB)
cursor = con.cursor()

ID2ACCOUNT_DB = 'id2account.db'
idmap_con = sqlite3.connect(ID2ACCOUNT_DB)
idmap_cursor = idmap_con.cursor()


def update_db(student_id):
    #cursor.execute("CREATE TABLE members (id INT UNIQUE, loggedin BIT)");
    try:
        cursor.execute("INSERT INTO members (id, loggedin) VALUES (?,?);", (student_id, 1))
    except sqlite3.IntegrityError as _:
        cursor.execute("UPDATE members SET loggedin = NOT loggedin WHERE id=:id", {'id': student_id})
    con.commit()
    cursor.execute("SELECT loggedin FROM members WHERE id=:id", {'id': student_id})
    return cursor.fetchone()[0]


def id2account(student_id):
    idmap_cursor.execute("SELECT account FROM idmap WHERE id=:id", {'id': student_id})
    account = idmap_cursor.fetchone()
    return (student_id[:4] + "****") if account is None else ("@" + account[0])


def sc_from_raw(sc):
    return nfc.tag.tt3.ServiceCode(sc >> 6, sc & 0x3f)


def on_startup(targets):
    return targets


def on_connect(tag):
    try:
        sc1 = sc_from_raw(0x200B)
        bc1 = nfc.tag.tt3.BlockCode(0, service=0)
        bc2 = nfc.tag.tt3.BlockCode(1, service=0)
        block_data = tag.read_without_encryption([sc1], [bc1, bc2])
        student_id = block_data[1:9].decode("utf-8")

        loggedin = update_db(student_id)
        account = id2account(student_id)
        print("[*] {} {} ITS!".format(student_id if account is None else account, "entering" if loggedin else "leaving"))
    except:
        print("[-] Error: not a student card")
        return False

    return True


def on_release(tag):
    pass


def main(args):
    # Use PaSoRi RC-S380
    with nfc.ContactlessFrontend(PASORI_S380_PATH) as clf:
        print clf
        while clf.connect(rdwr={
            'on-startup': on_startup,
            'on-connect': on_connect,
            'on-release': on_release,
        }):
            pass


if __name__ == "__main__":
    main(sys.argv)
