"""Independent User API entry point. Run from backend as app.user_main:app."""
from .application_factory import create_application

app = create_application("user")
