
#!/usr/bin/env python3
"""Custom launcher replacing osken-manager.
Usage: python controller/run_controller.py controller/simple_switch.py
"""

# Monkey-patching must happen before other os_ken imports
from os_ken.lib import hub
hub.patch(thread=False)

import sys
import logging

from os_ken import cfg
from os_ken import flags  # noqa: F401
from os_ken.base.app_manager import AppManager
from os_ken.controller import controller  # noqa: F401


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python controller/run_controller.py <app.py>")
        sys.exit(1)

    app_path = sys.argv[1]

    app_mgr = AppManager.get_instance()

    # Load applications before parsing configuration
    app_mgr.load_apps([
        app_path,
        "os_ken.controller.ofp_handler",
        "os_ken.topology.switches"
    ])

    CONF = cfg.CONF
    CONF.set_default("observe_links", True)
    CONF(args=[], project="os_ken", default_config_files=[])

    contexts = app_mgr.create_contexts()
    services = app_mgr.instantiate_apps(**contexts)

    print("Custom OS-Ken controller running (OpenFlow on port 6653). Ctrl+C to stop.")

    try:
        hub.joinall(services)
    except KeyboardInterrupt:
        print("\nStopping controller...")
    finally:
        app_mgr.close()


if __name__ == "__main__":
    main()
