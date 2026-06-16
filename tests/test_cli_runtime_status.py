"""Phase 22B tests: scripts/runtime_status.py CLI (read-only diagnostics).

驗證重點：
- CLI 預設為 human-readable output
- --json-report 輸出合法 JSON
- 不支援 --apply（無此 flag）
- CLI 不建立 runtime/rip.db
- script 可 import 無 side effects
- exit code 0：成功取得狀態
- exit code 1：非預期錯誤
"""

from __future__ import annotations

import json
from unittest.mock import patch

import app.core.config as cfg


def test_cli_default_human_readable_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    from scripts.runtime_status import main

    rc = main([])

    assert rc == 0
    captured = capsys.readouterr()
    assert "RIP runtime status" in captured.out
    assert "transaction log backend" in captured.out
    assert "approval store backend" in captured.out


def test_cli_json_report_valid_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(cfg.settings, "TRANSACTION_LOG_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")

    from scripts.runtime_status import main

    rc = main(["--json-report"])

    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["transaction_log_backend"] == "json"
    assert data["approval_store_backend"] == "json"
    assert "approvals_json" in data
    assert "sqlite" in data


def test_cli_does_not_create_rip_db(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    from scripts.runtime_status import main

    main([])
    main(["--json-report"])

    assert not (tmp_path / "rip.db").exists()


def test_cli_apply_flag_not_supported():
    import pytest

    from scripts.runtime_status import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--apply"])


def test_cli_unexpected_error_returns_exit_1(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    from scripts.runtime_status import main

    with patch(
        "app.core.runtime_status.collect_runtime_status",
        side_effect=RuntimeError("boom"),
    ):
        rc = main([])

    assert rc == 1


def test_cli_importable_no_side_effects():
    import importlib

    import scripts.runtime_status as mod

    importlib.reload(mod)
    assert callable(mod.main)
    assert callable(mod._build_parser)
