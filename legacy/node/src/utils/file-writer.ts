import { writeFile, mkdir, access } from "node:fs/promises";
import { dirname, join } from "node:path";

export interface WriteResult {
  path: string;
  action: "created" | "updated" | "skipped";
}

export async function writeProjectFiles(
  root: string,
  files: Record<string, string>,
  opts: { force?: boolean } = {}
): Promise<WriteResult[]> {
  const results: WriteResult[] = [];

  for (const [relativePath, content] of Object.entries(files)) {
    const fullPath = join(root, relativePath);
    const exists = await fileExists(fullPath);

    if (exists && !opts.force) {
      results.push({ path: relativePath, action: "skipped" });
      continue;
    }

    await mkdir(dirname(fullPath), { recursive: true });
    await writeFile(fullPath, content, "utf8");
    results.push({ path: relativePath, action: exists ? "updated" : "created" });
  }

  return results;
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}
