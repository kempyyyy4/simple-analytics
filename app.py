"""Rupert Analytics: a native Windows window showing the channel's YouTube analytics.

Run with Rupert Analytics.bat (no console window). Errors are written to app.log in the data folder.
"""
import traceback
from pathlib import Path

import webview

import analytics
import metrics
import store
from ytmcp import core

UI = Path(__file__).resolve().parent / "ui" / "index.html"


def _friendly(error):
    text = str(error)
    if "Not signed in" in text:
        return "Not signed in to YouTube yet. Double-click 'Sign in to YouTube.bat' and try Refresh again."
    return text


class Api:
    """Methods the page calls through window.pywebview.api."""

    def dashboard(self):
        return self._view(store.load_snapshot(), None)

    def refresh(self):
        try:
            raw = analytics.pull()
        except Exception as e:  # any failure: keep showing the last good pull
            core.log.warning("refresh failed: %s", e)
            message = f"Refresh failed: {_friendly(e)} Showing the last pull."
            return self._view(store.load_snapshot(), message)
        store.save_snapshot(raw)
        return self._view(raw, None)

    def save_targets(self, targets):
        store.save_targets(targets)
        return self.dashboard()

    def _view(self, raw, error):
        targets, targets_warning = store.load_config("targets.json")
        texts, texts_warning = store.load_config("diagnosis.json")
        warnings = [w for w in (targets_warning, texts_warning) if w]
        if raw is None:
            return {"empty": True, "error": error or "No data yet. Press Refresh to pull from YouTube.",
                    "warnings": warnings}
        view = metrics.build_view(raw, targets, texts)
        view.update(empty=False, error=error, warnings=warnings)
        return view


def main():
    webview.create_window("Rupert Analytics", str(UI), js_api=Api(),
                          width=1280, height=880, min_size=(960, 640))
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log = store.DATA_DIR / "app.log"
        store.DATA_DIR.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        raise
