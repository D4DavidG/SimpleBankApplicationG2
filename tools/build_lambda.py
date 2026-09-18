"""Package the backend into a zip Lambda will accept.

    python tools/build_lambda.py            # writes dist/lambda.zip

WHY A SCRIPT AND NOT "ZIP THE FOLDER"
-------------------------------------
Lambda runs no install step. Whatever the zip contains is the whole environment,
so pymongo and dnspython have to be *inside* it, installed for Lambda's platform
rather than for this laptop. Zipping the project by hand produces a function that
imports fine on Windows and then fails in the cloud with ModuleNotFoundError.

dnspython is the one people drop, because nothing imports it by name - pymongo
reaches for it only when the URI starts `mongodb+srv://`, which ours does. Its
absence looks like a DNS problem, not a packaging one.

WHY THE PLATFORM FLAGS
----------------------
`--platform manylinux2014_x86_64` asks pip for Linux wheels while running on
Windows or macOS. Without it pip builds for the machine you are on, and pymongo's
optional C extensions are compiled for the wrong platform. Set ARCH below to
aarch64 if the function is on Graviton.
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "lambda"
OUT = ROOT / "dist" / "lambda.zip"

ARCH = "manylinux2014_x86_64"   # aarch64 for a Graviton (arm64) function
PYTHON = "3.12"                 # match the function's runtime

# Only what the function imports. The tests, the frontend and server.py are not
# part of the deployment - a smaller zip is a faster cold start.
SOURCE = ["bank", "lambda_handler.py"]
DEPS = ["pymongo==4.18.1", "dnspython==2.8.0"]


def install_dependencies() -> None:
    print(f"  installing {len(DEPS)} dependencies for {ARCH}, python {PYTHON}...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *DEPS,
         "--target", str(BUILD),
         "--platform", ARCH,
         "--python-version", PYTHON,
         # Required with --platform: it tells pip to take the wheel as it is
         # rather than trying to build one for the machine it is running on.
         "--only-binary=:all:",
         "--quiet", "--upgrade"],
        check=True,
    )


def copy_source() -> None:
    for name in SOURCE:
        source = ROOT / name
        target = BUILD / name
        if source.is_dir():
            # __pycache__ holds bytecode compiled by this machine's interpreter.
            # Harmless but dead weight, and confusing to find in a deployment.
            shutil.copytree(source, target,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)
        print(f"  added {name}")


def write_zip() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUILD.rglob("*")):
            # pip leaves bytecode behind too, so the filter belongs here rather
            # than only on the source copy. Lambda recompiles what it needs, and
            # the .pyc files in the zip are for the wrong interpreter anyway.
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(BUILD))


def main() -> int:
    print("Building the Lambda deployment package")
    if BUILD.exists():
        # A stale build directory is how a removed file survives in the zip.
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    try:
        install_dependencies()
    except subprocess.CalledProcessError:
        print("\n  pip failed. If it could not find a wheel, check that ARCH and")
        print("  PYTHON at the top of this file match the function's settings.")
        return 1

    copy_source()
    write_zip()

    size_mb = OUT.stat().st_size / 1_000_000
    print(f"\n  wrote {OUT.relative_to(ROOT)} ({size_mb:.1f} MB)")
    # 50 MB is Lambda's limit for a direct upload; past it the zip has to go via
    # S3, which is a different command and a surprise at the wrong moment.
    if size_mb > 50:
        print("  over 50 MB - upload it to S3 and deploy from there, not directly.")
    print("\n  Handler: lambda_handler.lambda_handler")
    print("  Set BANK_SECRET, MONGODB_URI and MONGODB_DB on the function.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
