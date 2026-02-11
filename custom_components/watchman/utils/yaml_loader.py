"""YAML Loader for Watchman."""
from typing import Any, Self

import yaml

# Custom YAML Loader with Line Numbers

class StringWithLine(str):
    """String subclass that holds the line number, tag info, and scalar style."""

    def __new__(
        cls, value: str, line: int, *, is_tag: bool = False, style: str | None = None
    ) -> Self:
        obj = str.__new__(cls, value)
        obj.line = line
        obj.is_tag = is_tag
        obj.style = style  # Store the style (e.g., '"', "'", '>', '|')
        return obj

class LineLoader(yaml.SafeLoader):
    """Custom YAML loader that attaches line numbers to scalars."""

    def construct_scalar(self, node: yaml.ScalarNode) -> Any:
        value = super().construct_scalar(node)
        if isinstance(value, str):
            # Pass node.style to the string object
            return StringWithLine(value, node.start_mark.line + 1, style=node.style)
        return value

    def flatten_mapping(self, node: yaml.MappingNode) -> None:
        """Override flatten_mapping to handle merge keys ('<<') safely."""
        merge = []
        index = 0
        while index < len(node.value):
            key_node, value_node = node.value[index]
            if key_node.tag == 'tag:yaml.org,2002:merge':
                del node.value[index]
                if isinstance(value_node, yaml.MappingNode):
                    self.flatten_mapping(value_node)
                    merge.extend(value_node.value)
                elif isinstance(value_node, yaml.SequenceNode):
                    submerge = []
                    for subnode in value_node.value:
                        if isinstance(subnode, yaml.MappingNode):
                            self.flatten_mapping(subnode)
                            submerge.append(subnode)
                        elif isinstance(subnode, yaml.ScalarNode):
                            continue
                    for subnode in reversed(submerge):
                        merge.extend(subnode.value)
                elif isinstance(value_node, yaml.ScalarNode):
                    continue
            elif key_node.tag == 'tag:yaml.org,2002:value':
                key_node.tag = 'tag:yaml.org,2002:str'
                index += 1
            else:
                index += 1
        if merge:
            node.value = merge + node.value

LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, LineLoader.construct_scalar)

# Handle custom HA tags by ignoring them or treating as string
def default_ctor(loader: yaml.Loader, tag_suffix: str, node: yaml.ScalarNode) -> Any:
    value = loader.construct_scalar(node)
    if isinstance(value, str):
        # Pass node.style here as well
        return StringWithLine(value, node.start_mark.line + 1, is_tag=True, style=node.style)
    return value

yaml.add_multi_constructor('!', default_ctor, Loader=LineLoader)
