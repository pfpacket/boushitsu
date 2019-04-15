#!/usr/bin/env python2

import sys
import nfc
import sqlite3

PASORI_S380_PATH = 'usb:054c:06c3'
MEMBERS_DB = 'members.db'

con = sqlite3.connect(MEMBERS_DB)
cursor = con.cursor()


def update_db(student_id):
    #cursor.execute("CREATE TABLE members (id int unique, loggedin bit)");
    try:
        cursor.execute("insert into members (id, loggedin) values (?,?);", (student_id, 1))
    except sqlite3.IntegrityError as _:
        cursor.execute("update members set loggedin = not loggedin where id=:id", {'id':student_id})
    con.commit()
    cursor.execute("select loggedin from members where id=:id", {'id':student_id})
    return cursor.fetchone()[0]


def sc_from_raw(sc):
    return nfc.tag.tt3.ServiceCode(sc >> 6, sc & 0x3f)


def on_startup(targets):
    return targets


def on_connect(tag):
    sc1 = sc_from_raw(0x200B)
    bc1 = nfc.tag.tt3.BlockCode(0, service=0)
    bc2 = nfc.tag.tt3.BlockCode(1, service=0)
    block_data = tag.read_without_encryption([sc1], [bc1, bc2])
    student_id  = block_data[1:9].decode("utf-8")
    #shizudai_id = block_data[24:32].decode("utf-8")

    loggedin = update_db(student_id)
    print("[*] {} {} ITS!".format(student_id, "entering" if loggedin else "leaving"))

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
            'beep-on-connect' : True
        }):
            pass


if __name__ == "__main__":
    main(sys.argv)
