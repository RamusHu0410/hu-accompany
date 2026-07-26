"""Advertises this Django server on the LAN via mDNS/Bonjour.

The Flutter app has no fixed IP to call — dev machines hop between
networks/DHCP leases — so instead of hardcoding an address, the app
discovers this service by name (see frontend/lib/ServerDiscovery.dart).
"""

import atexit
import socket

from zeroconf import ServiceInfo, Zeroconf

SERVICE_TYPE = "_huaccompany._tcp.local."
SERVICE_NAME = f"hu-accompany-backend.{SERVICE_TYPE}"

_zeroconf: Zeroconf | None = None


def _local_ip() -> str:
    # Doesn't actually send anything (UDP), just asks the OS which local
    # interface it would use to reach an external address, which is a
    # reliable way to find the LAN-facing IP even with no default route.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start(port: int = 8000) -> None:
    global _zeroconf
    if _zeroconf is not None:
        return

    ip = _local_ip()
    info = ServiceInfo(
        SERVICE_TYPE,
        SERVICE_NAME,
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={},
        server=f"{socket.gethostname()}.local.",
    )

    # Scoped to just the LAN-facing interface: binding "all interfaces"
    # (zeroconf's default) also binds loopback, which on this dev machine
    # collides with other local mDNS responders (e.g. Lima, Chrome) that
    # already hold port 5353 there.
    _zeroconf = Zeroconf(interfaces=[ip])
    _zeroconf.register_service(info)
    atexit.register(stop)


def stop() -> None:
    global _zeroconf
    if _zeroconf is not None:
        _zeroconf.close()
        _zeroconf = None
