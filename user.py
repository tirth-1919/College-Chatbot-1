"""user.py - Unified launcher for AI FAQ College Chat Bot (User Side).

Usage:
  python user.py          # Starts User Backend (8000) and User Frontend (3000)
  python user.py all      # Starts all services (User + Admin)
  python user.py stop     # Stops User Side services (or python user.py stop all)
  python user.py status   # Shows User Side status
"""

import sys
from server_manager import ServiceManager, UnifiedManager


def main() -> int:
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "up"

    if action in ("stop", "down"):
        target = sys.argv[2].lower() if len(sys.argv) > 2 else "user"
        if target == "all":
            UnifiedManager().stop()
            print("All services stopped cleanly.")
        else:
            ServiceManager("user").stop()
            print("User Side services stopped cleanly.")
        return 0
    elif action == "status":
        ServiceManager("user").print_status()
        return 0
    elif action in ("all",):
        return UnifiedManager().run()
    elif action in ("up", "start", "user"):
        return ServiceManager("user").run()
    else:
        print(f"Unknown action: {action}. Use: python user.py [up|all|stop|status]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
