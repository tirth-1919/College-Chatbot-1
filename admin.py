"""admin.py - Unified launcher for AI FAQ College Chat Bot.

Usage:
  python admin.py              # Starts frontend, backend and other all (Admin + User services)
  python admin.py all          # Starts all services (Admin + User Frontends & Backends)
  python admin.py admin        # Starts only Admin Side services (Backend :8001, Frontend :3001)
  python admin.py user         # Starts only User Side services (Backend :8000, Frontend :3000)
  python admin.py stop         # Stops all running services cleanly
  python admin.py status       # Shows status of all services
"""

import sys
from server_manager import ServiceManager, UnifiedManager


def main() -> int:
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    # Handle stopping
    if action in ("stop", "down"):
        target = sys.argv[2].lower() if len(sys.argv) > 2 else "all"
        if target == "admin":
            ServiceManager("admin").stop()
            print("Admin Side services stopped cleanly.")
        elif target == "user":
            ServiceManager("user").stop()
            print("User Side services stopped cleanly.")
        else:
            UnifiedManager().stop()
            print("All services (Admin & User) stopped cleanly.")
        return 0

    # Handle status
    elif action == "status":
        target = sys.argv[2].lower() if len(sys.argv) > 2 else "all"
        if target == "admin":
            ServiceManager("admin").print_status()
        elif target == "user":
            ServiceManager("user").print_status()
        else:
            UnifiedManager().print_status()
        return 0

    # Handle admin-only mode
    elif action in ("admin", "--admin-only", "-admin"):
        manager = ServiceManager("admin")
        return manager.run()

    # Handle user-only mode
    elif action in ("user", "--user-only", "-user"):
        manager = ServiceManager("user")
        return manager.run()

    # Default / all mode: starts frontend, backend and other all (Admin & User)
    elif action in ("all", "up", "start"):
        manager = UnifiedManager()
        return manager.run()

    elif action in ("--help", "-h", "help"):
        print(__doc__)
        return 0

    else:
        print(f"Unknown action: {action}.")
        print("Usage: python admin.py [all|admin|user|stop|status]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
