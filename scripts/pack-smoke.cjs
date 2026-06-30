"use strict";

const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");
const { spawnSync } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const packDir = path.join(root, ".tmp", "pack-smoke");
const cacheDir = path.join(root, ".tmp", "pack-smoke-cache");

if (process.argv.includes("--clean")) {
  fs.rmSync(packDir, { recursive: true, force: true });
  fs.rmSync(cacheDir, { recursive: true, force: true });
  fs.mkdirSync(packDir, { recursive: true });
  process.exit(0);
}

const tarballs = fs.readdirSync(packDir).filter((name) => name.endsWith(".tgz"));
if (tarballs.length !== 1) {
  throw new Error(`Expected one package tarball, found ${tarballs.length}`);
}

const archive = zlib.gunzipSync(fs.readFileSync(path.join(packDir, tarballs[0])));
const extractDir = path.join(packDir, "extracted");
extractTar(archive, extractDir);

const rootPackage = require(path.join(root, "package.json"));
const packedPackage = require(path.join(extractDir, "package", "package.json"));
if (packedPackage.version !== rootPackage.version) {
  throw new Error(
    `Packed package version ${packedPackage.version} does not match ${rootPackage.version}`
  );
}

const binRelative = packedPackage.bin && packedPackage.bin.apidiom;
if (!binRelative) {
  throw new Error("Packed package.json missing bin.apidiom field");
}
const cliPath = path.join(extractDir, "package", binRelative);
if (!fs.existsSync(cliPath)) {
  throw new Error(`Packed bin.apidiom points to missing file: ${binRelative}`);
}

const result = spawnSync(process.execPath, [cliPath, "--version"], { encoding: "utf8" });
if (result.status !== 0) {
  throw new Error(`Packed CLI exited ${result.status}:\n${result.stderr}`);
}
if (result.stderr) {
  throw new Error(`Packed CLI printed to stderr:\n${result.stderr}`);
}
const runtimeVersion = result.stdout.trim();
if (runtimeVersion !== rootPackage.version) {
  throw new Error(
    `Packed CLI --version output ${JSON.stringify(runtimeVersion)} does not match ${rootPackage.version}`
  );
}

fs.rmSync(packDir, { recursive: true, force: true });
fs.rmSync(cacheDir, { recursive: true, force: true });
process.stdout.write(`Packed CLI version OK: ${rootPackage.version}\n`);

function extractTar(buffer, destination) {
  for (let offset = 0; offset + 512 <= buffer.length; ) {
    const header = buffer.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) break;

    const name = readString(header, 0, 100);
    const sizeText = readString(header, 124, 12).trim();
    const size = sizeText ? Number.parseInt(sizeText, 8) : 0;
    if (!Number.isSafeInteger(size) || size < 0) {
      throw new Error(`Invalid tar entry size for ${name}`);
    }

    const target = path.resolve(destination, name);
    const destinationRoot = path.resolve(destination) + path.sep;
    if (!target.startsWith(destinationRoot)) {
      throw new Error(`Unsafe tar entry: ${name}`);
    }

    const type = String.fromCharCode(header[156] || 0);
    if (type === "0" || type === "\0") {
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, buffer.subarray(offset + 512, offset + 512 + size));
    } else if (type === "5") {
      fs.mkdirSync(target, { recursive: true });
    }

    offset += 512 + Math.ceil(size / 512) * 512;
  }
}

function readString(buffer, start, length) {
  const end = buffer.indexOf(0, start);
  return buffer.toString("utf8", start, end === -1 || end > start + length ? start + length : end);
}
