# Copyright (c) 2026 meteozond.
# This tool is released under the terms of the AGPLv3 or higher.

from typing import Optional
from UM.Scene.SceneNodeDecorator import SceneNodeDecorator


class PinHoleLinkDecorator(SceneNodeDecorator):
    """A decorator that stores a link to the matching pin hole in the other half."""

    def __init__(self, node_id: Optional[int]) -> None:
        super().__init__()
        self._linked_node_id = node_id

    def pinHoleLinkedNodeId(self) -> Optional[int]:
        return self._linked_node_id

    # Skip copying the node id as a way of breaking the link, so a copied hole does not move the original's pair
    def __deepcopy__(self, memo) -> "PinHoleLinkDecorator":
        copied_decorator = PinHoleLinkDecorator(None)
        return copied_decorator
