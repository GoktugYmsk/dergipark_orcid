import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dashboardRoot = resolve(here, "..");
const sourceDirectory = resolve(dashboardRoot, "..", "outputs");
const destinationDirectory = resolve(dashboardRoot, "public", "data");
const files = [
  "orcid_candidates.csv",
  "orcid_api_validation.csv",
  "orcid_author_name_matches.csv",
];

await mkdir(destinationDirectory, { recursive: true });
for (const file of files) {
  await copyFile(resolve(sourceDirectory, file), resolve(destinationDirectory, file));
  console.log(`Kopyalandı: ${file}`);
}
