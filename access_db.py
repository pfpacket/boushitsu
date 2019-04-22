#!/usr/bin/env python3

import sqlite3

MEMBERS_DB = 'members.db'
members_con = sqlite3.connect(MEMBERS_DB)
members_cursor = members_con.cursor()

ID2ACCOUNT_DB = 'id2account.db'
idmap_con = sqlite3.connect(ID2ACCOUNT_DB)
idmap_cursor = idmap_con.cursor()

#
# assuming: Twitter accounts
#


def get_logged_in_ids():
    members_cursor.execute("SELECT id FROM members WHERE loggedin=1")
    return list(map(lambda id: id[0], members_cursor.fetchall()))


def id2account(student_id):
    idmap_cursor.execute("SELECT account FROM idmap WHERE id=:id", {'id': student_id})
    account = idmap_cursor.fetchone()
    return (student_id[:4] + "****") if account is None else ("@" + account[0])


def get_logged_in_accounts():
    return [id2account(id) for id in get_logged_in_ids()]


def logout_all_members():
    members_cursor.execute("UPDATE members SET loggedin = 0");
    members_con.commit()


if __name__ == '__main__':
    print(get_logged_in_ids())
    accounts = get_logged_in_accounts()
    if not accounts:
        print("404 No one logged in")
    else:
        print("200 {}".format(" ".join(accounts)))
