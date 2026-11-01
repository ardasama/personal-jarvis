"""POSIX escalation must finish before Python logging teardown."""

import signal

from jarvis.core import process_tree


def test_posix_escalation_finishes_before_interpreter_shutdown(monkeypatch):
    sent = []
    timers = []
    monkeypatch.setattr(process_tree, "_killpg", lambda pgid, sig: sent.append((pgid, sig)))

    class PendingTimer:
        def __init__(self, delay, callback, args):
            assert delay == process_tree.GRACE_S
            self.daemon = None
            self.callback = callback
            self.args = args

        def start(self):
            timers.append(self)

    monkeypatch.setattr(process_tree.threading, "Timer", PendingTimer)
    tree = process_tree._PosixProcessGroup("test")
    tree._pgids.add(30001)
    tree.close()
    assert sent == [(30001, signal.SIGTERM)]
    assert len(timers) == 1
    assert timers[0].daemon is False
    timers[0].callback(*timers[0].args)
    assert sent[-1] == (30001, process_tree._SIGKILL)
    tree.close()
    assert len(timers) == 1
