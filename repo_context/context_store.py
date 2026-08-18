from __future__ import annotations

import json
import pathlib
import re
import time
from typing import Any, Iterable

from .context_evidence import make_context_evidence
from .git_provenance import file_provenance
from .storage import prepare_state_dir, state_dir
from .util import file_cache_key

SCHEMA = "repo-context-context-store/v1"
_MAX_INVALIDATIONS = 200
_MAX_REJECTED_TOMBSTONES = 1000


def _safe_session(session: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(session or "default")).strip(".-")
    return value or "default"


def _active_keys(context_pack: dict[str, Any] | None) -> tuple[set[str], set[tuple[str, str, int, int]]]:
    files: set[str] = set()
    symbols: set[tuple[str, str, int, int]] = set()
    if not isinstance(context_pack, dict):
        return files, symbols
    for item in context_pack.get("files") or []:
        if isinstance(item, dict) and item.get("path"):
            files.add(str(item["path"]))
    for item in context_pack.get("symbols") or []:
        if isinstance(item, dict) and item.get("path") and item.get("name"):
            symbols.add((
                str(item["path"]), str(item["name"]),
                int(item.get("start_line") or 1), int(item.get("end_line") or item.get("start_line") or 1),
            ))
    return files, symbols


def _context_git_revisions(context_pack: dict[str, Any] | None) -> dict[str, str]:
    revisions: dict[str, str] = {}
    if not isinstance(context_pack, dict):
        return revisions
    for group in ("files", "symbols"):
        for item in context_pack.get(group) or []:
            if not isinstance(item, dict) or not item.get("path"):
                continue
            provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
            git = provenance.get("git") if isinstance(provenance.get("git"), dict) else {}
            identity = git.get("content_identity") if isinstance(git.get("content_identity"), dict) else {}
            blob = identity.get("blob_sha")
            if isinstance(blob, str) and blob:
                revisions[str(item["path"])] = blob
    return revisions


def iter_index_evidence(index: dict[str, Any], *, tier: str = "recallable") -> Iterable[dict[str, Any]]:
    """Yield lightweight evidence locators directly from the persistent repository index."""
    for f in index.get("files") or []:
        if not isinstance(f, dict) or not f.get("path"):
            continue
        path = str(f["path"]); revision = str(f.get("stat_fingerprint") or "")
        ev = make_context_evidence(kind="file", path=path, revision=revision, tier=tier)
        ev["language"] = f.get("language"); ev["rank_score"] = f.get("rank_score")
        yield ev
        for sym in f.get("symbol_details") or []:
            if not isinstance(sym, dict) or not sym.get("name"):
                continue
            sev = make_context_evidence(
                kind="symbol", path=path, symbol=str(sym["name"]),
                start_line=int(sym.get("start_line") or 1), end_line=int(sym.get("end_line") or sym.get("start_line") or 1),
                revision=revision, tier=tier,
            )
            sev["signature"] = sym.get("signature"); sev["symbol_kind"] = sym.get("kind")
            yield sev


