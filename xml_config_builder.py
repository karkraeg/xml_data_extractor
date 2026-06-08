#!/usr/bin/env python3
"""Interactive XML configuration builder for xml-extractor."""

import sys
from pathlib import Path
from typing import Dict, List, Optional

import click
import yaml
from lxml import etree
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Tree,
)
from textual.widgets.tree import TreeNode


# ── Namespace helpers ──────────────────────────────────────────────────────────

def collect_namespaces(root: etree._Element) -> Dict[str, str]:
    """Collect all namespace URI→prefix mappings from the document."""
    ns: Dict[str, str] = {}
    for el in root.iter():
        for prefix, uri in (el.nsmap or {}).items():
            if uri and uri not in ns.values():
                if prefix:
                    ns[prefix] = uri
                elif "default" not in ns:
                    ns["default"] = uri
    return ns


def tag_to_qualified(tag: str, ns: Dict[str, str]) -> str:
    """Convert Clark notation {uri}local to prefix:local using ns map."""
    if not isinstance(tag, str) or not tag.startswith("{"):
        return tag
    uri = tag[1 : tag.index("}")]
    local = tag[tag.index("}") + 1 :]
    prefix = next((p for p, u in ns.items() if u == uri), None)
    return f"{prefix}:{local}" if prefix else local


def make_element_xpath(element: etree._Element, ns: Dict[str, str]) -> str:
    return f".//{tag_to_qualified(element.tag, ns)}/text()"


def make_attr_xpath(element: etree._Element, ns: Dict[str, str], attr: str) -> str:
    return f".//{tag_to_qualified(element.tag, ns)}/@{attr}"


def make_root_xpath(element: etree._Element, ns: Dict[str, str]) -> str:
    return f".//{tag_to_qualified(element.tag, ns)}"


def display_tag(element: etree._Element, ns: Dict[str, str]) -> str:
    return tag_to_qualified(element.tag, ns)


def suggested_column(element: etree._Element, ns: Dict[str, str], attr: Optional[str] = None) -> str:
    tag = tag_to_qualified(element.tag, ns).split(":")[-1]
    if attr:
        return attr.lstrip("@").capitalize()
    return tag.capitalize()


# ── Custom Tree widget ────────────────────────────────────────────────────────

class XMLTree(Tree):
    """Tree with right/left arrow keys for expand/collapse instead of scroll."""

    DEFAULT_CSS = """
    XMLTree {
        overflow-x: hidden;
    }
    """

    def on_key(self, event) -> None:
        node = self.cursor_node
        if event.key == "right" and node is not None:
            event.stop()
            event.prevent_default()
            if not node.is_expanded:
                node.expand()
            elif node.children:
                self.move_cursor(node.children[0])
        elif event.key == "left" and node is not None:
            event.stop()
            event.prevent_default()
            if node.is_expanded:
                node.collapse()
            elif node.parent and node.parent.data is not None:
                self.move_cursor(node.parent)


# ── Node data types ────────────────────────────────────────────────────────────

class ElemData:
    def __init__(self, element: etree._Element):
        self.element = element
        self.is_attr = False


class AttrData:
    def __init__(self, element: etree._Element, attr: str, value: str):
        self.element = element
        self.attr = attr
        self.value = value
        self.is_attr = True


# ── Modal screens ──────────────────────────────────────────────────────────────

