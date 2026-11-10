"""Verify the exact RPF-107 Actions archive and its public projection."""
import argparse
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from runtime.runproof_runtime.effectwitness.pge_r107_capsule import SENSITIVE, validate
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, check, sha, strict

SOURCE = "be485bdefd359578c4f050fb222d5edb08b16974"
RUN = "42764310121"
OWNER = "2ce7e1d22f264334ad75ddccf06ad838"
OUTER = "67de0b59a2336a9ad577fedd74e99b0d4f800a48ba0f7a855e7730beb74be7fb"
INNER = "84de3ad53911b428d28a4544761904dabf124f85a03c6364a61a406edab70a25"
PUBLIC = "fa967d921ebaf1233110155c23eba9f7081c4a4d42ecaf0222685c91ab2a57c4"
ARCHIVE = Path("spikes/rpf-108/evidence/rpf107-run-42764310121-actions.zip")


def verify_archive(raw):
    check(len(raw) == 4492 and sha(raw) == OUTER, "ACTIONS_ARCHIVE_IDENTITY")
    with ZipFile(BytesIO(raw)) as archive:
        members = archive.infolist()
        check(len(members) == 1 and members[0].filename == "public.zip"
              and members[0].file_size == 13872, "ACTIONS_MEMBERS")
        inner = archive.read(members[0])
    check(len(inner) == 13872 and sha(inner) == INNER, "INNER_IDENTITY")
    with ZipFile(BytesIO(inner)) as archive:
        members = archive.infolist()
        check([(x.filename, x.compress_type, x.file_size) for x in members] ==
              [("manifest.json", ZIP_STORED, 134), ("public.json", ZIP_STORED, 13516)], "INNER_MEMBERS")
        manifest, public = (archive.read(member) for member in members)
    check(len(public) == 13516 and sha(public) == PUBLIC, "PUBLIC_IDENTITY")
    check(manifest == canonical({"schema": "rpf107-manifest-v1", "public_sha256": PUBLIC,
                                 "public_size": len(public)}) and not SENSITIVE.search(public), "PUBLIC_MANIFEST")
    row = strict(public)
    check(canonical(row) == public, "PUBLIC_CANONICAL")
    validate(row, SOURCE, RUN, OWNER)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=ARCHIVE)
    with parser.parse_args().archive.open("rb") as file:
        row = verify_archive(file.read(4493))
    print(f"PUBLIC_PROJECTION_VERIFIED cases={len(row['cases'])} actions_sha256={OUTER}")


if __name__ == "__main__":
    main()
