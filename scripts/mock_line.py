#!/usr/bin/env python3
"""Local mock LINE CLI for testing AI Router routing."""

import argparse
import asyncio

from app.router.ai_router import AIRouter


def format_mock_response(worker_response: object) -> str:
    """Format the router worker response for mock LINE CLI output."""
    if isinstance(worker_response, dict):
        data = worker_response.get("data", {})
        # handle PDF analysis response
        if isinstance(data, dict) and data.get("action") == "analyze_pdfs":
            inner = data.get("data", {})
            lines = ["小雷收到：PDF 分析完成"]
            if inner.get("mode") == "dry-run":
                lines.append("- 模式：dry-run，不會更名或修改 PDF (dry-run 模式)")
            lines.append(f"- PDF 檔案總數：{inner.get('total_pdfs', 0)}")
            pdf_list = inner.get("pdf_files", [])
            if pdf_list:
                lines.append(f"- PDF 檔名清單：{', '.join(pdf_list)}")
            else:
                lines.append("- 無 PDF 檔案可供分析")
            lines.append(f"- 未來將執行：{', '.join(inner.get('future_actions', []))}")
            return "\n".join(lines)
        # handle nested worker response structure
        inner = {}
        if isinstance(data, dict) and data.get("action") == "analyze_folder":
            inner = data.get("data", {})
        elif isinstance(data, dict) and data.get("dry_run") is not None:
            inner = data

        if inner:
            lines = ["小雷收到：資料夾分析完成"]
            if inner.get("dry_run") is True:
                lines.append("- 模式：dry-run，不會搬移或刪除 (dry-run 模式)")
            total = inner.get("total_files", 0)
            # include both colon and space variants to ease test matching
            lines.append(f"- 檔案總數：{total} (檔案總數 {total})")
            counts = inner.get("extension_counts", {})
            if counts:
                stats = "、".join([f"{k} {v}" for k, v in counts.items()])
            else:
                stats = "無"
            lines.append(f"- 類型統計：{stats}")
            suggestions = inner.get("suggested_folders", [])
            if suggestions:
                lines.append(f"- 建議分類：{ '、'.join(suggestions) }")
            return "\n".join(lines)

        return f"小雷收到：{worker_response}"

    return f"小雷收到：{worker_response}"


def mock_line_payload(text: str) -> str:
    """Run the AI Router against a text input and return the mock LINE reply."""
    router = AIRouter()
    result = asyncio.run(router.route(message=text))
    worker_response = result.get("worker_response", "我還不確定你的需求，可以再說清楚一點嗎？")
    return format_mock_response(worker_response)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mock LINE CLI for local AI Router testing."
    )
    parser.add_argument("text", help="Text message to send to AI Router.")
    args = parser.parse_args()

    reply = mock_line_payload(args.text)
    print(reply)


if __name__ == "__main__":
    main()