class WelcomeDialog(ModalScreen):
    """Startup instructions for Phase 1."""

    DEFAULT_CSS = """
    WelcomeDialog {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: solid $primary;
        padding: 1 3;
        width: 64;
        height: auto;
    }
    #title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #body {
        margin-bottom: 1;
        color: $text;
    }
    #hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #btn-row {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("enter", "ok", "OK"), Binding("escape", "ok", "OK")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Step 1 — Select the root element", id="title")
            yield Label(
                "Navigate the XML tree with the arrow keys and press [bold]Enter[/bold] "
                "on the element that represents one record (one output row).\n\n"
                "Example: in an OAI-PMH feed, that would be [bold]oai_dc:dc[/bold].",
                id="body",
            )
            with Horizontal(id="btn-row"):
                yield Button("Got it", variant="primary", id="btn-ok")

    @on(Button.Pressed, "#btn-ok")
    def action_ok(self) -> None:
        self.dismiss(None)


class ColumnDialog(ModalScreen):
    """Ask user for a column name for the selected XPath."""

    DEFAULT_CSS = """
    ColumnDialog {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: solid $primary;
        padding: 1 3;
        width: 64;
        height: auto;
    }
    #xpath-label {
        color: $text-muted;
        margin-bottom: 1;
    }
    #xpath-value {
        color: $success;
        margin-bottom: 1;
        overflow-x: auto;
    }
    #col-input {
        margin-bottom: 1;
    }
    #btn-row {
        height: auto;
        align: right middle;
    }
    Button { margin-left: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, xpath: str, suggested: str = ""):
        super().__init__()
        self.xpath = xpath
        self.suggested = suggested

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("XPath:", id="xpath-label")
            yield Static(self.xpath, id="xpath-value")
            yield Input(value=self.suggested, placeholder="Column name", id="col-input")
            yield Label("Separator (for multiple values):", id="sep-label")
            yield Input(value=" | ", placeholder="e.g.  |  or ,", id="sep-input")
            with Horizontal(id="btn-row"):
                yield Button("Add", variant="primary", id="btn-add")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        inp = self.query_one("#col-input", Input)
        inp.focus()
        inp.action_end()

    @on(Input.Submitted)
    def submitted(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#btn-add")
    def pressed_add(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _confirm(self) -> None:
        column = self.query_one("#col-input", Input).value.strip()
        if not column:
            self.dismiss(None)
            return
        separator = self.query_one("#sep-input", Input).value
        self.dismiss({"column": column, "separator": separator})


class SaveDialog(ModalScreen):
    """Ask user where to save the config YAML."""

    DEFAULT_CSS = """
    SaveDialog {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: solid $primary;
        padding: 1 3;
        width: 50;
        height: auto;
    }
    #btn-row {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    Button { margin-left: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, default: str = "config.yaml"):
        super().__init__()
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Save config as:")
            yield Input(value=self.default, id="path-input")
            with Horizontal(id="btn-row"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    @on(Input.Submitted)
    def submitted(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#btn-save")
    def pressed_save(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _confirm(self) -> None:
        value = self.query_one("#path-input", Input).value.strip()
        self.dismiss(Path(value) if value else None)


class RunDialog(ModalScreen):
    """Ask user whether to run extraction immediately."""

    DEFAULT_CSS = """
    RunDialog {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: solid $success;
        padding: 1 3;
        width: 50;
        height: auto;
    }
    #btn-row {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    Button { margin-left: 1; }
    """

    def __init__(self, config_path: Path, input_dir: Path):
        super().__init__()
        self.config_path = config_path
        self.input_dir = input_dir

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Saved to [bold]{self.config_path}[/bold]")
            yield Label(f"Run extraction now on all XML files in [bold]{self.input_dir}[/bold]?")
            with Horizontal(id="btn-row"):
                yield Button("Run", variant="success", id="btn-run")
                yield Button("Exit", id="btn-exit")

    @on(Button.Pressed, "#btn-run")
    def do_run(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#btn-exit")
    def do_exit(self) -> None:
        self.dismiss(False)


# ── Main App ───────────────────────────────────────────────────────────────────

PHASE_ROOT = "root"
PHASE_FIELDS = "fields"


class ConfigBuilderApp(App):
    """Interactive XML → YAML config builder."""

    TITLE = "xml-config-builder"
    SUB_TITLE = "Build xml-extractor configs interactively"

    DEFAULT_CSS = """
    #main {
        layout: horizontal;
        height: 1fr;
        overflow: hidden hidden;
    }
    #tree-pane {
        width: 1fr;
        border: solid $primary;
        padding: 0 1;
        overflow: hidden hidden;
    }
    #fields-pane {
        width: 1fr;
        border: solid $accent;
        padding: 0 1;
        overflow: hidden hidden;
    }
    .pane-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #root-display {
        color: $success;
        margin-bottom: 1;
        overflow-x: auto;
    }
    #status {
        height: 3;
        background: $panel;
        padding: 0 2;
        content-align: left middle;
        color: $text-muted;
    }
    #fields-table {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("s", "save", "Save config"),
        Binding("d", "delete_field", "Delete field"),
        Binding("r", "reset", "Reset"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, xml_file: Path):
        super().__init__()
        self.xml_file = xml_file
        self.ns: Dict[str, str] = {}
        self.phase = PHASE_ROOT
        self.root_xpath: Optional[str] = None
        self.root_element: Optional[etree._Element] = None
        self.fields: List[Dict[str, str]] = []
        self.run_config: Optional[Path] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="tree-pane"):
                yield Static("XML Tree", classes="pane-title")
                yield XMLTree("document", id="xml-tree")
            with Vertical(id="fields-pane"):
                yield Static("Mapped Fields", classes="pane-title")
                yield Static("root_xpath: (not selected)", id="root-display")
                yield DataTable(id="fields-table", cursor_type="row")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        self._load_xml()
        self._update_status()
        self.push_screen(WelcomeDialog())

    def _load_xml(self) -> None:
        parser = etree.XMLParser(remove_blank_text=True, recover=True)
        tree = etree.parse(str(self.xml_file), parser)
        root = tree.getroot()
        self.ns = collect_namespaces(root)
        self._populate_tree(root)

    def _populate_tree(self, root: etree._Element, subtree_root: Optional[etree._Element] = None) -> None:
        target = subtree_root if subtree_root is not None else root
        widget = self.query_one("#xml-tree", XMLTree)
        widget.clear()
        label = display_tag(target, self.ns)
        if subtree_root is not None:
            label += "  [dim](record root)[/dim]"
        widget.root.set_label(label)
        widget.root.data = ElemData(target)
        self._add_children(widget.root, target, depth=0)
        widget.root.expand()

    def _add_children(self, node: TreeNode, el: etree._Element, depth: int) -> None:
        if depth >= 12:
            return
        for attr_name, attr_val in el.attrib.items():
            preview = attr_val[:50]
            child = node.add_leaf(f"[dim]@{attr_name}[/dim] = {preview}")
            child.data = AttrData(el, attr_name, attr_val)
        for child_el in el:
            if not isinstance(child_el.tag, str):
                continue
            tag = display_tag(child_el, self.ns)
            text = (child_el.text or "").strip()
            preview = f"  [dim]{text[:40]}[/dim]" if text else ""
            has_children = bool(len(child_el) or child_el.attrib)
            if has_children:
                child_node = node.add(f"{tag}{preview}")
            else:
                child_node = node.add_leaf(f"{tag}{preview}")
            child_node.data = ElemData(child_el)
            self._add_children(child_node, child_el, depth + 1)

    def _setup_table(self) -> None:
        table = self.query_one("#fields-table", DataTable)
        table.add_column("Column", width=20)
        table.add_column("XPath")

    def _refresh_table(self) -> None:
        table = self.query_one("#fields-table", DataTable)
        table.clear()
        for f in self.fields:
            table.add_row(f["column"], f["xpath"])

    def _update_status(self) -> None:
        if self.phase == PHASE_ROOT:
            msg = "Phase 1 — Navigate to the RECORD element (one row = one record), press Enter to set as root_xpath"
        else:
            msg = "Phase 2 — Navigate to a field, press Enter to map it  |  [S] save  |  [D] delete selected  |  [R] reset"
        self.query_one("#status", Static).update(msg)

    def _update_root_display(self) -> None:
        self.query_one("#root-display", Static).update(
            f"root_xpath: [bold]{self.root_xpath}[/bold]"
        )

    @on(Tree.NodeSelected)
    def on_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if data is None:
            return

        if self.phase == PHASE_ROOT:
            if data.is_attr:
                self.notify("Select an element, not an attribute, as root", severity="warning")
                return
            self.root_element = data.element
            self.root_xpath = make_root_xpath(data.element, self.ns)
            self._update_root_display()
            self.phase = PHASE_FIELDS
            self._update_status()
            self._populate_tree(None, subtree_root=data.element)

        elif self.phase == PHASE_FIELDS:
            if data.is_attr:
                xpath = make_attr_xpath(data.element, self.ns, data.attr)
                sug = suggested_column(data.element, self.ns, data.attr)
            else:
                xpath = make_element_xpath(data.element, self.ns)
                sug = suggested_column(data.element, self.ns)

            def add_field(result: Optional[dict]) -> None:
                if result:
                    field = {"column": result["column"], "xpath": xpath}
                    if result["separator"] != " | ":
                        field["separator"] = result["separator"]
                    self.fields.append(field)
                    self._refresh_table()

            self.push_screen(ColumnDialog(xpath, sug), add_field)

    def action_delete_field(self) -> None:
        if self.phase != PHASE_FIELDS or not self.fields:
            return
        table = self.query_one("#fields-table", DataTable)
        idx = table.cursor_row
        if 0 <= idx < len(self.fields):
            self.fields.pop(idx)
            self._refresh_table()

    def action_reset(self) -> None:
        self.phase = PHASE_ROOT
        self.root_xpath = None
        self.root_element = None
        self.fields = []
        self._refresh_table()
        self.query_one("#root-display", Static).update("root_xpath: (not selected)")
        self._load_xml()
        self._update_status()

    def action_save(self) -> None:
        if not self.root_xpath:
            self.notify("Select a root element first (Phase 1)", severity="error")
            return
        if not self.fields:
            self.notify("Map at least one field first", severity="warning")
            return

        default = self.xml_file.stem + "_config.yaml"

        def on_path(path: Optional[Path]) -> None:
            if not path:
                return
            self._write_yaml(path)

        self.push_screen(SaveDialog(default), on_path)

    def _write_yaml(self, path: Path) -> None:
        config = {
            "input_directory": str(self.xml_file.parent),
            "output_file": path.stem.removesuffix("_config"),
            "root_xpath": self.root_xpath,
            "namespaces": self.ns,
            "fields": self.fields,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")
            return

        def on_run(should_run: Optional[bool]) -> None:
            self.run_config = path if should_run else None
            self.exit(self.run_config)

        self.push_screen(RunDialog(path, self.xml_file.parent), on_run)


# ── CLI ────────────────────────────────────────────────────────────────────────

@click.command()
@click.argument("xml_file", type=click.Path(exists=True, path_type=Path))
def main(xml_file: Path) -> None:
    """Interactively build an xml-extractor config from an XML sample file."""
    app = ConfigBuilderApp(xml_file)
    result = app.run()  # returns config Path if user chose "Run", else None

    if result:
        click.echo(f"\nRunning extraction with {result} …\n")
        try:
            from xml_extractor import cli
            cli(args=["run", str(result)], standalone_mode=False)
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
