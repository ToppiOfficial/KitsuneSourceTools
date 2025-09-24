class KVValue:
    """Base class for KeyValues typed values.

    Subclasses must implement __str__ to produce KV-compliant serialization.
    """
    def __str__(self):
        raise NotImplementedError
    
class KVVector2(KVValue):
    """Represents a 2D vector."""
    def __init__(self, x, y):
        self.x, self.y = x, y

    def __str__(self):
        return f"[ {self.x}, {self.y} ]"

class KVVector3(KVValue):
    """Represents a 3D vector."""
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

    def __str__(self):
        return f"[ {self.x}, {self.y}, {self.z} ]"
    
class KVVector4(KVValue):
    """Represents a 4D vector."""
    def __init__(self, x, y, z, w):
        self.x, self.y, self.z, self.w = x, y, z, w

    def __str__(self):
        return f"[ {self.x}, {self.y}, {self.z}, {self.w} ]"

class KVBool(KVValue):
    """Represents a boolean literal (true/false)."""
    def __init__(self, value: bool):
        self.value = bool(value)

    def __str__(self):
        return "true" if self.value else "false"

class KVArray(KVValue):
    """Represents an array of values (supports KVValue types, numbers, or strings)."""
    def __init__(self, *values):
        self.values = values

    def __str__(self):
        formatted = ", ".join(KVNode._format_value_static(v) for v in self.values)
        return f"[ {formatted} ]"

class KVHeader:
    """Represents the header for KeyValues.

    Attributes:
        encoding: Encoding type (usually 'text')
        encoding_version: GUID for KV encoding version
        format: ModelDoc format version (e.g., 'modeldoc28')
        format_version: GUID for the modeldoc format
    """
    DEFAULT_ENCODING_GUID = "{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d}"
    MODEL_DOC_GUID = "{fb63b6ca-f435-4aa0-a2c7-c66ddc651dca}"  # modeldoc28 GUID

    def __init__(self, encoding="text", encoding_version=None,
                 format="modeldoc28", format_version=None):
        self.version = "kv3"
        self.encoding = encoding
        self.encoding_version = encoding_version or self.DEFAULT_ENCODING_GUID
        self.format = format
        self.format_version = format_version or self.MODEL_DOC_GUID

    def __str__(self):
        return (f"<!-- {self.version} encoding:{self.encoding}"
                f":version{self.encoding_version} "
                f"format:{self.format}"
                f":version{self.format_version} -->")

class KVNode:
    """Represents a single node in a KeyValues tree.

    Attributes:
        _class: Type of the node (e.g., 'RootNode', 'DefineBone')
        name: Optional human-readable name
        children: List of child KVNode objects
        properties: Arbitrary key-value pairs (str, KVValue, int, float, list, etc.)
    """
    def __init__(self, **kwargs):
        self.children = []
        self.properties = kwargs

    def add_child(self, child: "KVNode"):
        """Attach a child KVNode to this node."""
        self.children.append(child)
        
    def remove_child(self, child: "KVNode") -> bool:
        """
        Remove a child node. Returns True if the child was found and removed,
        False otherwise.
        """
        try:
            self.children.remove(child)
            return True
        except ValueError:
            return False

    def _serialize(self, indent=0) -> str:
        """Serialize this node to a KeyValues string.

        Args:
            indent: Number of indentation levels (for pretty printing)

        Returns:
            str: KeyValues-compliant string representation
        """
        tab = "    " * indent
        out = f"{tab}{{\n"
        
        # Properties
        for key, value in self.properties.items():
            out += f"{tab}    {key} = {self._format_value(value)}\n"

        # Children
        if self.children:
            out += f"{tab}    children = [\n"
            for c in self.children:
                out += c._serialize(indent + 2)
                out += ",\n"
            out += f"{tab}    ]\n"

        out += f"{tab}}}"
        return out

    @staticmethod
    def _format_value_static(value):
        """Format a value into a KV-compliant string."""
        if isinstance(value, KVValue):
            return str(value)
        if isinstance(value, KVNode):
            return value._serialize()
        if isinstance(value, str):
            escaped = value.replace("\n", "\\n")
            return f'"{escaped}"'
        if isinstance(value, (list, tuple)):
            return "[ " + ", ".join(KVNode._format_value_static(v) for v in value) + " ]"
        return str(value)

    def _format_value(self, value):
        """Instance wrapper for static format method."""
        return self._format_value_static(value)
    
class KVDocument:
    """Represents a full KV3 document, including header and multiple top-level keys."""
    def __init__(self, format="modeldoc28", format_version=None, encoding="text", encoding_version=None):
        self.header = KVHeader(encoding=encoding, encoding_version=encoding_version,
                               format=format, format_version=format_version)
        self.roots: dict[str, KVNode] = {}

    def add_root(self, key: str, node: KVNode):
        """Add a top-level root node."""
        self.roots[key] = node
        
    def remove_root(self, key: str) -> bool:
        """Remove a root node by key. Returns True if removed, False if not found."""
        return self.roots.pop(key, None) is not None

    def to_text(self) -> str:
        out = str(self.header) + "\n{\n"
        for key, node in self.roots.items():
            out += f"    {key} = {node._serialize(indent=1)}\n"
        out += "}\n"
        return out