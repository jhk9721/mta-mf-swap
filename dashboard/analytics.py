"""
Analytics tracking for Roosevelt Island Dashboard

Privacy-first implementation with three tiers:
1. Simple logging (default, most private) — stdout → Streamlit Cloud Logs
2. Plausible (privacy-focused, paid)
3. Google Analytics (full-featured, free)

All implementations include IP anonymization and minimal data collection.
"""

import streamlit as st
from datetime import datetime
import json
import uuid
from typing import Optional, Dict, Any


def init_analytics():
    """
    Initialize analytics tracking based on secrets configuration.
    Call this once at the top of app.py.
    """
    # Generate session ID for this visit
    if "analytics_session_id" not in st.session_state:
        st.session_state["analytics_session_id"] = str(uuid.uuid4())

    # Initialize page view counter
    if "analytics_page_views" not in st.session_state:
        st.session_state["analytics_page_views"] = 0

    # Check which analytics provider is configured
    analytics_config = st.secrets.get("analytics", {})

    if analytics_config.get("google_analytics_id"):
        _inject_google_analytics(analytics_config["google_analytics_id"])

    if analytics_config.get("plausible_domain"):
        _inject_plausible(analytics_config["plausible_domain"])

    # Always log a page view as fallback (appears in Streamlit Cloud Logs)
    _log_page_view()


def _inject_google_analytics(ga_id: str):
    """Inject Google Analytics 4 with privacy-friendly settings."""
    ga_script = f"""
    <!-- Google Analytics 4 - Privacy Enhanced -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{ga_id}', {{
        'anonymize_ip': true,
        'allow_google_signals': false,
        'allow_ad_personalization_signals': false,
        'cookie_flags': 'SameSite=None;Secure',
      }});
    </script>
    """
    st.markdown(ga_script, unsafe_allow_html=True)


def _inject_plausible(domain: str):
    """Inject Plausible analytics (privacy-friendly alternative)."""
    plausible_script = f"""
    <!-- Plausible Analytics - Privacy First -->
    <script defer data-domain="{domain}" src="https://plausible.io/js/script.js"></script>
    """
    st.markdown(plausible_script, unsafe_allow_html=True)


def _log_page_view():
    """Simple logging fallback — prints to stdout, visible in Streamlit Cloud Logs."""
    st.session_state["analytics_page_views"] += 1

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "page_view",
        "session_id": st.session_state["analytics_session_id"],
        "view_count": st.session_state["analytics_page_views"],
    }
    # print() goes to stdout → Streamlit Cloud > Manage app > Logs
    print(f"[ANALYTICS] {json.dumps(log_entry)}")


def track_event(event_name: str, properties: Optional[Dict[str, Any]] = None):
    """
    Track custom events across all configured analytics providers.

    Usage:
        track_event('section_view', {'section': 'mta_promise'})
        track_event('cta_click', {'button': 'contact_menin'})

    Args:
        event_name: Name of the event (use snake_case)
        properties: Optional dict of event properties
    """
    if properties is None:
        properties = {}

    # Add session context
    properties["session_id"] = st.session_state.get("analytics_session_id", "unknown")

    props_json = json.dumps(properties)

    # Inject client-side tracking for GA4 + Plausible (if configured)
    event_script = f"""
    <script>
      if (typeof gtag !== 'undefined') {{
        gtag('event', '{event_name}', {props_json});
      }}
      if (typeof plausible !== 'undefined') {{
        plausible('{event_name}', {{props: {props_json}}});
      }}
    </script>
    """
    st.markdown(event_script, unsafe_allow_html=True)

    # Simple logging fallback
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_name,
        "properties": properties,
    }
    print(f"[ANALYTICS] {json.dumps(log_entry)}")


def track_scroll_depth():
    """
    Track how far users scroll down the page.
    Fires events at 25%, 50%, 75%, 100% scroll depth.
    """
    scroll_script = """
    <script>
    (function() {
        let maxScroll = 0;
        const milestones = [25, 50, 75, 100];

        window.addEventListener('scroll', function() {
            const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
            if (scrollHeight <= 0) return;
            const scrollPct = Math.round((window.scrollY / scrollHeight) * 100);

            milestones.forEach(function(milestone) {
                if (scrollPct >= milestone && maxScroll < milestone) {
                    maxScroll = milestone;

                    if (typeof gtag !== 'undefined') {
                        gtag('event', 'scroll_depth', {
                            'depth': milestone,
                            'event_category': 'engagement'
                        });
                    }
                    if (typeof plausible !== 'undefined') {
                        plausible('Scroll', {props: {depth: milestone}});
                    }
                }
            });
        });
    })();
    </script>
    """
    st.markdown(scroll_script, unsafe_allow_html=True)


def track_cta_click(button_name: str):
    """
    Track CTA button clicks.

    Usage:
        track_cta_click('contact_menin')
        track_cta_click('github_download')
        track_cta_click('share_link')
    """
    track_event("cta_click", {"button": button_name})


def get_analytics_summary() -> Dict[str, Any]:
    """
    Get simple analytics summary from session state.
    Useful for debugging or displaying to admins.
    """
    return {
        "session_id": st.session_state.get("analytics_session_id", "unknown"),
        "page_views": st.session_state.get("analytics_page_views", 0),
        "timestamp": datetime.now().isoformat(),
    }
