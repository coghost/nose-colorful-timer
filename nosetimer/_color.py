# -*- coding: utf-8 -*-
"""color"""

R = '\x1b[0;91m{}\x1b[0m'  # red
G = '\x1b[0;92m{}\x1b[0m'  # green
Y = '\x1b[0;93m{}\x1b[0m'  # yellow
B = '\x1b[0;94m{}\x1b[0m'  # blue
F = '\x1b[0;95m{}\x1b[0m'  # fuchsia
C = '\x1b[0;96m{}\x1b[0m'  # cyan
W = '\x1b[0;97m{}\x1b[0m'  # white

# OK, FAIL = '✔', '✘'
OK, FAIL = '☕️', '🐛'
SEPARATOR = '○'


def colorful(num, precision=2):
    if isinstance(num, float):
        num = round(num, precision)

    _fmt = '{:>5.2f}%'
    rgb = [5, 20, 75]
    if num <= rgb[0]:
        return G.format(_fmt.format(num))
    elif num <= rgb[1]:
        return Y.format(_fmt.format(num))
    elif num <= rgb[2]:
        return R.format(_fmt.format(num))
    else:
        return F.format(_fmt.format(num))
