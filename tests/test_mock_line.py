"""Tests for the local mock LINE CLI."""

from scripts.mock_line import mock_line_payload


def test_mock_line_pdf_task():
    assert mock_line_payload("處理電費單") == "小雷收到：我判斷這是 PDF 任務"


def test_mock_line_folder_task():
    assert mock_line_payload("整理 Downloads") == "小雷收到：我判斷這是資料夾整理任務"


def test_mock_line_code_task():
    assert mock_line_payload("幫我寫 API") == "小雷收到：我判斷這是程式開發任務"


def test_mock_line_requirements_task():
    assert mock_line_payload("幫我整理需求") == "小雷收到：我判斷這是需求分析任務"


def test_mock_line_default_task():
    assert mock_line_payload("你好") == "小雷收到：我還不確定你的需求，可以再說清楚一點嗎？"
