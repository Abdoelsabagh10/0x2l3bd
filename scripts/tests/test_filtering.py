"""Unit tests for the Phase 3 shared utilities."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bbh import (  # noqa: E402
    InputError,
    RunConflict,
    ScopeError,
)
from bbh import classify as classify_mod  # noqa: E402
from bbh import cli  # noqa: E402
from bbh import dedupe as dedupe_mod  # noqa: E402
from bbh import normalize as norm  # noqa: E402
from bbh import runs as runs_mod  # noqa: E402
from bbh.scope import (  # noqa: E402
    Scope,
    load_scope,
    parse_scope_text,
)

BASE_SCOPE = {
    "program": "acme",
    "in_scope": ["acme.test", "*.acme.test", "203.0.113.10"],
    "out_of_scope": [
        "admin.acme.test",
        "*.internal.acme.test",
        "https://acme.test/private",
    ],
    "allowed_ports": [],
    "restrictions": ["No brute force"],
    "updated": "2026-11-07",
    "notes": "",
}


def scope_text(**overrides) -> str:
    data = dict(BASE_SCOPE)
    data.update(overrides)
    body = json.dumps(data, indent=2)
    return "# Scope\n\n```json\n%s\n```\n\nProse only.\n" % body


def scope_obj(**overrides) -> Scope:
    return Scope(parse_scope_text(scope_text(**overrides)))


def verdict(scope: Scope, kind: str, value: str) -> str:
    if kind == "host":
        return scope.check_host(value).verdict
    return scope.check_url(value).verdict


class ScopeParsingTests(unittest.TestCase):
    def test_valid_scope_parses(self):
        scope = scope_obj()
        self.assertEqual(scope.program, "acme")
        self.assertEqual(len(scope.in_scope), 3)
        self.assertEqual(len(scope.out_of_scope), 3)
        self.assertEqual(scope.restrictions, ("No brute force",))

    def test_missing_block_rejected(self):
        with self.assertRaises(ScopeError):
            parse_scope_text("# no scope here\n")

    def test_unterminated_block_rejected(self):
        with self.assertRaises(ScopeError):
            parse_scope_text('```json\n{"program": "acme"}\n')

    def test_invalid_json_rejected(self):
        with self.assertRaises(ScopeError):
            parse_scope_text("```json\n{not json}\n```\n")

    def test_missing_in_scope_rejected(self):
        with self.assertRaises(ScopeError):
            parse_scope_text('```json\n{"program": "acme"}\n```\n')

    def test_in_scope_not_list_rejected(self):
        with self.assertRaises(ScopeError):
            parse_scope_text(
                '```json\n{"program": "acme", "in_scope": "acme.test"}\n```\n'
            )

    def test_empty_entry_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=[""])

    def test_cidr_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=["10.0.0.0/8"])

    def test_regex_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=[r"^.*\.acme\.test$"])

    def test_wildcard_tld_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=["*.test"])

    def test_host_with_port_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=["acme.test:8443"])

    def test_url_with_query_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=["https://acme.test/path?x=1"])

    def test_url_with_credentials_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=["https://user:pass@acme.test/"])

    def test_invalid_ports_rejected(self):
        with self.assertRaises(ScopeError):
            scope_obj(allowed_ports=["443"])
        with self.assertRaises(ScopeError):
            scope_obj(allowed_ports=[70000])

    def test_missing_scope_file(self):
        with self.assertRaises(InputError):
            load_scope("definitely-not-here.md")


class HostScopeTests(unittest.TestCase):
    def setUp(self):
        self.scope = scope_obj()

    def test_exact_host(self):
        self.assertEqual(verdict(self.scope, "host", "acme.test"), "in_scope")

    def test_uppercase_host(self):
        self.assertEqual(verdict(self.scope, "host", "ACME.TEST"), "in_scope")

    def test_trailing_dot(self):
        self.assertEqual(verdict(self.scope, "host", "acme.test."), "in_scope")

    def test_wildcard_one_level(self):
        self.assertEqual(verdict(self.scope, "host", "www.acme.test"), "in_scope")

    def test_wildcard_deep(self):
        self.assertEqual(verdict(self.scope, "host", "a.b.acme.test"), "in_scope")

    def test_wildcard_matches_apex(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=[])
        self.assertEqual(verdict(scope, "host", "acme.test"), "in_scope")

    def test_wildcard_matches_apex_uppercase(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=[])
        self.assertEqual(verdict(scope, "host", "ACME.TEST"), "in_scope")

    def test_wildcard_matches_apex_trailing_dot(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=[])
        self.assertEqual(verdict(scope, "host", "acme.test."), "in_scope")

    def test_wildcard_matches_nested_uppercase(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=[])
        self.assertEqual(verdict(scope, "host", "A.B.ACME.TEST"), "in_scope")

    def test_wildcard_matches_apex_url(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=[])
        self.assertEqual(verdict(scope, "url", "https://acme.test/x"), "in_scope")

    def test_apex_excluded_by_exact_out_of_scope(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=["acme.test"])
        self.assertEqual(verdict(scope, "host", "acme.test"), "out_of_scope")

    def test_apex_excluded_by_out_of_scope_wildcard(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=["*.acme.test"])
        self.assertEqual(verdict(scope, "host", "acme.test"), "out_of_scope")

    def test_apex_url_excluded_by_exact_out_of_scope(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=["acme.test"])
        self.assertEqual(verdict(scope, "url", "https://acme.test/x"), "out_of_scope")

    def test_apex_still_rejects_lookalikes(self):
        scope = scope_obj(in_scope=["*.acme.test"], out_of_scope=[])
        self.assertEqual(verdict(scope, "host", "notacme.test"), "out_of_scope")
        self.assertEqual(
            verdict(scope, "host", "acme.test.attacker.test"), "out_of_scope"
        )

    def test_wildcard_tld_still_rejected_after_apex_change(self):
        with self.assertRaises(ScopeError):
            scope_obj(in_scope=["*.test"], out_of_scope=[])

    def test_lookalike_prefix(self):
        self.assertEqual(verdict(self.scope, "host", "notacme.test"), "out_of_scope")

    def test_lookalike_suffix(self):
        self.assertEqual(
            verdict(self.scope, "host", "acme.test.attacker.test"), "out_of_scope"
        )

    def test_exclusion_exact(self):
        self.assertEqual(verdict(self.scope, "host", "admin.acme.test"), "out_of_scope")

    def test_exact_exclusion_does_not_cover_subdomains(self):
        self.assertEqual(
            verdict(self.scope, "host", "x.admin.acme.test"), "in_scope"
        )

    def test_wildcard_exclusion(self):
        self.assertEqual(
            verdict(self.scope, "host", "x.internal.acme.test"), "out_of_scope"
        )

    def test_exclusion_internal(self):
        self.assertEqual(
            verdict(self.scope, "host", "x.internal.acme.test"), "out_of_scope"
        )

    def test_ip_exact(self):
        self.assertEqual(verdict(self.scope, "host", "203.0.113.10"), "in_scope")

    def test_ip_other(self):
        self.assertEqual(verdict(self.scope, "host", "203.0.113.11"), "out_of_scope")

    def test_invalid_host_ambiguous(self):
        self.assertEqual(verdict(self.scope, "host", "bad host"), "ambiguous")

    def test_wildcard_value_ambiguous(self):
        self.assertEqual(verdict(self.scope, "host", "*.acme.test"), "ambiguous")

    def test_url_value_ambiguous(self):
        self.assertEqual(verdict(self.scope, "host", "https://acme.test"), "ambiguous")

    def test_single_label_ambiguous(self):
        self.assertEqual(verdict(self.scope, "host", "localhost"), "ambiguous")

    def test_path_scoped_only_is_ambiguous(self):
        scope = Scope(
            parse_scope_text(
                scope_text(in_scope=["https://api.acme.test/v1"], out_of_scope=[])
            )
        )
        self.assertEqual(verdict(scope, "host", "api.acme.test"), "ambiguous")


class UrlScopeTests(unittest.TestCase):
    def setUp(self):
        self.scope = scope_obj()

    def test_host_entry_any_path(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://acme.test/anything"), "in_scope"
        )

    def test_host_entry_any_scheme(self):
        self.assertEqual(
            verdict(self.scope, "url", "http://acme.test/x"), "in_scope"
        )

    def test_wildcard_subdomain(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://www.acme.test/x"), "in_scope"
        )

    def test_exclusion_path(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://acme.test/private"), "out_of_scope"
        )

    def test_exclusion_path_child(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://acme.test/private/data"),
            "out_of_scope",
        )

    def test_exclusion_is_scheme_agnostic(self):
        self.assertEqual(
            verdict(self.scope, "url", "http://acme.test/private"), "out_of_scope"
        )

    def test_public_path_in_scope(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://acme.test/public"), "in_scope"
        )

    def test_userinfo_attack(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://acme.test@evil.test/"),
            "out_of_scope",
        )

    def test_query_host_attack(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://evil.test/?next=acme.test"),
            "out_of_scope",
        )

    def test_backslash_ambiguous(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://acme.test\\@evil.test/"),
            "ambiguous",
        )

    def test_unsupported_scheme_ambiguous(self):
        self.assertEqual(verdict(self.scope, "url", "ftp://acme.test/"), "ambiguous")

    def test_garbage_ambiguous(self):
        self.assertEqual(verdict(self.scope, "url", "not a url"), "ambiguous")

    def test_ip_url(self):
        self.assertEqual(
            verdict(self.scope, "url", "http://203.0.113.10/"), "in_scope"
        )

    def test_query_is_ignored_for_scope(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://acme.test/search?b=2&a=1"),
            "in_scope",
        )


class UrlPrefixTests(unittest.TestCase):
    def setUp(self):
        self.scope = Scope(
            parse_scope_text(
                scope_text(in_scope=["https://api.acme.test/v1"], out_of_scope=[])
            )
        )

    def test_prefix_exact(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://api.acme.test/v1"), "in_scope"
        )

    def test_prefix_child(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://api.acme.test/v1/users"), "in_scope"
        )

    def test_prefix_boundary(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://api.acme.test/v1beta"),
            "out_of_scope",
        )

    def test_scheme_mismatch(self):
        self.assertEqual(
            verdict(self.scope, "url", "http://api.acme.test/v1"), "out_of_scope"
        )

    def test_other_path(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://api.acme.test/v2"), "out_of_scope"
        )

    def test_other_subdomain(self):
        self.assertEqual(
            verdict(self.scope, "url", "https://www.api.acme.test/v1"),
            "out_of_scope",
        )


class PortScopeTests(unittest.TestCase):
    def test_empty_ports_unrestricted(self):
        scope = scope_obj(out_of_scope=[])
        self.assertEqual(
            verdict(scope, "url", "https://acme.test:8443/"), "in_scope"
        )

    def test_implicit_default_allowed(self):
        scope = Scope(
            parse_scope_text(
                scope_text(in_scope=["acme.test"], out_of_scope=[], allowed_ports=[443])
            )
        )
        self.assertEqual(verdict(scope, "url", "https://acme.test/"), "in_scope")

    def test_explicit_port_denied(self):
        scope = Scope(
            parse_scope_text(
                scope_text(in_scope=["acme.test"], out_of_scope=[], allowed_ports=[443])
            )
        )
        self.assertEqual(
            verdict(scope, "url", "https://acme.test:8443/"), "out_of_scope"
        )

    def test_http_default_denied(self):
        scope = Scope(
            parse_scope_text(
                scope_text(in_scope=["acme.test"], out_of_scope=[], allowed_ports=[443])
            )
        )
        self.assertEqual(verdict(scope, "url", "http://acme.test/"), "out_of_scope")


class NormalizeTests(unittest.TestCase):
    def test_host_from_url(self):
        self.assertEqual(
            norm.normalize_host_line("HTTPS://WWW.ACME.TEST:8443/path?q=1"),
            "www.acme.test",
        )

    def test_host_with_port(self):
        self.assertEqual(norm.normalize_host_line("acme.test:8080"), "acme.test")

    def test_host_trailing_dot(self):
        self.assertEqual(norm.normalize_host_line("acme.test."), "acme.test")

    def test_host_ipv4(self):
        self.assertEqual(norm.normalize_host_line("1.2.3.4:80"), "1.2.3.4")

    def test_host_ipv6(self):
        self.assertEqual(
            norm.normalize_host_line("[2001:db8::1]:443"), "2001:db8::1"
        )

    def test_host_invalid_passthrough(self):
        self.assertEqual(norm.normalize_host_line("*.acme.test"), "*.acme.test")

    def test_host_blank(self):
        self.assertIsNone(norm.normalize_host_line("   "))

    def test_url_fragment_removed(self):
        self.assertEqual(
            norm.canonical_url("https://acme.test/a#frag"), "https://acme.test/a"
        )

    def test_url_default_port_removed(self):
        self.assertEqual(
            norm.canonical_url("https://acme.test:443/a"), "https://acme.test/a"
        )

    def test_url_query_sorted(self):
        self.assertEqual(
            norm.canonical_url("https://acme.test/?b=2&a=1"),
            "https://acme.test/?a=1&b=2",
        )

    def test_url_duplicate_slashes_collapsed(self):
        self.assertEqual(
            norm.canonical_url("https://acme.test//a///b"), "https://acme.test/a/b"
        )

    def test_url_uppercase_host(self):
        self.assertEqual(
            norm.canonical_url("HTTPS://ACME.TEST/A"), "https://acme.test/A"
        )

    def test_url_invalid_passthrough(self):
        self.assertEqual(norm.normalize_url_line("not a url"), "not a url")

    def test_url_ftp_passthrough(self):
        self.assertEqual(norm.normalize_url_line("ftp://acme.test/"), "ftp://acme.test/")


class DedupeTests(unittest.TestCase):
    def test_order_preserved(self):
        self.assertEqual(
            dedupe_mod.dedupe_lines(["b", "a", "b", "c"]), ["b", "a", "c"]
        )

    def test_blank_and_comments_dropped(self):
        self.assertEqual(
            dedupe_mod.dedupe_lines(["", "a", "# note", "  ", "a"]), ["a"]
        )


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bbh-classify-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.urls = [
            "https://acme.test/app.js",
            "https://acme.test/logo.png",
            "https://acme.test/api/users",
            "https://api.acme.test/users",
            "https://acme.test/about",
            "https://acme.test/search?q=1&page=2",
            "https://acme.test/api/users?id=1",
            "https://acme.test/app.js?v=2",
            "https://acme.test/logo.png?x=1",
        ]

    def read_set(self, name):
        return set((self.tmp / name).read_text(encoding="utf-8").splitlines())

    def test_categories_are_mutually_exclusive(self):
        result = classify_mod.classify_lines(self.urls, self.tmp)
        self.assertEqual(result["total"], len(self.urls))
        buckets = {
            name: self.read_set(name + ".txt")
            for name in ("api", "static", "javascript", "other")
        }
        union = set().union(*buckets.values())
        self.assertEqual(union, set(self.urls))
        self.assertEqual(sum(len(value) for value in buckets.values()), len(self.urls))
        names = list(buckets)
        for left in range(len(names)):
            for right in range(left + 1, len(names)):
                self.assertFalse(buckets[names[left]] & buckets[names[right]])

    def test_with_parameters_overlaps_categories(self):
        classify_mod.classify_lines(self.urls, self.tmp)
        with_parameters = self.read_set("with-parameters.txt")
        api = self.read_set("api.txt")
        javascript = self.read_set("javascript.txt")
        self.assertIn("https://acme.test/api/users?id=1", with_parameters)
        self.assertIn("https://acme.test/app.js?v=2", with_parameters)
        self.assertIn("https://acme.test/search?q=1&page=2", with_parameters)
        self.assertNotIn("https://acme.test/about", with_parameters)
        self.assertIn("https://acme.test/api/users?id=1", api)
        self.assertIn("https://acme.test/app.js?v=2", javascript)

    def test_parameters_unique_and_sorted(self):
        classify_mod.classify_lines(self.urls, self.tmp)
        self.assertEqual(
            (self.tmp / "parameters.txt").read_text(encoding="utf-8").splitlines(),
            ["id", "page", "q", "v", "x"],
        )

    def test_javascript_precedes_static_and_api(self):
        self.assertEqual(
            classify_mod.classify_url("https://acme.test/api/app.js"), "javascript"
        )

    def test_static_precedes_api(self):
        self.assertEqual(
            classify_mod.classify_url("https://acme.test/api/logo.png"), "static"
        )

    def test_api_detection(self):
        self.assertEqual(classify_mod.classify_url("https://acme.test/graphql"), "api")
        self.assertEqual(classify_mod.classify_url("https://gateway.acme.test/x"), "api")

    def test_other_category(self):
        self.assertEqual(classify_mod.classify_url("https://acme.test/about"), "other")

    def test_empty_input_creates_empty_files(self):
        classify_mod.classify_lines([], self.tmp)
        for name in (
            "api.txt",
            "static.txt",
            "javascript.txt",
            "other.txt",
            "with-parameters.txt",
            "parameters.txt",
        ):
            self.assertTrue((self.tmp / name).is_file())
            self.assertEqual((self.tmp / name).stat().st_size, 0)


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bbh-ws-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.old_cwd = Path.cwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.old_cwd)

    def make_program(self, program="acme", **overrides):
        pdir = self.tmp / "programs" / program
        (pdir / "recon").mkdir(parents=True, exist_ok=True)
        (pdir / "program.md").write_text("# Program\n", encoding="utf-8")
        data = dict(BASE_SCOPE)
        data["program"] = program
        data.update(overrides)
        (pdir / "scope.md").write_text(scope_text(**data), encoding="utf-8")
        return pdir

    def metadata_path(self, pdir, run_id):
        return pdir / "recon" / "runs" / run_id / "run.json"

    def read_metadata(self, pdir, run_id):
        path = self.metadata_path(pdir, run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def write_metadata(self, pdir, run_id, data):
        self.metadata_path(pdir, run_id).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )


class RunsTests(WorkspaceTestCase):
    def test_init_creates_metadata_and_dirs(self):
        pdir = self.make_program()
        result = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")
        self.assertTrue(result["ok"])
        self.assertRegex(result["run_id"], r"^\d{8}-\d{6}-subdomains$")

        metadata = self.metadata_path(pdir, result["run_id"])
        self.assertTrue(metadata.is_file())
        data = self.read_metadata(pdir, result["run_id"])
        self.assertEqual(data["program"], "acme")
        self.assertEqual(data["stages"]["subdomains"]["status"], "running")
        self.assertEqual(len(data["scope_sha256"]), 64)

        for name in ("raw", "processed", "rejected", "logs"):
            root = pdir / "recon" / "subdomains" / result["run_id"] / name
            self.assertTrue(root.is_dir())

    def test_resume_running_preserves_metadata(self):
        pdir = self.make_program()
        first = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")
        run_id = first["run_id"]

        data = self.read_metadata(pdir, run_id)
        data["notes"].append("operator note")
        data["stages"]["subdomains"]["tools"].append("subfinder@2.6.0")
        self.write_metadata(pdir, run_id, data)

        second = runs_mod.init_run(
            "acme", "subdomains", "programs/acme/scope.md", run_id
        )
        self.assertTrue(second["resumed"])
        self.assertTrue(second["changed"])

        data = self.read_metadata(pdir, run_id)
        self.assertIn("operator note", data["notes"])
        self.assertIn("subfinder@2.6.0", data["stages"]["subdomains"]["tools"])
        self.assertEqual(data["stages"]["subdomains"]["status"], "running")
        self.assertEqual(data["stages"]["subdomains"]["attempts"], 2)

    def test_completed_stage_is_not_reverted(self):
        pdir = self.make_program()
        first = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")
        run_id = first["run_id"]

        data = self.read_metadata(pdir, run_id)
        data["stages"]["subdomains"]["status"] = "completed"
        data["stages"]["subdomains"]["finished_at"] = "2026-11-07T00:00:00Z"
        self.write_metadata(pdir, run_id, data)

        second = runs_mod.init_run(
            "acme", "subdomains", "programs/acme/scope.md", run_id
        )
        self.assertFalse(second["changed"])

        data = self.read_metadata(pdir, run_id)
        self.assertEqual(data["stages"]["subdomains"]["status"], "completed")
        self.assertEqual(data["stages"]["subdomains"]["attempts"], 1)

    def test_failed_stage_resumes_and_keeps_error_history(self):
        pdir = self.make_program()
        first = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")
        run_id = first["run_id"]

        data = self.read_metadata(pdir, run_id)
        data["stages"]["subdomains"]["status"] = "failed"
        data["stages"]["subdomains"]["error"] = "boom"
        self.write_metadata(pdir, run_id, data)

        runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md", run_id)
        data = self.read_metadata(pdir, run_id)
        record = data["stages"]["subdomains"]
        self.assertEqual(record["status"], "running")
        self.assertIsNone(record["error"])
        self.assertIn("boom", record["errors"])
        self.assertEqual(record["attempts"], 2)

    def test_changed_scope_refused(self):
        pdir = self.make_program()
        first = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")

        (pdir / "scope.md").write_text(
            scope_text(in_scope=["other.test"], out_of_scope=[]), encoding="utf-8"
        )
        with self.assertRaises(RunConflict):
            runs_mod.init_run(
                "acme", "subdomains", "programs/acme/scope.md", first["run_id"]
            )

        data = self.read_metadata(pdir, first["run_id"])
        self.assertEqual(data["scope_sha256"], first["scope_sha256"])

    def test_program_mismatch_refused(self):
        pdir = self.make_program()
        (pdir / "scope.md").write_text(
            scope_text(program="other"), encoding="utf-8"
        )
        with self.assertRaises(RunConflict):
            runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")

    def test_template_program_refused(self):
        (self.tmp / "programs" / "_template").mkdir(parents=True)
        with self.assertRaises(InputError):
            runs_mod.init_run(
                "_template", "subdomains", "programs/_template/scope.md"
            )

    def test_full_recon_has_no_stage_tree(self):
        pdir = self.make_program()
        result = runs_mod.init_run("acme", "full_recon", "programs/acme/scope.md")
        root = pdir / "recon" / "runs" / result["run_id"]
        self.assertTrue((root / "run.json").is_file())
        self.assertFalse((pdir / "recon" / "full_recon").exists())

    def test_verify_marks_completed(self):
        pdir = self.make_program()
        result = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")
        output = (
            pdir
            / "recon"
            / "subdomains"
            / result["run_id"]
            / "processed"
            / "subdomains.txt"
        )
        output.write_text("a.acme.test\n", encoding="utf-8")

        payload, code = runs_mod.verify_run("acme", result["run_id"], "subdomains")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        data = self.read_metadata(pdir, result["run_id"])
        self.assertEqual(data["stages"]["subdomains"]["status"], "completed")

    def test_verify_marks_failed_when_missing(self):
        pdir = self.make_program()
        result = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")

        payload, code = runs_mod.verify_run("acme", result["run_id"], "subdomains")
        self.assertEqual(code, 5)
        self.assertFalse(payload["ok"])
        self.assertIn("processed/subdomains.txt", payload["missing"])
        data = self.read_metadata(pdir, result["run_id"])
        self.assertEqual(data["stages"]["subdomains"]["status"], "failed")

    def test_verify_does_not_revert_completed(self):
        pdir = self.make_program()
        result = runs_mod.init_run("acme", "subdomains", "programs/acme/scope.md")
        output = (
            pdir
            / "recon"
            / "subdomains"
            / result["run_id"]
            / "processed"
            / "subdomains.txt"
        )
        output.write_text("a.acme.test\n", encoding="utf-8")
        runs_mod.verify_run("acme", result["run_id"], "subdomains")
        output.unlink()

        payload, code = runs_mod.verify_run("acme", result["run_id"], "subdomains")
        self.assertEqual(code, 5)
        self.assertFalse(payload["ok"])
        data = self.read_metadata(pdir, result["run_id"])
        self.assertEqual(data["stages"]["subdomains"]["status"], "completed")

    def test_verify_missing_run(self):
        self.make_program()
        with self.assertRaises(InputError):
            runs_mod.verify_run("acme", "20990101-000000-subdomains", "subdomains")


def run_cli(*argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliPipelineTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.pdir = self.make_program()
        self.run_root = self.pdir / "recon" / "subdomains" / "r1"
        for name in ("raw", "processed", "rejected", "logs"):
            (self.run_root / name).mkdir(parents=True)
        self.raw = self.run_root / "raw" / "all.txt"
        self.raw.write_text(
            "\n".join(
                [
                    "WWW.ACME.TEST",
                    "https://api.acme.test/v1",
                    "admin.acme.test",
                    "notacme.test",
                    "bad host",
                    "www.acme.test",
                    "203.0.113.10",
                    "*.acme.test",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.normalized = self.run_root / "processed" / "normalized.txt"
        self.in_scope = self.run_root / "processed" / "in-scope.txt"
        self.out_scope = self.run_root / "rejected" / "out-of-scope.txt"
        self.review = self.run_root / "rejected" / "ambiguous.txt"
        self.deduped = self.run_root / "processed" / "subdomains.txt"

    def normalize(self):
        return run_cli(
            "normalize",
            "--kind",
            "host",
            "-i",
            str(self.raw),
            "-o",
            str(self.normalized),
        )

    def check(self):
        return run_cli(
            "scope",
            "check",
            "--scope",
            "programs/acme/scope.md",
            "--kind",
            "host",
            "-i",
            str(self.normalized),
            "--in",
            str(self.in_scope),
            "--out",
            str(self.out_scope),
            "--review",
            str(self.review),
        )

    def dedupe(self):
        return run_cli(
            "dedupe", "-i", str(self.in_scope), "-o", str(self.deduped)
        )

    def test_pipeline_order_and_counts(self):
        code, out, _ = self.normalize()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 8)

        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out)["counts"],
            {"in_scope": 4, "out_of_scope": 2, "ambiguous": 2, "total": 8},
        )

        code, out, _ = self.dedupe()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 3)
        self.assertEqual(
            self.deduped.read_text(encoding="utf-8").splitlines(),
            ["www.acme.test", "api.acme.test", "203.0.113.10"],
        )

    def test_rejections_carry_reasons(self):
        self.normalize()
        self.check()
        rejected = self.out_scope.read_text(encoding="utf-8").splitlines()
        self.assertTrue(
            any("admin.acme.test" in line and "excluded by" in line for line in rejected)
        )
        self.assertTrue(
            any("notacme.test" in line and "not in scope" in line for line in rejected)
        )
        review = self.review.read_text(encoding="utf-8").splitlines()
        self.assertTrue(
            any(line.startswith("bad host") and "invalid host" in line for line in review)
        )
        self.assertTrue(
            any(
                line.startswith("*.acme.test") and "invalid host" in line
                for line in review
            )
        )

    def test_rerun_is_idempotent(self):
        self.normalize()
        self.check()
        self.dedupe()
        tracked = (
            self.normalized,
            self.in_scope,
            self.out_scope,
            self.review,
            self.deduped,
        )
        before = {path: path.read_bytes() for path in tracked}

        for step in (self.normalize, self.check, self.dedupe):
            code, _, _ = step()
            self.assertEqual(code, 0)
        for path in tracked:
            self.assertEqual(path.read_bytes(), before[path])

    def test_changed_input_refuses_overwrite(self):
        self.normalize()
        self.raw.write_text(
            self.raw.read_text(encoding="utf-8") + "new.acme.test\n",
            encoding="utf-8",
        )
        code, out, _ = self.normalize()
        self.assertEqual(code, 4)
        self.assertFalse(json.loads(out)["ok"])

    def test_scope_value_tokens(self):
        cases = (
            ("www.acme.test", "in_scope"),
            ("admin.acme.test", "out_of_scope"),
            ("bad host", "ambiguous"),
        )
        for value, expected in cases:
            code, out, _ = run_cli(
                "scope",
                "check",
                "--scope",
                "programs/acme/scope.md",
                "--kind",
                "host",
                "--value",
                value,
            )
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), expected)

    def test_classify_cli(self):
        urls = self.run_root / "processed" / "urls.txt"
        urls.write_text(
            "https://acme.test/app.js\n"
            "https://acme.test/api/x?id=1\n"
            "https://acme.test/about\n",
            encoding="utf-8",
        )
        out_dir = self.run_root / "processed" / "categories"
        code, out, _ = run_cli(
            "classify", "--kind", "url", "-i", str(urls), "--out-dir", str(out_dir)
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(
            payload["categories"],
            {"api": 1, "static": 0, "javascript": 1, "other": 1},
        )
        self.assertTrue((out_dir / "with-parameters.txt").is_file())
        self.assertEqual(
            (out_dir / "parameters.txt").read_text(encoding="utf-8").splitlines(),
            ["id"],
        )

    def test_url_pipeline_canonicalizes_and_scopes(self):
        raw = self.run_root / "raw" / "urls.txt"
        raw.write_text(
            "HTTPS://ACME.TEST:443/search?b=2&a=1\n"
            "https://acme.test/private\n"
            "ftp://acme.test/\n",
            encoding="utf-8",
        )
        normalized = self.run_root / "processed" / "urls-normalized.txt"
        in_scope = self.run_root / "processed" / "urls-in-scope.txt"
        out_scope = self.run_root / "rejected" / "urls-out.txt"
        review = self.run_root / "rejected" / "urls-review.txt"

        code, _, _ = run_cli(
            "normalize", "--kind", "url", "-i", str(raw), "-o", str(normalized)
        )
        self.assertEqual(code, 0)
        code, out, _ = run_cli(
            "scope",
            "check",
            "--scope",
            "programs/acme/scope.md",
            "--kind",
            "url",
            "-i",
            str(normalized),
            "--in",
            str(in_scope),
            "--out",
            str(out_scope),
            "--review",
            str(review),
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out)["counts"],
            {"in_scope": 1, "out_of_scope": 1, "ambiguous": 1, "total": 3},
        )
        self.assertEqual(
            in_scope.read_text(encoding="utf-8").splitlines(),
            ["https://acme.test/search?a=1&b=2"],
        )
        self.assertTrue(
            out_scope.read_text(encoding="utf-8").startswith("https://acme.test/private")
        )
        self.assertIn("ftp://acme.test/", review.read_text(encoding="utf-8"))

    def test_missing_input_exits_5(self):
        code, out, _ = run_cli(
            "normalize", "--kind", "host", "-i", "nope.txt", "-o", "out.txt"
        )
        self.assertEqual(code, 5)

    def test_invalid_scope_exits_2(self):
        bad = self.pdir / "bad-scope.md"
        bad.write_text("# no json block\n", encoding="utf-8")
        code, out, _ = run_cli(
            "scope",
            "check",
            "--scope",
            str(bad),
            "--kind",
            "host",
            "--value",
            "acme.test",
        )
        self.assertEqual(code, 2)

    def test_runs_init_cli(self):
        code, out, _ = run_cli(
            "runs",
            "init",
            "--program",
            "acme",
            "--stage",
            "subdomains",
            "--scope",
            "programs/acme/scope.md",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertTrue(Path(payload["run_json"]).is_file())


if __name__ == "__main__":
    unittest.main()
