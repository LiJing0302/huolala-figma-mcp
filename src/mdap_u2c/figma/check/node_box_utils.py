from typing import Dict, Any


class NodeBoxUtils:
    @classmethod
    def get_node_width_use_bounding(cls, absolute_bounding_box: Dict[str, Any]) -> int | None:
        if absolute_bounding_box:
            return int(absolute_bounding_box.get("width", 0))

    @classmethod
    def get_node_height_use_bounding(cls, absolute_bounding_box: Dict[str, Any]) -> int | None:
        if absolute_bounding_box:
            return int(absolute_bounding_box.get("height", 0))
