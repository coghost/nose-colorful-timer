# -*- coding: utf-8 -*-
"""color"""
import os

R = '\x1b[0;91m{}\x1b[0m'  # red
G = '\x1b[0;92m{}\x1b[0m'  # green
Y = '\x1b[0;93m{}\x1b[0m'  # yellow
B = '\x1b[0;94m{}\x1b[0m'  # blue
F = '\x1b[0;95m{}\x1b[0m'  # fuchsia
C = '\x1b[0;96m{}\x1b[0m'  # cyan
W = '\x1b[0;97m{}\x1b[0m'  # white

# OK, FAIL = '✔', '✘'
OK, FAIL = '☕️', '🐛'
SEPARATOR_U = '○'
SEPARATOR_D = '○'
ORDER = 0


def load_cfg():
    lines = ''
    _cfg = os.path.expanduser('~/.nose_timer_rc')
    if os.path.exists(_cfg):
        with open(_cfg) as fp:
            lines = fp.read()
    if lines:
        lines = [x for x in lines.split('\n') if x and not x.startswith('#')]
    for line in lines:
        if line.startswith('ok_fail'):
            global OK, FAIL
            OK, FAIL = line.split('=')[-1].split(', ')
        if line.startswith('separator'):
            global SEPARATOR_U, SEPARATOR_D
            sep = line.split('=')[-1]
            sep = sep.split(',')
            if len(sep) == 1:
                SEPARATOR_U = sep
                SEPARATOR_D = sep
            else:
                SEPARATOR_U = sep[0]
                SEPARATOR_D = sep[1]
        if line.startswith('order'):
            global ORDER
            ORDER = int(line.split('=')[-1])


def colorful(num, precision=2):
    if isinstance(num, float):
        num = round(num, precision)

    _fmt = '{:>5.2f}%'
    rgb = [5, 20, 75]
    if num <= rgb[0]:
        return G.format(_fmt.format(num))
    elif num <= rgb[1]:
        return C.format(_fmt.format(num))
    elif num <= rgb[2]:
        return Y.format(_fmt.format(num))
    else:
        return R.format(_fmt.format(num))


load_cfg()
