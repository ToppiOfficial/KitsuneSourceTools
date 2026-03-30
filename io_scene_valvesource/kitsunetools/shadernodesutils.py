
def _get_socket_items(self, context):
    node = self.get_node()
    if not node or not hasattr(node, "outputs") or not node.outputs:
        return [('0', 'None', '')]
    return [(str(i), f"{o.name} [{o.type}]", "") for i, o in enumerate(node.outputs)]