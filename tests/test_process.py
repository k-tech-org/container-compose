import signal

from container_compose_proxy.process import terminate_process_group


class FakeProcess:
    pid = 12345

    def __init__(self) -> None:
        self.waited = False

    def wait(self) -> None:
        self.waited = True


def test_terminate_process_group_uses_sigkill(monkeypatch) -> None:
    calls = []

    def fake_killpg(pid, sig):
        calls.append((pid, sig))

    proc = FakeProcess()
    monkeypatch.setattr("container_compose_proxy.process.os.killpg", fake_killpg)

    terminate_process_group(proc)

    assert calls == [(12345, signal.SIGKILL)]
    assert proc.waited
