"""Entity utilities for Watchman."""
from homeassistant.helpers import entity_registry as er
from .logger import _LOGGER

async def update_or_cleanup_entity(
    ent_reg: er.EntityRegistry, platform: str, domain: str, old_uid: str, new_uid: str
) -> None:
    """Migrate entity unique ID or remove duplicates."""
    if old_entity_id := ent_reg.async_get_entity_id(platform, domain, old_uid):
        # we found entities with old-style uid in registry, apply migration logic
        if ent_reg.async_get_entity_id(platform, domain, new_uid):
            ent_reg.async_remove(old_entity_id)
            _LOGGER.debug(
                "async_setup_entry: 2 entities found in registry. "
                "Will remove %s in favor of %s.",
                old_uid,
                new_uid,
            )
        else:
            _LOGGER.debug(
                "async_setup_entry: Entity with old uid %s was migrated to %s.",
                old_uid,
                new_uid,
            )
            ent_reg.async_update_entity(old_entity_id, new_unique_id=new_uid)
