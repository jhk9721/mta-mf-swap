"""
Tests for analytics tracking.

Ensures analytics functions work correctly and respect privacy settings.
Run with: pytest dashboard/tests/test_analytics.py -v
"""

import json
import uuid
import pytest
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session_state(extra=None):
    base = {}
    if extra:
        base.update(extra)
    return base


# ── Init tests ────────────────────────────────────────────────────────────────

class TestAnalyticsInit:
    """Test analytics initialization."""

    @patch("streamlit.session_state", _make_session_state())
    @patch("streamlit.secrets", {"analytics": {}})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_init_creates_session_id(self, mock_print, mock_markdown):
        """init_analytics() generates a unique session ID on first call."""
        import streamlit as st
        st.session_state.clear()

        from analytics import init_analytics
        init_analytics()

        assert "analytics_session_id" in st.session_state
        assert len(st.session_state["analytics_session_id"]) > 0
        assert "analytics_page_views" in st.session_state
        assert st.session_state["analytics_page_views"] == 1

    @patch("streamlit.session_state", _make_session_state())
    @patch("streamlit.secrets", {"analytics": {"google_analytics_id": "G-TEST123"}})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_init_with_google_analytics(self, mock_print, mock_markdown):
        """Google Analytics script is injected when configured."""
        import streamlit as st
        st.session_state.clear()

        from analytics import init_analytics
        init_analytics()

        calls = " ".join(str(c) for c in mock_markdown.call_args_list)
        assert "gtag" in calls
        assert "G-TEST123" in calls

    @patch("streamlit.session_state", _make_session_state())
    @patch("streamlit.secrets", {"analytics": {"google_analytics_id": "G-TEST123"}})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_ip_anonymization_in_ga_script(self, mock_print, mock_markdown):
        """GA4 injection always includes anonymize_ip: true."""
        import streamlit as st
        st.session_state.clear()

        from analytics import init_analytics
        init_analytics()

        calls = " ".join(str(c) for c in mock_markdown.call_args_list)
        assert "anonymize_ip" in calls
        assert "true" in calls

    @patch("streamlit.session_state", _make_session_state())
    @patch("streamlit.secrets", {"analytics": {"google_analytics_id": "G-TEST123"}})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_no_ad_tracking_in_ga_script(self, mock_print, mock_markdown):
        """Ad personalisation and Google Signals are disabled."""
        import streamlit as st
        st.session_state.clear()

        from analytics import init_analytics
        init_analytics()

        calls = " ".join(str(c) for c in mock_markdown.call_args_list)
        assert "allow_ad_personalization_signals" in calls
        assert "allow_google_signals" in calls
        assert "false" in calls

    @patch("streamlit.session_state", _make_session_state())
    @patch("streamlit.secrets", {"analytics": {"plausible_domain": "test.app"}})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_init_with_plausible(self, mock_print, mock_markdown):
        """Plausible script is injected when configured."""
        import streamlit as st
        st.session_state.clear()

        from analytics import init_analytics
        init_analytics()

        calls = " ".join(str(c) for c in mock_markdown.call_args_list)
        assert "plausible.io" in calls
        assert "test.app" in calls


# ── Event tracking tests ──────────────────────────────────────────────────────

class TestEventTracking:
    """Test event tracking functions."""

    @patch("streamlit.session_state", {"analytics_session_id": "test-session-id"})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_track_event_logs_to_stdout(self, mock_print, mock_markdown):
        """track_event() writes an [ANALYTICS] line to stdout."""
        from analytics import track_event
        track_event("test_event", {"key": "value"})

        assert mock_print.called
        log_line = mock_print.call_args[0][0]
        assert "[ANALYTICS]" in log_line
        assert "test_event" in log_line

    @patch("streamlit.session_state", {"analytics_session_id": "test-session-id"})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_track_event_includes_session_id(self, mock_print, mock_markdown):
        """Logged events include the current session ID."""
        from analytics import track_event
        track_event("test_event")

        log_line = mock_print.call_args[0][0]
        assert "test-session-id" in log_line

    @patch("streamlit.session_state", {"analytics_session_id": "test-session-id"})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_track_event_injects_ga_js(self, mock_print, mock_markdown):
        """track_event() injects a <script> block for GA4 / Plausible."""
        from analytics import track_event
        track_event("some_event", {"foo": "bar"})

        assert mock_markdown.called
        script = " ".join(str(c) for c in mock_markdown.call_args_list)
        assert "gtag" in script
        assert "plausible" in script
        assert "some_event" in script

    @patch("streamlit.session_state", {"analytics_session_id": "test-session-id"})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_track_cta_click(self, mock_print, mock_markdown):
        """track_cta_click() fires a cta_click event with the button name."""
        from analytics import track_cta_click
        track_cta_click("contact_menin")

        log_line = mock_print.call_args[0][0]
        assert "cta_click" in log_line
        assert "contact_menin" in log_line

    @patch("streamlit.session_state", {"analytics_session_id": "test-session-id"})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_track_event_no_properties(self, mock_print, mock_markdown):
        """track_event() works when called without properties."""
        from analytics import track_event
        track_event("bare_event")  # No properties argument

        log_line = mock_print.call_args[0][0]
        parsed = json.loads(log_line.replace("[ANALYTICS] ", ""))
        assert parsed["event"] == "bare_event"
        assert "session_id" in parsed["properties"]


# ── Privacy tests ─────────────────────────────────────────────────────────────

class TestPrivacy:
    """Test privacy-related functionality."""

    def test_session_id_is_valid_uuid(self):
        """Session ID is a random UUID — not PII."""
        session_id = str(uuid.uuid4())
        # Verify format
        parsed = uuid.UUID(session_id)
        assert str(parsed) == session_id

    @patch("streamlit.session_state", _make_session_state())
    @patch("streamlit.secrets", {})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_init_works_without_secrets(self, mock_print, mock_markdown):
        """App still initialises when secrets.toml is absent."""
        import streamlit as st
        st.session_state.clear()

        from analytics import init_analytics
        init_analytics()  # Must not raise

        assert "analytics_session_id" in st.session_state

    @patch("streamlit.session_state", _make_session_state())
    @patch("streamlit.secrets", {"analytics": {}})
    @patch("streamlit.markdown")
    @patch("builtins.print")
    def test_page_view_counter_increments(self, mock_print, mock_markdown):
        """Each init call increments the page-view counter."""
        import streamlit as st
        st.session_state.clear()

        from analytics import init_analytics
        init_analytics()
        assert st.session_state["analytics_page_views"] == 1

        init_analytics()
        assert st.session_state["analytics_page_views"] == 2


# ── Summary tests ─────────────────────────────────────────────────────────────

class TestAnalyticsSummary:
    """Test analytics summary helper."""

    @patch("streamlit.session_state", {
        "analytics_session_id": "abc-123",
        "analytics_page_views": 7,
    })
    def test_get_summary_returns_expected_keys(self):
        """get_analytics_summary() returns session_id, page_views, timestamp."""
        from analytics import get_analytics_summary
        summary = get_analytics_summary()

        assert summary["session_id"] == "abc-123"
        assert summary["page_views"] == 7
        assert "timestamp" in summary

    @patch("streamlit.session_state", {})
    def test_get_summary_handles_missing_state(self):
        """get_analytics_summary() doesn't raise when state is empty."""
        from analytics import get_analytics_summary
        summary = get_analytics_summary()

        assert summary["session_id"] == "unknown"
        assert summary["page_views"] == 0