class RepositoryContextStore:
    """HOT overlay for repository context.

    WARM/Recallable locators live in the persistent repository index and are never copied
    into this file. This store persists only current HOT evidence, explicit rejected
    tombstones, and a bounded invalidation log.
    """

    def __init__(self, root: pathlib.Path | str, session: str = "default") -> None:
        self.root = pathlib.Path(root).resolve(); self.session = _safe_session(session)
        self.path = state_dir(self.root) / "context-stores" / f"{self.session}.json"
        self.data: dict[str, Any] = {
            "schema": SCHEMA, "version": 2, "session": self.session,
            "updated_at": int(time.time()), "items": {}, "index_summary": {}, "invalidations": [],
        }
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("schema") == SCHEMA and isinstance(loaded.get("items"), dict):
                # v1 stored WARM locators redundantly. Migrate by retaining only HOT and
                # rejected items; the persistent repository index is the WARM source.
                loaded["version"] = 2
                loaded["items"] = {
                    k: v for k, v in loaded["items"].items()
                    if isinstance(v, dict) and v.get("tier") in {"active", "rejected"}
                }
                loaded.setdefault("index_summary", {}); loaded.setdefault("invalidations", [])
                self.data = loaded
        except (OSError, json.JSONDecodeError):
            pass

    def upsert(self, evidence: dict[str, Any]) -> None:
        eid = str(evidence.get("id") or "")
        if not eid: raise ValueError("context evidence requires id")
        if evidence.get("tier") not in {"active", "rejected"}:
            raise ValueError("context store persists only active or rejected overlay items")
        old = self.data["items"].get(eid); item = dict(evidence)
        if isinstance(old, dict):
            item["last_recalled_at"] = old.get("last_recalled_at")
            item["recall_count"] = int(old.get("recall_count") or 0)
        self.data["items"][eid] = item

    def promote_evidence(self, evidence: dict[str, Any]) -> bool:
        item = dict(evidence)
        if item.get("validity") != "current": return False
        item["tier"] = "active"; item["last_recalled_at"] = int(time.time())
        existing = self.data["items"].get(item.get("id"), {})
        item["recall_count"] = int(existing.get("recall_count") or 0) + 1 if isinstance(existing, dict) else 1
        self.upsert(item)
        return True

    def remove_active(self, evidence_id: str, *, reason: str) -> bool:
        item = self.data["items"].get(evidence_id)
        if not isinstance(item, dict) or item.get("tier") != "active": return False
        self.data["items"].pop(evidence_id, None)
        self._record_invalidation(evidence_id, reason)
        return True

    def reject_evidence(self, evidence: dict[str, Any], *, reason: str, validity: str = "current") -> None:
        item = dict(evidence); item["tier"] = "rejected"; item["validity"] = validity
        item["rejection_reason"] = reason; item["rejected_at"] = int(time.time())
        self.upsert(item); self._prune_rejected()

    def _record_invalidation(self, evidence_id: str, reason: str, **extra: Any) -> None:
        rows = self.data.setdefault("invalidations", [])
        rows.append({"id": evidence_id, "reason": reason, "ts": int(time.time()), **extra})
        if len(rows) > _MAX_INVALIDATIONS: del rows[:-_MAX_INVALIDATIONS]

    def _prune_rejected(self) -> None:
        rejected = [(k, v) for k, v in self.data["items"].items() if isinstance(v, dict) and v.get("tier") == "rejected"]
        if len(rejected) <= _MAX_REJECTED_TOMBSTONES: return
        rejected.sort(key=lambda kv: int(kv[1].get("rejected_at") or 0), reverse=True)
        keep = {k for k, _ in rejected[:_MAX_REJECTED_TOMBSTONES]}
        for key, _ in rejected[_MAX_REJECTED_TOMBSTONES:]:
            if key not in keep: self.data["items"].pop(key, None)

    def items(self, tier: str | None = None, *, current_only: bool = False) -> list[dict[str, Any]]:
        rows = [dict(v) for v in self.data.get("items", {}).values() if isinstance(v, dict)]
        if tier: rows = [r for r in rows if r.get("tier") == tier]
        if current_only: rows = [r for r in rows if r.get("validity") == "current"]
        return sorted(rows, key=lambda r: (str(r.get("path") or ""), str(r.get("symbol") or ""), str(r.get("id") or "")))

    def active_ids(self) -> set[str]: return {str(x["id"]) for x in self.items("active")}
    def rejected_ids(self) -> set[str]: return {str(x["id"]) for x in self.items("rejected")}

    def reconcile_index(self, index: dict[str, Any], *, locators: list[dict[str, Any]] | None = None) -> dict[str, int]:
        """Reconcile the HOT/tombstone overlay against the current repository index.

        The repository index is the only WARM locator source. Missing-path tombstones
        must not block evidence forever after a file is recreated, and HOT evidence
        whose logical locator disappeared from the refreshed index must not remain active.
        """
        rows = list(locators) if locators is not None else list(iter_index_evidence(index))
        current_ids = {str(x.get("id") or "") for x in rows if x.get("id")}
        self.data["index_summary"] = {
            "file_count": len(index.get("files") or []),
            "symbol_count": sum(len(f.get("symbol_details") or []) for f in index.get("files") or [] if isinstance(f, dict)),
            "locator_count": len(rows),
        }
        resurrected = 0
        for item in self.items("rejected"):
            if item.get("id") in current_ids and item.get("rejection_reason") in {"repository-path-missing", "not-present-in-current-index"}:
                self.data["items"].pop(item["id"], None)
                resurrected += 1
        retired_hot = 0
        for item in self.items("active"):
            if item.get("id") not in current_ids:
                self.data["items"].pop(item["id"], None)
                self.reject_evidence(item, reason="not-present-in-current-index", validity="missing")
                self._record_invalidation(str(item.get("id") or ""), "not-present-in-current-index")
                retired_hot += 1
        current_rejected = sum(1 for item in self.items("rejected") if item.get("id") in current_ids)
        self.data["index_summary"]["current_rejected_count"] = current_rejected
        return {"locator_count": len(rows), "resurrected_tombstones": resurrected, "retired_hot": retired_hot}

    def stats(self) -> dict[str, Any]:
        active = len(self.items("active")); rejected = len(self.items("rejected"))
        summary = self.data.get("index_summary") if isinstance(self.data.get("index_summary"), dict) else {}
        total = int(summary.get("locator_count") or 0)
        current_rejected = int(summary.get("current_rejected_count") or 0)
        recallable = max(0, total - active - current_rejected)
        return {
            "schema": SCHEMA, "session": self.session,
            "counts": {"active": active, "recallable": recallable, "rejected": rejected, "invalidations": len(self.data.get("invalidations") or [])},
            "locator_source": "persistent-repository-index", "overlay_only": True, "locator_only": True,
            "warm_locators_duplicated": False, "full_source_persisted": False,
        }

    def save(self) -> None:
        prepare_state_dir(self.root); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = int(time.time()); self._prune_rejected()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(self.path)


