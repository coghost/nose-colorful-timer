import json
import logging
import os
import sys
import re
import timeit

from nose.plugins import Plugin
from ._color import *

try:
    import Queue
except ImportError:
    import queue as Queue

from collections import OrderedDict

try:
    import termcolor
except ImportError:
    termcolor = None  # noqa

try:
    import colorama

    TERMCOLOR2COLORAMA = {
        'green': colorama.Fore.GREEN,
        'yellow': colorama.Fore.YELLOW,
        'red': colorama.Fore.RED,
    }
except ImportError:
    colorama = None

# define constants
IS_NT = os.name == 'nt'

# Windows and Python 2.7 multiprocessing don't marry well.
_results_queue = None
if not IS_NT:
    import multiprocessing
    from multiprocessing import queues


    class TimerQueue(queues.Queue):
        """A portable implementation of multiprocessing.Queue.

        Because of multithreading / multiprocessing semantics, Queue.qsize()
        may raise the NotImplementedError exception on Unix platforms like
        Mac OS X where sem_getvalue() is not implemented. This subclass
        addresses this problem by using a synchronized shared counter
        (initialized to zero) and increasing / decreasing its value every time
        the put() and get() methods are called, respectively. This not only
        prevents NotImplementedError from being raised, but also allows us to
        implement a reliable version of both qsize() and empty().
        """

        def __init__(self, *args, **kwargs):
            if hasattr(multiprocessing, 'get_context'):
                kwargs.update(ctx=multiprocessing.get_context())
            super(TimerQueue, self).__init__(*args, **kwargs)
            self.size = multiprocessing.Value('i', 0)

        def put(self, *args, **kwargs):
            with self.size.get_lock():
                self.size.value += 1
            super(TimerQueue, self).put(*args, **kwargs)

        def get(self, *args, **kwargs):
            with self.size.get_lock():
                self.size.value -= 1
            return super(TimerQueue, self).get(*args, **kwargs)

        def qsize(self):
            """Reliable implementation of multiprocessing.Queue.qsize()."""
            return self.size.value

        def empty(self):
            """Reliable implementation of multiprocessing.Queue.empty()."""
            return not self.qsize()


    _results_queue = TimerQueue()

log = logging.getLogger('nose.plugin.timer')


def _colorize(val, color):
    """Colorize a string using termcolor or colorama.

    If any of them are available.
    """
    if termcolor is not None:
        val = termcolor.colored(val, color)
    elif colorama is not None:
        val = TERMCOLOR2COLORAMA[color] + val + colorama.Style.RESET_ALL

    return val


