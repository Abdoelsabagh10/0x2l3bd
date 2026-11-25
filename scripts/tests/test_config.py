"""Configuration and repository hygiene tests.

Checks the things that break silently: a malformed opencode.json, a skill whose
frontmatter OpenCode cannot read, a lost license attribution, or a personal
absolute path leaking into a tracked file.

Run: python -m unittest discover -s scripts/tests -p "test_*.py"
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ATTRIBUTION_MARKERS = ("Claude-BugHunter", "CC BY 4.0", "Sachin Sharma")
PERSONAL_PATH = re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\"]+|/Users/[A-Za-z0-9._-]+/")
SECRET_PATTERN = re.compile(r"ntn_[A-Za-z0-9]{10,}|secret_[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}")


def read_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            return None
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key.strip()] = value
    return None


class OpencodeConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(read_text("opencode.json"))
        cls.servers = cls.config["mcp"]["servers"]

    def test_config_parses_and_targets_v2_schema(self) -> None:
        self.assertEqual(self.config["$schema"], "https://opencode.ai/config.json")
        self.assertIsInstance(self.servers, dict)
        self.assertNotIn("mcpServers", self.config, "V2 uses mcp.servers")

    def test_every_server_is_a_local_stdio_command(self) -> None:
        for name, server in self.servers.items():
            with self.subTest(server=name):
                self.assertEqual(server["type"], "local")
                self.assertIsInstance(server["command"], list)
                self.assertTrue(server["command"], "command must not be empty")
                self.assertTrue(all(isinstance(part, str) for part in server["command"]))

    def test_no_absolute_personal_paths_in_tracked_config(self) -> None:
        for name, server in self.servers.items():
            with self.subTest(server=name):
                joined = " ".join(server["command"])
                self.assertNotRegex(joined, r"(?:^|\s)[A-Za-z]:[\\/]")
                self.assertNotIn("Users", joined)

    def test_burp_jar_is_relative_and_gitignored(self) -> None:
        command = self.servers["burp"]["command"]
        jar = [part for part in command if part.endswith(".jar")]
        self.assertEqual(len(jar), 1, "expected exactly one JAR argument")
        self.assertEqual(jar[0], "tools/mcp/burp/mcp-proxy.jar")
        self.assertTrue(jar[0].startswith("tools/"), "tools/ is gitignored")

    def test_notion_connections_stay_separate(self) -> None:
        self.assertIn("notion-main", self.servers)
        self.assertIn("notion-bb", self.servers)
        self.assertNotEqual(self.servers["notion-main"], self.servers["notion-bb"])
        main = " ".join(self.servers["notion-main"]["command"])
        bb = " ".join(self.servers["notion-bb"]["command"])
        self.assertIn("notion-main.mjs", main)
        self.assertIn("notion-bb.mjs", bb)

    def test_optional_servers_are_disabled_by_default(self) -> None:
        self.assertIs(self.servers["otpkit"].get("disabled"), True)
        self.assertIs(self.servers["playwright"].get("disabled"), True)

    def test_playwright_does_not_duplicate_the_native_browser(self) -> None:
        enabled = [name for name, server in self.servers.items() if not server.get("disabled")]
        self.assertNotIn("playwright", enabled)
        self.assertIn("browser", read_text("docs/integrations/browser.md").lower())

    def test_env_example_documents_required_variables(self) -> None:
        example = read_text(".env.example")
        for name in ("NOTION_TOKEN_MAIN", "NOTION_TOKEN_BB"):
            with self.subTest(variable=name):
                self.assertIn(name, example)
        self.assertIn("FIVESIM_API_KEY", example)
        self.assertIn("SMSPOOL_API_KEY", example)


class GitignoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ignore = read_text(".gitignore").splitlines()

    def test_sensitive_paths_are_ignored(self) -> None:
        for entry in (".env", "tools/", "programs/*", "shared/tools.local.json", "*.bak"):
            with self.subTest(entry=entry):
                self.assertIn(entry, self.ignore)

    def test_template_program_is_tracked(self) -> None:
        self.assertIn("!programs/_template/", self.ignore)


class ToolRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(read_text("shared/tools.json"))

    def test_registry_parses_with_expected_keys(self) -> None:
        for key in ("version", "stages", "system", "system_policy"):
            self.assertIn(key, self.registry)

    def test_system_entries_resolve_from_path(self) -> None:
        for entry in self.registry["system"]:
            with self.subTest(tool=entry["name"]):
                self.assertEqual(entry.get("resolve"), "path")
                self.assertNotIn("path", entry, "absolute paths belong in tools.local.json")
                self.assertTrue(entry.get("candidates"))

    def test_no_personal_absolute_paths_in_registry(self) -> None:
        self.assertNotRegex(read_text("shared/tools.json"), r"[A-Za-z]:\\\\Users")


class SkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_dirs = sorted(
            path for path in (ROOT / ".opencode" / "skills").iterdir() if path.is_dir()
        )

    def test_at_least_one_skill_exists(self) -> None:
        self.assertGreaterEqual(len(self.skill_dirs), 10)

    def test_each_skill_has_valid_frontmatter(self) -> None:
        seen: set[str] = set()
        for directory in self.skill_dirs:
            with self.subTest(skill=directory.name):
                skill_file = directory / "SKILL.md"
                self.assertTrue(skill_file.is_file(), f"{directory.name} has no SKILL.md")
                text = skill_file.read_text(encoding="utf-8")
                front = parse_frontmatter(text)
                self.assertIsNotNone(front, "missing or malformed frontmatter")
                assert front is not None
                self.assertEqual(set(front), {"name", "description"})
                self.assertEqual(front["name"], directory.name)
                self.assertGreaterEqual(len(front["description"]), 40)
                self.assertNotIn(front["name"], seen, "duplicate skill name")
                seen.add(front["name"])

    def test_imported_skills_keep_attribution(self) -> None:
        for directory in self.skill_dirs:
            with self.subTest(skill=directory.name):
                head = (directory / "SKILL.md").read_text(encoding="utf-8")[:2000]
                for marker in ATTRIBUTION_MARKERS:
                    self.assertIn(marker, head, f"missing attribution marker: {marker}")

    def test_skills_are_not_copied_into_programs(self) -> None:
        programs = ROOT / "programs"
        if not programs.is_dir():
            self.skipTest("no programs directory")
        for found in programs.rglob("SKILL.md"):
            self.fail(f"skill copied into a program: {found}")

    def test_skill_index_documents_every_import(self) -> None:
        index = read_text("docs/skills.md")
        for directory in self.skill_dirs:
            with self.subTest(skill=directory.name):
                self.assertIn(f"`{directory.name}`", index)
        self.assertIn("Claude-BugHunter", index)
        self.assertIn("CC BY 4.0", index)


class ReadOnlyFilterTests(unittest.TestCase):
    def test_notion_main_uses_the_filter(self) -> None:
        bridge = read_text("scripts/mcp/notion-main.mjs")
        self.assertIn("readonly-filter.mjs", bridge)
        self.assertIn("NOTION_READ_ONLY_TOOLS", bridge)
        self.assertIn("runProxy", bridge)

    def test_notion_bb_is_not_filtered(self) -> None:
        bridge = read_text("scripts/mcp/notion-bb.mjs")
        self.assertNotIn("readonly-filter", bridge)

    def test_allowlist_is_reads_only(self) -> None:
        source = read_text("scripts/mcp/readonly-filter.mjs")
        allowlist = re.search(
            r"NOTION_READ_ONLY_TOOLS = \[(.*?)\];", source, re.DOTALL
        )
        self.assertIsNotNone(allowlist, "allowlist not found")
        assert allowlist is not None
        names = re.findall(r'"([^"]+)"', allowlist.group(1))
        self.assertEqual(len(names), 14)
        write_verbs = ("create", "update", "delete", "patch", "post-page", "move")
        for name in names:
            with self.subTest(tool=name):
                self.assertFalse(
                    any(verb in name for verb in write_verbs),
                    f"{name} looks like a write tool",
                )


class RepositoryHygieneTests(unittest.TestCase):
    def test_license_and_notice_exist(self) -> None:
        self.assertIn("MIT License", read_text("LICENSE"))
        notice = read_text("NOTICE")
        self.assertIn("CC BY 4.0", notice)
        self.assertIn("Copyright (c) 2026 Sachin Sharma", notice)

    def test_no_secrets_or_personal_paths_in_docs(self) -> None:
        for relative in ("README.md", "NOTICE", "docs/skills.md"):
            with self.subTest(file=relative):
                text = read_text(relative)
                self.assertIsNone(SECRET_PATTERN.search(text))
                self.assertIsNone(PERSONAL_PATH.search(text))

    def test_sources_have_no_absolute_personal_paths(self) -> None:
        offenders = []
        skip_dirs = {".git", "tools", "programs", "__pycache__"}
        # Machine-local overrides are intentionally absolute and gitignored.
        skip_files = {"shared/tools.local.json", ".env"}
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if skip_dirs & set(relative.parts):
                continue
            if relative.as_posix() in skip_files:
                continue
            if path.suffix.lower() not in {".json", ".md", ".py", ".mjs", ".example"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if re.search(r"(?:^|\s)[A-Za-z]:\\\\Users", text, re.MULTILINE):
                offenders.append(relative.as_posix())
        self.assertEqual(offenders, [], f"personal paths found in: {offenders}")


if __name__ == "__main__":
    unittest.main()
