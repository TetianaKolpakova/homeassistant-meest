"""Aggregate parcels without creating per-parcel entities."""

from __future__ import annotations

from typing import Any

TRANSIT_CODES = {"1", "3", "7"}  # SENT, COURIER, CUSTOMS; live validation still needed.
TERMINAL_CODES = {"4", "5", "6"}
PICKUP_SERVICES = {"Branch", "PostStation"}


def text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def aggregate(items: list[dict]) -> dict[str, Any]:
    ready, transit, unclassified = [], [], []
    groups: dict[tuple[str, str], dict] = {}
    for item in items:
        if type(item.get("direction")) is not int:
            raise ValueError("Missing or invalid parcel direction")
        if item.get("direction") != 1 or item.get("archive") is True:
            continue
        delivery = item.get("DeliveryInfo")
        if not isinstance(delivery, dict):
            raise ValueError("Missing DeliveryInfo in incoming parcel")
        receiver = delivery.get("receiver")
        receiver = receiver if isinstance(receiver, dict) else {}
        code = str(delivery.get("statusCode", ""))
        service = text(receiver.get("service"))
        parcel = {
            "number": text(item.get("parcelNumber")),
            "name": text(item.get("notation"))
            or text(item.get("contentName"))
            or text(item.get("parcelNumber")),
            "status_code": code,
            "status": text(delivery.get("statusName")) or text(delivery.get("status")),
            "service": service,
            "branch_number": text(receiver.get("branchNumber")),
            "address": text(receiver.get("address")),
            "estimated_delivery": text(delivery.get("estimatedDeliveryDate")),
        }
        if code == "2" and service in PICKUP_SERVICES:
            ready.append(parcel)
            location_id = (
                text(receiver.get("branchID"))
                or parcel["branch_number"]
                or parcel["address"]
                or text(item.get("parcelID"))
                or parcel["number"]
            )
            group = groups.setdefault(
                (service, location_id),
                {
                    "type": "post_station" if service == "PostStation" else "branch",
                    "branch_number": parcel["branch_number"],
                    "address": parcel["address"],
                    "parcels": [],
                },
            )
            group["parcels"].append(parcel)
        elif code in TRANSIT_CODES:
            transit.append(parcel)
        elif code not in TERMINAL_CODES and code != "0":
            # Do not silently map unknown statuses/delivered-to-door to pickup.
            unclassified.append(
                {"number": parcel["number"], "status_code": code, "service": service}
            )
    ready.sort(key=lambda parcel: parcel["number"])
    transit.sort(key=lambda parcel: parcel["number"])
    group_list = sorted(
        groups.values(), key=lambda group: (group["type"], group["branch_number"], group["address"])
    )
    for group in group_list:
        group["parcels"].sort(key=lambda parcel: parcel["number"])
    unclassified.sort(key=lambda parcel: parcel["number"])
    return {
        "ready_for_pickup": ready,
        "in_transit": transit,
        "locations": group_list,
        "unclassified": unclassified,
    }
