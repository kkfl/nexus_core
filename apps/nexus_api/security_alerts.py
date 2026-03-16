"""
Security Alerts — thin re-export from packages.shared.alerts.

Kept for backwards compatibility. New code should import from packages.shared.alerts directly.
"""

from packages.shared.alerts import send_alert, send_security_alert  # noqa: F401
