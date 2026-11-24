"""PyFFI enum fields keep every value a file holds when copied or set, as they do when read.

PyFFI reads any stored value into an enum field, but its EnumBase.set_value refuses one its nif.xml does not list:
it logs `invalid enum value` and keeps the old value. Every copy (deepcopy, setattr) goes through set_value, so it
silently dropped what the file authored.

See: docs/commentary/asset_convert_nif.md#enum-values-kept
"""

from pyffi.object_models.xml.enum import EnumBase


def install() -> None:
    """Make EnumBase.set_value keep an integer outside the enum's list, as read does; idempotent."""
    if getattr(EnumBase, '_tesconv_any_value', False):
        return
    listed = EnumBase.set_value

    def set_value(self, value):
        """Keep int `value` as is when the enum does not list it; else PyFFI's own set_value."""
        if isinstance(value, int) and not isinstance(value, bool) and value not in self._enumvalues:
            self._value = value
            return
        listed(self, value)

    EnumBase.set_value = set_value
    EnumBase._tesconv_any_value = True
