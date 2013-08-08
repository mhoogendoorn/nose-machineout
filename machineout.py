"""
Formats nose output into format easily parsable by machine.
It is intended to be use to integrate nose with your IDE such as Vim.
"""
import os
import re
import textwrap
import traceback
from nose.plugins import Plugin

class DummyStream:

    def write(self, *arg):
        pass

    def writeln(self, *arg):
        pass

    def flush(self):
        pass

doctest_value_pattern = re.compile(
    r'File "([^"]*)", line (\d*), in ([^\n]*)\nFailed example:\n'
    r'\s*([^\n]*)\n(?:(?:Expected:\n(.*)\nGot(?:(?::?\n(.*)\n)|(?: (nothing))))'
    r'|(?:Exception raised:\n(.*)))', re.DOTALL)

class NoseMachineReadableOutput(Plugin):
    """
    Output errors and failures in a machine-readable way.
    """

    name = 'machineout'

    def __init__(self):
        super(NoseMachineReadableOutput, self).__init__()
        self.basepath = os.getcwd()

    def addError(self, test, err):
        self.add_formatted('error', err)

    def addFailure(self, test, err):
        self.add_formatted('fail', err)

    def setOutputStream(self, stream):
        self.stream = stream
        return DummyStream()

    def _calcScore(self, frame):
        """Calculates a score for this stack frame, so that can be used as a
        quality indicator to compare to other stack frames in selecting the
        most developer-friendly one to show in one-line output.

        """
        fname, _, funname, _ = frame
        score = 0.0
        max_score = 7.0  # update this when new conditions are added

        # Being in the project directory means it's one of our own files
        if fname.startswith(self.basepath):
            score += 4

        # Being one of our tests means it's a better match
        if os.path.basename(fname).find('test') >= 0:
            score += 2

        # The check for the `assert' prefix allows the user to extend
        # unittest.TestCase with custom assert-methods, while
        # machineout still returns the most useful error line number.
        if not funname.startswith('assert'):
            score += 1
        return score / max_score

    def _selectBestStackFrame(self, traceback):
        best_score = 0
        best = traceback[-1]   # fallback value
        for frame in traceback:
            curr_score = self._calcScore(frame)
            if curr_score > best_score:
                best = frame
                best_score = curr_score

                # Terminate the walk as soon as possible
                if best_score >= 1:
                    break
        return best

    def add_formatted(self, etype, err):
        exctype, value, tb = err
        value_str = str(value)

        if value_str.startswith(u'Failed doctest test'):
            linesets = self._format_doctests(value_str)
            for etype, fname, lineno, lines in linesets:
                self._write_lines(etype, fname, lineno, lines)
        else:
            fulltb = traceback.extract_tb(tb)
            fname, lineno, funname, msg = self._selectBestStackFrame(fulltb)

            lines = traceback.format_exception_only(exctype, value)
            lines = [line.strip('\n') for line in lines]

            self._write_lines(etype, fname, lineno, lines)


    def _write_lines(self, etype, fname, lineno, lines):
        fname = self._format_testfname(fname)
        prefix = "%s:%d" % (fname, lineno)
        
        if lines:
            self.stream.writeln("%s: %s: %s" % (prefix, etype, lines[0]))

        if len(lines) > 1:
            pad = ' ' * (len(etype) + 1)
            for line in lines[1:]:
                self.stream.writeln("%s: %s %s" % (prefix, pad, line))

    def _format_doctests(self, err_str):
        """
        >>> o = NoseMachineReadableOutput()
        >>> err = '''
        ...          Failed doctest test for foo
        ...            File "/foo.py", line 1, in foo_fn
        ...          
        ...          -------------------------------------------------
        ...          File "/foo.py", line 5, in foo_fn
        ...          Failed example:
        ...              foo_bar()
        ...          Expected:
        ...              foo
        ...          Got nothing
        ...          -------------------------------------------------
        ...          File "/foo.py", line 9, in foo_fn
        ...          Failed example:
        ...              foo_fn()
        ...          Expected:
        ...              foo
        ...          Got:
        ...              bar
        ...          -------------------------------------------------
        ...          File "/foo.py", line 10, in foo_fn
        ...          Failed example:
        ...              print(bar)
        ...          Exception raised:
        ...              Traceback (most recent call last):
        ...                ...
        ...              NameError: name 'bar' is not defined
        ...       '''
        >>> err = textwrap.dedent(err)
        >>> list(o._format_doctests(err)) # doctest: +NORMALIZE_WHITESPACE
        [('fail', '/foo.py', 5, ["expected '    foo' but got nothing"]),
         ('fail', '/foo.py', 9, ["expected '    foo' but got '    bar'"]),
         ('error', '/foo.py', 10,
          ["NameError: name 'bar' is not defined",
           'Traceback (most recent call last):',
           '  ...'])]
        """
        err_parts = re.split('-+', err_str)

        for part in err_parts[1:]:
            m = doctest_value_pattern.search(part)
            fname, lineno, funname, example, expected, got, got_nothing, exc = m.groups()
            lineno = int(lineno)
            if exc:
                etype = 'error'
                lines = textwrap.dedent(exc.strip('\n')).split('\n')
                lines.insert(0, lines.pop())
            elif got_nothing:
                etype = 'fail'
                lines = ["expected %s but got nothing" % (repr(expected))]
            else:
                etype = 'fail'
                lines = ["expected %s but got %s" % (repr(expected),
                                                     repr(got))]
            yield etype, fname, lineno, lines

        

    def _format_testfname(self, fname):
        if fname.startswith(self.basepath):
            return fname[len(self.basepath) + 1:]

        return fname
