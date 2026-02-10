"""Text entity for Watchman ignored labels."""
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir, label_registry as lr
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_IGNORED_LABELS, DOMAIN
from .coordinator import WatchmanCoordinator


class WatchmanIgnoredLabelsText(RestoreEntity, TextEntity):
    """Text entity to manage ignored labels."""

    _attr_has_entity_name = True
    _attr_translation_key = "ignored_labels"
    _attr_icon = "mdi:label-off"

    def __init__(self, hass: HomeAssistant, coordinator: WatchmanCoordinator) -> None:
        """Initialize the entity."""
        self.hass = hass
        self.coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_ignored_labels"
        self.entity_id = f"text.{DOMAIN}_ignored_labels"
        self._attr_native_value = ""
        # Orphan entity: No device_info, so it won't appear on the device page

    @property
    def native_value(self) -> str:
        """Return the value of the text entity."""
        labels = self.coordinator.config_entry.data.get(CONF_IGNORED_LABELS, [])
        return ", ".join(labels)

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Migration: Restore state to config entry if key is missing
        if CONF_IGNORED_LABELS not in self.coordinator.config_entry.data:
            if (state := await self.async_get_last_state()) is not None:
                restored_labels = self._parse_labels(state.state)
                if restored_labels:
                    self.hass.config_entries.async_update_entry(
                        self.coordinator.config_entry,
                        data={**self.coordinator.config_entry.data, CONF_IGNORED_LABELS: restored_labels}
                    )
            else:
                # If no restored state, initialize key to empty list to mark migration done
                self.hass.config_entries.async_update_entry(
                    self.coordinator.config_entry,
                    data={**self.coordinator.config_entry.data, CONF_IGNORED_LABELS: []}
                )

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        # Create deprecation issue
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            "deprecated_ignored_labels_entity",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_text_entity",
            translation_placeholders={
                "entity_id": self.entity_id,
            },
        )

        valid_labels, invalid_labels = self._validate_labels(value)

        if invalid_labels:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Watchman: Invalid Labels",
                    "message": f"The following labels were not found and ignored: {', '.join(invalid_labels)}",
                    "notification_id": "watchman_invalid_labels",
                },
            )

        # Save to config entry (triggers reload)
        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data={**self.coordinator.config_entry.data, CONF_IGNORED_LABELS: valid_labels}
        )

    def _parse_labels(self, value: str) -> list[str]:
        """Parse comma-separated string to list."""
        if not value:
            return []
        return [x.strip() for x in value.split(",") if x.strip()]

    def _validate_labels(self, value: str) -> tuple[list[str], list[str]]:
        """Validate labels against registry."""
        registry = lr.async_get(self.hass)
        existing_labels = {l.label_id for l in registry.async_list_labels()}

        input_labels = self._parse_labels(value)
        valid = []
        invalid = []

        for label in input_labels:
            if label in existing_labels:
                valid.append(label)
            else:
                invalid.append(label)

        return valid, invalid

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the text platform."""
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities([WatchmanIgnoredLabelsText(hass, coordinator)])