def build_repository_context_store(index: dict[str, Any], context_pack: dict[str, Any] | None = None, *, session: str = "default", persist: bool = True) -> RepositoryContextStore:
    root = pathlib.Path(index.get("root") or ".").resolve(); store = RepositoryContextStore(root, session)
    all_locators = list(iter_index_evidence(index))
    current_ids = {x["id"] for x in all_locators}
    store.reconcile_index(index, locators=all_locators)
    if context_pack is not None:
        # The provided context pack defines the new HOT working set. Remove old HOT items;
        # WARM state is represented by the index, so no demoted copy is needed.
        for item in store.items("active"):
            store.data["items"].pop(item["id"], None)
        active_files, active_symbols = _active_keys(context_pack); git_revisions = _context_git_revisions(context_pack)
        for ev in all_locators:
            path = str(ev.get("path") or "")
            active = ev.get("kind") == "file" and path in active_files
            if ev.get("kind") == "symbol":
                active = (path, str(ev.get("symbol") or ""), int(ev.get("start_line") or 1), int(ev.get("end_line") or ev.get("start_line") or 1)) in active_symbols
            if not active: continue
            if path in git_revisions:
                ev["revision"] = {"kind": "git-blob", "value": git_revisions[path]}
            ev["tier"] = "active"; ev["validity"] = "current"; store.upsert(ev)
    # Active entries removed from the latest index become rejected tombstones.
    for item in store.items("active"):
        if item["id"] not in current_ids:
            store.reject_evidence(item, reason="not-present-in-current-index", validity="missing")
    if persist: store.save()
    return store


def invalidate_stale_context(store: RepositoryContextStore, *, persist: bool = True) -> dict[str, Any]:
    by_path: dict[str, dict[str, Any]] = {}; changed: list[str] = []; missing: list[str] = []
    for item in store.items("active"):
        path = str(item.get("path") or "")
        if not path: continue
        if path not in by_path:
            full = (store.root / path).resolve()
            try:
                full.relative_to(store.root); stat_fp = file_cache_key(full); git = file_provenance(store.root, path)
                by_path[path] = {"exists": full.is_file(), "stat": stat_fp, "blob": ((git.get("content_identity") or {}).get("blob_sha") if isinstance(git, dict) else None)}
            except (OSError, ValueError): by_path[path] = {"exists": False, "stat": None, "blob": None}
        current = by_path[path]; revision = item.get("revision") if isinstance(item.get("revision"), dict) else {}
        kind = str(revision.get("kind") or "stat-fingerprint"); old = str(revision.get("value") or "")
        actual = current.get("blob") if kind == "git-blob" and current.get("blob") else current.get("stat")
        if not current["exists"]:
            store.data["items"].pop(item["id"], None); store.reject_evidence(item, reason="repository-path-missing", validity="missing")
            missing.append(item["id"]); store._record_invalidation(item["id"], "missing")
        elif old and actual and old != actual:
            store.data["items"].pop(item["id"], None); changed.append(item["id"])
            store._record_invalidation(item["id"], "stale", previous_revision=revision, current_revision={"kind": kind, "value": actual})
    if persist: store.save()
    return {
        "classification": "deterministic-repository-stale-invalidation", "checked_paths": len(by_path),
        "stale_items": len(changed), "missing_items": len(missing), "active_items_demoted": len(changed),
        "stale_ids": changed[:100], "missing_ids": missing[:100],
        "policy": "Changed HOT evidence is removed from the active overlay and must be rehydrated from the current repository index before reuse.",
    }
