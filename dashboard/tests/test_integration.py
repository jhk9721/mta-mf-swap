"""
Integration tests — analytics + app bootstrap.

Run with: pytest dashboard/tests/test_integration.py -v -m integration
"""

import pytest
from unittest.mock import patch


class TestAnalyticsIntegration:
    """Test analytics integration with the main app."""

    @pytest.mark.integration
    @patch("streamlit.session_state", {})
    @patch("streamlit.secrets", {"analytics": {}})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_analytics_doesnt_break_on_init(self, mock_print, mock_markdown):
        """init_analytics() must never raise, regardless of config."""
        from analytics import init_analytics

        try:
            init_analytics()
            success = True
        except Exception as exc:
            success = False
            print(f"init_analytics() raised: {exc}")

        assert success

    @pytest.mark.integration
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_analytics_works_without_any_secrets(self, mock_print, mock_markdown):
        """App degrades gracefully when secrets.toml is missing entirely."""
        with patch("streamlit.secrets", {}):
            with patch("streamlit.session_state", {}):
                from analytics import init_analytics

                try:
                    init_analytics()
                    success = True
                except Exception:
                    success = False

        assert success

    @pytest.mark.integration
    @patch("streamlit.session_state", {"analytics_session_id": "int-test"})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_track_scroll_depth_injects_script(self, mock_print, mock_markdown):
        """track_scroll_depth() injects a valid <script> block."""
        from analytics import track_scroll_depth
        track_scroll_depth()

        assert mock_markdown.called
        script = str(mock_markdown.call_args[0][0])
        assert "<script>" in script
        assert "scroll" in script.lower()
        assert "milestones" in script
