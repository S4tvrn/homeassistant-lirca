"""Sensori per l'integrazione LIRCA."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LircaDataUpdateCoordinator
from .api import LircaReading
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Crea un sensore per ogni contatore trovato dal coordinator."""
    coordinator: LircaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        LircaMeterSensor(coordinator, entry, reading.matricola)
        for reading in coordinator.data
    ]
    async_add_entities(entities)


class LircaMeterSensor(CoordinatorEntity[LircaDataUpdateCoordinator], SensorEntity):
    """Rappresenta un singolo contatore LIRCA (calore o acqua)."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: LircaDataUpdateCoordinator, entry: ConfigEntry, matricola: str
    ) -> None:
        super().__init__(coordinator)
        self._matricola = matricola
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{matricola}"

    @property
    def _reading(self) -> LircaReading | None:
        for reading in self.coordinator.data:
            if reading.matricola == self._matricola:
                return reading
        return None

    @property
    def name(self) -> str | None:
        reading = self._reading
        if reading is None:
            return self._matricola
        return f"{reading.tipo} {reading.ubicazione}"

    @property
    def native_value(self) -> float | str | None:
        reading = self._reading
        if reading is None:
            return None
        try:
            return float(reading.ultima_lettura.replace(".", "").replace(",", "."))
        except ValueError:
            return reading.ultima_lettura

    @property
    def extra_state_attributes(self) -> dict[str, str | list[dict[str, str]]] | None:
        reading = self._reading
        if reading is None:
            return None
        attributes: dict[str, str | list[dict[str, str]]] = {
            "matricola": reading.matricola,
            "data_lettura": reading.data_lettura,
            "tipo": reading.tipo,
            "ubicazione": reading.ubicazione,
        }
        if reading.storico is not None:
            attributes["storico_letture"] = [
                {
                    "tipo_consumo": entry.tipo_consumo,
                    "data_doc": entry.data_doc,
                    "data_lettura_precedente": entry.data_lettura_precedente,
                    "data_lettura_attuale": entry.data_lettura_attuale,
                    "lettura_precedente": entry.lettura_precedente,
                    "lettura_attuale": entry.lettura_attuale,
                    "consumo": entry.consumo,
                }
                for entry in reading.storico
            ]
        return attributes

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="LIRCA",
            entry_type="service",
        )

    @property
    def available(self) -> bool:
        return super().available and self._reading is not None
