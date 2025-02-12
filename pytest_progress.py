import multiprocessing

import pytest
from _pytest.terminal import TerminalReporter


class Counter(object):
    def __init__(self):
        self.val = multiprocessing.Value('i', 0)

    def increment(self, n=1):
        with self.val.get_lock():
            self.val.value += n

    def __iadd__(self, other):
        self.increment(other)
        return self

    @property
    def value(self):
        return self.val.value


def pytest_collection_finish(session):
    terminal_reporter = session.config.pluginmanager.getplugin('terminalreporter')
    if terminal_reporter:
        terminal_reporter.tests_count = len(session.items)


try:
    import xdist
except ImportError:
    pass
else:
    from distutils.version import LooseVersion

    xdist_version = LooseVersion(xdist.__version__)
    if xdist_version >= LooseVersion("1.14"):
        def pytest_xdist_node_collection_finished(node, ids):
            terminal_reporter = node.config.pluginmanager.getplugin('terminalreporter')
            if terminal_reporter:
                terminal_reporter.tests_count = len(ids)


def pytest_addoption(parser):
    group = parser.getgroup("terminal reporting")
    group.addoption('--showprogress', '--show-progress',
                    action="count",
                    default=0,
                    dest="progress",
                    help="Prints test progress on the terminal.")

    group.addoption('--showprogresssample', '--show-progress-sample',
                    type=int,
                    default=1,
                    dest="count_sample",
                    help="Skips printing every single test")


@pytest.mark.trylast
def pytest_configure(config):
    progress = config.option.progress

    if progress and not getattr(config, 'slaveinput', None):
        standard_reporter = config.pluginmanager.getplugin('terminalreporter')
        instaprogress_reporter = ProgressTerminalReporter(standard_reporter, config.option.count_sample)

        config.pluginmanager.unregister(standard_reporter)
        config.pluginmanager.register(instaprogress_reporter, 'terminalreporter')


class ProgressTerminalReporter(TerminalReporter):

    def __init__(self, reporter, print_every_x_pass=1):
        TerminalReporter.__init__(self, reporter.config, )
        self.print_every_x_pass = print_every_x_pass
        self._tw = reporter._tw
        self.tests_count = 0
        self.tests_taken = Counter()
        self.pass_count = Counter()
        self.fail_count = Counter()
        self.skip_count = Counter()
        self.xpass_count = Counter()
        self.xfail_count = Counter()
        self.error_count = Counter()
        self.rerun_count = Counter()

    def append_rerun(self, report):

        if report.failed:
            self.append_failure(report)

        if report.when == "call" and report.rerun:  # ignore setup/teardown
            self.rerun_count += 1

        elif report.skipped:
            self.append_skipped(report)

    def append_pass(self, report):

        if hasattr(report, "wasxfail"):
            self.xpass_count += 1
            self.tests_taken += 1

        else:
            self.pass_count += 1
            self.tests_taken += 1

        if hasattr(report, 'rerun'):
            if report.rerun:
                self.rerun_count += 1

    def append_failure(self, report):

        if report.when == "call":
            if hasattr(report, "wasxfail"):
                self.xpass_count += 1
                self.tests_taken += 1

            else:
                self.fail_count += 1
                self.tests_taken += 1

        else:
            self.append_error()

    def append_error(self):

        self.error_count += 1
        self.tests_taken += 1

    def append_skipped(self, report):

        if hasattr(report, "wasxfail"):
            self.xfail_count += 1
            self.tests_taken += 1

        else:
            self.skip_count += 1
            self.tests_taken += 1

    def pytest_report_teststatus(self, report):
        """ Called after every test for test case status"""
        if report.passed and report.when == "call":
            self.append_pass(report)

        elif hasattr(report, 'rerun'):
            self.append_rerun(report)

        elif report.failed:
            self.append_failure(report)

        elif report.skipped:
            self.append_skipped(report)

        if report.when in ("teardown"):
            if not report.failed:  # Print failures
                if self.tests_taken.value != 1 and self.tests_taken.value != self.tests_count:  # Print first/last test
                    if self.pass_count.value % self.print_every_x_pass != 0:  # Skip every x pass
                        return
            status = (self.tests_taken.value, self.tests_count, self.pass_count.value, self.fail_count.value,
                      self.skip_count.value, self.xpass_count.value, self.xfail_count.value, self.error_count.value,
                      self.rerun_count.value)

            msg = "%d of %d completed, %d Pass, %d Fail, %d Skip, %d XPass, %d XFail, %d Error, %d ReRun" % (status)
            self.write_sep("_", msg)

    def pytest_collectreport(self, report):
        # Show errors occurred during the collection instantly.
        TerminalReporter.pytest_collectreport(self, report)
        if report.failed:
            self.rewrite("")  # erase the "collecting" message
            self.print_failure(report)

    def pytest_runtest_logreport(self, report):
        # Show failures and errors occuring during running a test
        # instantly.
        TerminalReporter.pytest_runtest_logreport(self, report)
        if (report.failed or report.outcome == "rerun") and not hasattr(report, 'wasxfail'):
            if self.verbosity <= 0:
                self._tw.line()
            self.print_failure(report)

    def summary_failures(self):
        # Prevent failure summary from being shown since we already
        # show the failure instantly after failure has occured.
        pass

    def summary_errors(self):
        # Prevent error summary from being shown since we already
        # show the error instantly after error has occured.
        pass

    def print_failure(self, report):
        if self.config.option.tbstyle != "no":
            if self.config.option.tbstyle == "line":
                line = self._getcrashline(report)
                self.write_line(line)
            else:
                msg = self._getfailureheadline(report)
                if not hasattr(report, 'when'):
                    msg = "ERROR collecting " + msg
                elif report.when == "setup":
                    msg = "ERROR at setup of " + msg
                elif report.when == "teardown":
                    msg = "ERROR at teardown of " + msg
                self.write_sep("_", msg)
                if not self.config.getvalue("usepdb"):
                    self._outrep_summary(report)
