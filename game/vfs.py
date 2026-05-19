from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from game.documents import SupportingDocument


@dataclass
class VFSNode:
    name: str
    is_directory: bool
    parent: Optional[VFSNode] = None
    children: Optional[Dict[str, VFSNode]] = None  # None for files
    content: Optional[str] = None  # For text files
    document: Optional[SupportingDocument] = None  # For doc files


class VirtualFileSystem:
    def __init__(
        self,
        briefing: str,
        rules: List[str],
        objectives_text: str,
        documents: List[SupportingDocument],
    ) -> None:
        self.root = VFSNode(name="", is_directory=True, children={})
        self.cwd_node = self.root

        # Add text files to root
        self._add_file(self.root, "briefing.txt", briefing)
        self._add_file(self.root, "rules.txt", "\n".join(f"- {r}" for r in rules))
        self._add_file(self.root, "objectives.txt", objectives_text)
        self._add_file(
            self.root,
            "system_info.txt",
            (
                "========================================\n"
                " THE LEDGER HEIST TERMINAL v4.2.1\n"
                " CODENAME: NEON_AUDITOR\n"
                " STATUS: ONLINE\n"
                " SECURITY LEVEL: OPERATOR\n"
                " DECRYPTION KEY: ENABLED\n"
                "========================================\n"
            ),
        )

        # Add documents grouped by type folder
        for doc in documents:
            # Group into folders like invoices/, receipts/, contracts/...
            folder_name = f"{doc.document_type}s"
            folder_node = self._get_or_create_dir(self.root, folder_name)
            self._add_doc_file(folder_node, f"{doc.document_id}.doc", doc)

    def _add_file(self, parent: VFSNode, name: str, content: str) -> VFSNode:
        node = VFSNode(name=name, is_directory=False, parent=parent, content=content)
        if parent.children is not None:
            parent.children[name.lower()] = node
        return node

    def _add_doc_file(self, parent: VFSNode, name: str, doc: SupportingDocument) -> VFSNode:
        node = VFSNode(name=name, is_directory=False, parent=parent, document=doc)
        if parent.children is not None:
            parent.children[name.lower()] = node
        return node

    def _get_or_create_dir(self, parent: VFSNode, name: str) -> VFSNode:
        key = name.lower()
        if parent.children is not None and key in parent.children:
            return parent.children[key]
        node = VFSNode(name=name, is_directory=True, parent=parent, children={})
        if parent.children is not None:
            parent.children[key] = node
        return node

    def get_path_string(self) -> str:
        parts = []
        curr = self.cwd_node
        while curr and curr != self.root:
            parts.append(curr.name)
            curr = curr.parent
        return "/" + "/".join(reversed(parts))

    def resolve_path(self, path: str) -> Optional[VFSNode]:
        if not path:
            return self.cwd_node

        path = path.strip()
        if path.startswith("/"):
            curr = self.root
            parts = [p for p in path.split("/") if p]
        else:
            curr = self.cwd_node
            parts = [p for p in path.split("/") if p]

        for part in parts:
            part_lower = part.lower()
            if part == ".":
                continue
            elif part == "..":
                if curr.parent:
                    curr = curr.parent
            elif curr.children and part_lower in curr.children:
                curr = curr.children[part_lower]
            else:
                return None
        return curr

    def cd(self, path: str) -> Union[str, bool]:
        node = self.resolve_path(path)
        if not node:
            return f"Directory not found: '{path}'"
        if not node.is_directory:
            return f"Not a directory: '{path}'"
        self.cwd_node = node
        return True

    def ls(self, path: str = "") -> Union[str, List[VFSNode]]:
        node = self.resolve_path(path)
        if not node:
            return f"Path not found: '{path}'"
        if not node.is_directory:
            return f"Not a directory: '{path}'"
        if node.children is None:
            return []
        return list(node.children.values())
