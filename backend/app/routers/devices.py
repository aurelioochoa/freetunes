from fastapi import APIRouter

from ..models import Device
from ..services.devices import get_service

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[Device])
def list_devices() -> list[Device]:
    """Real usbmuxd enumeration; empty when mock mode or no device."""
    return get_service().list_devices()


@router.get("/{udid}/info", response_model=Device)
def device_info(udid: str) -> Device:
    for d in get_service().list_devices():
        if d.udid == udid:
            return d
    return Device(udid=udid, name="iPhone", ios_version="unknown", trusted=False)


@router.post("/{udid}/pair")
def pair_device(udid: str) -> dict:
    """Ask the iPhone to show 'Trust This Computer?' (via idevicepair pair)."""
    return get_service().pair(udid)
