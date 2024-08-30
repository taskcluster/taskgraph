from pathlib import Path

from hatchling.metadata.plugin.interface import MetadataHookInterface


class MetaDataHook(MetadataHookInterface):
    def update(self, metadata):
        namespace = {}
        src = Path(self.root) / "src" / "taskgraph" / "__init__.py"
        exec(src.read_text(), namespace)
        metadata["version"] = namespace["__version__"]
