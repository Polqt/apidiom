import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["ts/cli.ts"],
  format: ["cjs"],
  outDir: "dist",
  clean: true,
  shims: true,
  banner: { js: "#!/usr/bin/env node" },
});
