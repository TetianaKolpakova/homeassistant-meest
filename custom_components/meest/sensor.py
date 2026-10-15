"""Exactly two aggregate sensors per account."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCOUNT_ID, DOMAIN, NAME

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities(
        [
            MeestSensor(entry.runtime_data, entry, "ready_for_pickup"),
            MeestSensor(entry.runtime_data, entry, "in_transit"),
        ]
    )


class MeestSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = "Data provided by Meest"
    _unrecorded_attributes = frozenset({"parcels", "locations", "unclassified"})

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.data[CONF_ACCOUNT_ID]}_{key}"
        self._attr_icon = (
            "mdi:package-variant-closed-check"
            if key == "ready_for_pickup"
            else "mdi:truck-delivery"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_ACCOUNT_ID])},
            name=entry.title or NAME,
            manufacturer="Meest",
            model="Parcel account",
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data[self.key])

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        attrs = {
            "parcels": data[self.key],
            "unclassified_count": len(data["unclassified"]),
            "unclassified": data["unclassified"],
        }
        if self.key == "ready_for_pickup":
            attrs["locations"] = data["locations"]
        return attrs