class TimerPlugin(Plugin):
    """This plugin provides test timings."""

    name = 'timer'
    score = 1

    time_format = re.compile(r'^(?P<time>\d+)(?P<units>s|ms)?$')
    _timed_tests = {}

    _COLOR_TO_FILTER = {
        'green': 'ok',
        'yellow': 'warning',
        'red': 'error',
    }

    def __init__(self, *args, **kwargs):
        super(TimerPlugin, self).__init__(*args, **kwargs)
        self._threshold = None

    def _time_taken(self):
        if hasattr(self, '_timer'):
            taken = timeit.default_timer() - self._timer
        else:
            # Test died before it ran (probably error in setup()) or
            # success/failure added before test started probably due to custom
            # `TestResult` munging.
            taken = 0.0
        return taken

    def _parse_time(self, value):
        """Parse string time representation to get number of milliseconds.
        Raises the ``ValueError`` for invalid format.
        """
        try:
            # Default time unit is a second, we should convert it to milliseconds.
            return int(value) * 1000
        except ValueError:
            # Try to parse if we are unlucky to cast value into int.
            m = self.time_format.match(value)
            if not m:
                raise ValueError("Could not parse time represented by '{t}'".format(t=value))
            time = int(m.group('time'))
            if m.group('units') != 'ms':
                time *= 1000
            return time

    @staticmethod
    def _parse_filter(value):
        """Parse timer filters."""
        return value.split(',') if value is not None else None

    def configure(self, options, config):
        """Configures the test timer plugin."""
        super(TimerPlugin, self).configure(options, config)
        self.config = config
        if self.enabled:
            self.timer_top_n = int(options.timer_top_n)
            self.timer_ok = self._parse_time(options.timer_ok)
            self.timer_warning = self._parse_time(options.timer_warning)
            self.timer_filter = self._parse_filter(options.timer_filter)
            self.timer_fail = options.timer_fail
            self.timer_no_color = True
            self.json_file = options.json_file

            # Windows + nosetests does not support colors (even with colorama).
            if not IS_NT:
                self.timer_no_color = options.timer_no_color

            # determine if multiprocessing plugin enabled
            self.multiprocessing_enabled = bool(getattr(options, 'multiprocess_workers', False))

    def startTest(self, test):
        """Initializes a timer before starting a test."""
        self._timer = timeit.default_timer()

    def report(self, stream):
        """Report the test times."""
        if not self.enabled:
            return

        # if multiprocessing plugin enabled - get items from results queue
        if self.multiprocessing_enabled:
            for i in range(_results_queue.qsize()):
                try:
                    k, v, s = _results_queue.get(False)
                    self._timed_tests[k] = {
                        'time': v,
                        'status': s,
                    }
                except Queue.Empty:
                    pass

        if ORDER:
            d = sorted(self._timed_tests.items(), key=lambda item: item[1]['time'], reverse=ORDER == -1)
        else:
            d = self._timed_tests.items()

        if self.json_file:
            dict_type = OrderedDict if self.timer_top_n else dict
            with open(self.json_file, 'w') as f:
                json.dump({'tests': dict_type((k, v) for k, v in d)}, f)

        total_time = sum([vv['time'] for kk, vv in d])

        # the number of tests used for `(index/total): (1/12)`
        self.total_tests = len(d)
        stream.writeln(C.format(SEPARATOR_U * (64 // len(SEPARATOR_U))))
        for i, (test, time_and_status) in enumerate(d):
            time_taken = time_and_status['time']
            status = time_and_status['status']
            if i < self.timer_top_n or self.timer_top_n == -1:
                color = self._get_result_color(time_taken)
                percent = 0 if total_time == 0 else time_taken / total_time * 100
                line = self._format_report_line(
                    test=test,
                    time_taken=time_taken,
                    color=color,
                    status=status,
                    percent=percent,
                    index=i,
                )
                _filter = self._COLOR_TO_FILTER.get(color)
                if self.timer_filter is None or _filter is None or _filter in self.timer_filter:
                    stream.writeln(line)
        stream.writeln(C.format(SEPARATOR_D * (64 // len(SEPARATOR_D))))

    def _get_result_color(self, time_taken):
        """Get time taken result color."""
        time_taken_ms = time_taken * 1000
        if time_taken_ms <= self.timer_ok:
            color = 'green'
        elif time_taken_ms <= self.timer_warning:
            color = 'cyan'
        else:
            color = 'yellow'

        return color

    @property
    def threshold(self):
        """Get maximum test time allowed when --timer-fail option is used."""
        if self._threshold is None:
            self._threshold = {
                'error': self.timer_warning,
                'warning': self.timer_ok,
            }[self.timer_fail]
        return self._threshold

    def _colored_time(self, time_taken, color=None):
        """Get formatted and colored string for a given time taken."""
        if self.timer_no_color:
            return "{0:>7.4f}s".format(time_taken)

        return _colorize("{0:>7.4f}s".format(time_taken), color)

    @staticmethod
    def _shorten_dir():
        # rm file/module/package in sys.argv[-1]
        try:
            params = [param for param in sys.argv if '.py' in param] or sys.argv
            params = [param for param in params if '/' in param][-1].replace('.py', '')
            params = [x for x in params.split('/') if x]
            return params
        except:
            return ''

    def _format_report_line(self, test, time_taken, color, status, percent, index):
        """Format a single report line."""
        _hint_num = '%{}s'.format(len(str(self.total_tests))) % (index + 1)
        _shorten = self._shorten_dir()
        test = test.replace('.'.join(_shorten), '')
        if test.startswith('.'):
            test = test[1:]
        if status == 'success':
            status = G.format('[' + OK + ']')
            index = G.format('({}/{})'.format(_hint_num, self.total_tests))
        else:
            status = R.format('[' + FAIL + ']')
            index = R.format('({}/{})'.format(_hint_num, self.total_tests))
            test = R.format(test)
        percent = colorful(percent)
        return "{} {} {} {} {}".format(
            index, status, self._colored_time(time_taken, color), percent, test,
        )

    def _register_time(self, test, status=None):
        time_taken = self._time_taken()
        if self.multiprocessing_enabled:
            _results_queue.put((test.id(), time_taken, status))

        self._timed_tests[test.id()] = {
            'time': time_taken,
            'status': status,
        }
        return time_taken

    def addError(self, test, err, capt=None):
        """Called when a test raises an uncaught exception."""
        self._register_time(test, 'error')

    def addFailure(self, test, err, capt=None, tb_info=None):
        """Called when a test fails."""
        self._register_time(test, 'fail')

    def addSuccess(self, test, capt=None):
        """Called when a test passes."""
        time_taken = self._register_time(test, 'success')
        if self.timer_fail is not None and time_taken * 1000.0 > self.threshold:
            test.fail('Test was too slow (took {0:0.4f}s, threshold was '
                      '{1:0.4f}s)'.format(time_taken, self.threshold / 1000.0))

    def prepareTestResult(self, result):
        """Called before the first test is run."""

        def _add_success(result, test):
            """Called when a test passes."""
            if result.showAll:
                output = 'ok'
                time_taken = self._timed_tests.get(test.id())['time']
                if time_taken is not None:
                    color = self._get_result_color(time_taken)
                    output += ' ({0})'.format(self._colored_time(time_taken, color))
                result.stream.writeln(output)
            elif result.dots:
                result.stream.write('.')
                result.stream.flush()

        # monkeypatch the result
        result.addSuccess = lambda test: _add_success(result, test)
        result._timed_tests = self._timed_tests

    def options(self, parser, env=os.environ):
        """Register commandline options."""
        super(TimerPlugin, self).options(parser, env)

        # timer top n
        parser.add_option(
            "--timer-top-n",
            action="store",
            default="-1",
            dest="timer_top_n",
            help=(
                "When the timer plugin is enabled, only show the N tests that "
                "consume more time. The default, -1, shows all tests."
            ),
        )

        parser.add_option(
            "--timer-json-file",
            action="store",
            default=None,
            dest="json_file",
            help=(
                "Save the results of the timing and status of each tests in "
                "said Json file."
            ),
        )

        _time_units_help = ("Default time unit is a second, but you can set "
                            "it explicitly (e.g. 1s, 500ms)")

        # timer ok
        parser.add_option(
            "--timer-ok",
            action="store",
            default=1,
            dest="timer_ok",
            help=(
                "Normal execution time. Such tests will be highlighted in "
                "green. {units_help}.".format(units_help=_time_units_help)
            ),
        )

        # time warning
        parser.add_option(
            "--timer-warning",
            action="store",
            default=3,
            dest="timer_warning",
            help=(
                "Warning about execution time to highlight slow tests in "
                "yellow. Tests which take more time will be highlighted in "
                "red. {units_help}.".format(units_help=_time_units_help)
            ),
        )

        # Windows + nosetests does not support colors (even with colorama).
        if not IS_NT:
            parser.add_option(
                "--timer-no-color",
                action="store_true",
                default=False,
                dest="timer_no_color",
                help="Don't colorize output (useful for non-tty output).",
            )

        # timer filter
        parser.add_option(
            "--timer-filter",
            action="store",
            default=None,
            dest="timer_filter",
            help="Show filtered results only (ok,warning,error).",
        )

        # timer fail
        parser.add_option(
            "--timer-fail",
            action="store",
            default=None,
            dest="timer_fail",
            choices=('warning', 'error'),
            help="Fail tests that exceed a threshold (warning,error)",
        )
