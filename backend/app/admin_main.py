"""Independent Admin API entry point. Run from backend as app.admin_main:app."""
from .application_factory import create_application

app = create_application("admin")
