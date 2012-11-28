#!/usr/bin/env python
import sys
import os
import itertools
import re
import random
import pprint
from collections import defaultdict

USER_ID_RE = re.compile(r"voip-(?P<number>[0-9]*)-.*")


def parse_users(dir_id, dir_name, lst):
    res = []
    for f_name in lst:
        matched_id = USER_ID_RE.match(f_name)
        if matched_id is not None:
            res += [(dir_id, matched_id.group('number'), os.path.join(dir_name, f_name), )]
        else:
            print >>sys.stderr, \
                "Warning: file ``%s'' is not named according to the scheme." \
                "Ignoring." % f_name

    return res


def group_dirs(lst):
    res = defaultdict(lambda: [])

    for user, udict in lst.items():
        res[user] = list(itertools.izip_longest(*udict.values()))

    return res


def generate(dirs):
    f_lists = [parse_users(i, x, os.listdir(x)) for (i, x) in enumerate(dirs)]
    lists_by_user = defaultdict(lambda: defaultdict(lambda: []))
    num_dialogs = 0
    for lst in f_lists:
        for d_id, u_id, f_name in lst:
            lists_by_user[u_id][d_id] += [f_name]
            num_dialogs += 1

    lists_by_user_grouped = group_dirs(lists_by_user)

    # generate the resulting list, that always groups together conversations
    # of an interaction of one user across all systems
    res = [l for l in lists_by_user_grouped.values()]
    res = reduce(lambda a, b: a + b, res, [])
    random.shuffle(res)
    res = [[i for i in x if i is not None] for x in res]
    res = reduce(lambda a, b: a + b, res, [])
    """
    while len(lists_by_user_grouped) > 0:
        # pick user
        user = random.randint(0, len(lists_by_user_grouped) - 1)
        curr_user = lists_by_user_grouped.keys()[user]

        udialogs = lists_by_user_grouped[curr_user]
        dialogs = udialogs.pop()

        if len(udialogs) == 0:
            del lists_by_user_grouped[curr_user]

        res += [dialog for dialog in dialogs if dialog is not None]

    #seq = [item[1] for lst in itertools.izip_longest(*f_lists)
    #    for item in lst if item is not None]
    """
    return res

if __name__ == '__main__':
    data_dirs = sys.argv[1:]

    print "\n".join(generate(data_dirs))
