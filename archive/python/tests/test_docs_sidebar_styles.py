from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_sidebar_group_label_has_no_global_vertical_offset() -> None:
    css = (REPO_ROOT / "docs" / "src" / "styles" / "custom.css").read_text()

    assert ".sidebar-content .group-label {\n  margin-top:" not in css


def test_sidebar_group_label_centers_against_caret_in_component() -> None:
    component = (
        REPO_ROOT / "docs" / "src" / "components" / "SidebarSublist.astro"
    ).read_text()

    assert (
        "\t.group-label {\n\t\tdisplay: inline-flex;\n\t\talign-items: center;"
        in component
    )
    assert "\t\tmargin-block-start: 0;" in component
