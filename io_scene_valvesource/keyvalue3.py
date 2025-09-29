import re

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
        tab = "    " * indent
        out = f"{tab}{{\n"

        # Properties
        for key, value in self.properties.items():
            if isinstance(value, KVNode):
                out += f"{tab}    {key} = {value._serialize(indent + 1)}\n"
            elif isinstance(value, dict):
                out += f"{tab}    {key} = {{\n"
                for k2, v2 in value.items():
                    out += f"{tab}        {k2} = {self._format_value(v2)}\n"
                out += f"{tab}    }}\n"
            else:
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
    def _format_value_static(value, indent=0):
        if isinstance(value, KVValue):
            return str(value)
        if isinstance(value, KVNode):
            return "\n" + value._serialize(indent=indent + 1)  # relative indent
        if isinstance(value, str):
            # Detect typed literal: type:"value"
            if re.match(r"^\w+:\".*\"$", value):
                return value  # leave as-is
            escaped = value.replace("\n", "\\n")
            return f'"{escaped}"'
        if isinstance(value, (list, tuple)):
            return "[ " + ", ".join(KVNode._format_value_static(v, indent=indent) for v in value) + " ]"
        return str(value)

    def _format_value(self, value):
        """Instance wrapper for static format method."""
        return self._format_value_static(value)
    
    def get(self, **conditions) -> "KVNode | None":
        """
        Find the first direct child node that matches all given property conditions.
        
        Example:
            node.get(name="TestNode")
            node.get(name="TestNode", enabled=True)
        """
        for child in self.children:
            if all(child.properties.get(k) == v for k, v in conditions.items()):
                return child
        return None
    
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

class KVParserError(Exception):
    pass

class KVParser:
    """Parses KV3 text into Python dicts or KVDocument objects."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def parse(self) -> KVDocument:
        header = self._parse_header()
        self._consume_whitespace()
        self._expect("{")
        roots = self._parse_roots()
        self._expect("}")
        doc = KVDocument(format=header.get("format"), encoding=header.get("encoding")) # type: ignore
        doc.roots = roots
        return doc

    def _parse_header(self) -> dict:
        header_match = re.search(
            r"<!--\s*kv3\s+encoding:(\w+):version([^\s]+)\s+format:(\w+):version([^\s]+)\s*-->",
            self.text
        )
        if not header_match:
            return {}
        
        self.pos = header_match.end()

        return {
            "encoding": header_match.group(1),
            "encoding_version": header_match.group(2),
            "format": header_match.group(3),
            "format_version": header_match.group(4)
        }

    def _parse_roots(self) -> dict:
        roots = {}
        while True:
            self._consume_whitespace()
            if self._peek() == "}":
                break
            key = self._parse_identifier()
            self._consume_whitespace()
            self._expect("=")
            self._consume_whitespace()
            node = self._parse_node()
            roots[key] = node
        return roots

    def _parse_node(self) -> KVNode:
        self._expect("{")
        props = {}
        children = []

        while True:
            self._consume_whitespace()
            c = self._peek()

            if c == "}":
                self._advance()
                break

            if c == "{":
                children.append(self._parse_node())
                continue

            key = self._parse_identifier()
            self._consume_whitespace()

            if self._peek() == "=":
                self._advance()
                self._consume_whitespace()
            else:
                pass

            if key == "children":
                children = self._parse_children()
            else:
                props[key] = self._parse_value()

        node = KVNode(**props)
        node.children = children
        return node


    def _parse_children(self) -> list:
        self._expect("[")
        children = []
        while True:
            self._consume_whitespace()
            c = self._peek()
            if c == "]":
                self._advance()
                break

            if c == "{":
                child = self._parse_node()
            else:
                child = self._parse_value()

            children.append(child)

            self._consume_whitespace()
            if self._peek() == ",":
                self._advance()

        return children


    def _parse_value(self):
        c = self._peek()
        if c == "{":
            return self._parse_node()
        if c == "[":
            return self._parse_array()
        if c == '"':
            return self._parse_string()

        # read the next word (could be true, false, number, or typed literal)
        word = self._parse_word()

        if word.endswith(":") and self._peek() == '"':
            literal_type = word[:-1]
            literal_value = self._parse_string()
            return f"{literal_type}:{literal_value}"

        if word == "true":
            return True
        if word == "false":
            return False
        if self._is_number(word):
            return float(word) if "." in word else int(word)
        return word

    def _parse_array(self):
        self._expect("[")
        values = []
        while True:
            self._consume_whitespace()
            if self._peek() == "]":
                self._advance()
                break
            values.append(self._parse_value())
            self._consume_whitespace()
            if self._peek() == ",":
                self._advance()
        return values

    def _parse_identifier(self):
        self._consume_whitespace()
        return self._parse_word()

    def _parse_word(self):
        self._consume_whitespace()
        start = self.pos
        while self.pos < self.length and self.text[self.pos] not in " \t\r\n={}[],":
            self.pos += 1
        return self.text[start:self.pos]

    def _parse_string(self):
        self._expect('"')
        start = self.pos
        while self.pos < self.length and self.text[self.pos] != '"':
            if self.text[self.pos] == "\\":
                self.pos += 1
            self.pos += 1
        s = self.text[start:self.pos]
        self._expect('"')
        return s.replace("\\n", "\n")

    def _consume_whitespace(self):
        while self.pos < self.length and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def _peek(self):
        self._consume_whitespace()
        return self.text[self.pos] if self.pos < self.length else ""

    def _advance(self):
        self.pos += 1

    def _expect(self, char):
        self._consume_whitespace()
        if self.pos >= self.length or self.text[self.pos] != char:
            raise KVParserError(f"Expected '{char}' at pos {self.pos}")
        self.pos += 1

    def _is_number(self, word: str) -> bool:
        return re.match(r"^-?\d+(\.\d+)?$", word) is not None
