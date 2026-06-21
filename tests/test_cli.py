from unittest.mock import patch

from container_compose_proxy.cli import main


def test_main_rejects_missing_compose_command_without_starting_engine(capsys) -> None:
    with (
        patch("container_compose_proxy.cli.ensure_engine") as ensure_engine,
        patch("container_compose_proxy.cli.run_compose") as run_compose,
    ):
        status = main(["-f", "tests/fixtures/basic/compose.yml"])

    assert status == 2
    assert not ensure_engine.called
    assert not run_compose.called
    assert "compose command required" in capsys.readouterr().err
