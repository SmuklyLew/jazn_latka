from __future__ import annotations

from pathlib import Path

from latka_jazn import cli


def test_mcp_http_cli_is_explicitly_loopback_dev_only(tmp_path: Path, capsys) -> None:
    code = cli.main(["mcp-http", "--root", str(tmp_path), "--json"])
    captured = capsys.readouterr().out
    assert code == 2
    assert "mcp_http_cli_requires_explicit_loopback_dev" in captured


def test_mcp_http_parser_exposes_canonical_operator_command(tmp_path: Path) -> None:
    parser = cli.build_parser()
    ns = parser.parse_args(
        [
            "mcp-http",
            "--root",
            str(tmp_path),
            "--loopback-dev",
            "--host",
            "127.0.0.1",
            "--port",
            "8181",
        ]
    )
    assert ns.command == "mcp-http"
    assert ns.loopback_dev is True
    assert ns.host == "127.0.0.1"
    assert ns.port == 8181
