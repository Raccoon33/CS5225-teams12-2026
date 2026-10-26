// Runtime Pydantic/OpenAPI is the source; never edit generated artifacts by hand.
import { execFileSync } from 'node:child_process';
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createClient } from '@hey-api/openapi-ts';
import { format, resolveConfig } from 'prettier';

const root = fileURLToPath(new URL('../../', import.meta.url));
const check = process.argv.includes('--check');
const target = check
  ? await mkdtemp(join(tmpdir(), 'flatsplit-contracts-'))
  : root;
const config = await resolveConfig(join(root, 'package.json'));
const schemaPath = 'packages/contracts/openapi.json';
const outputs = [
  'packages/contracts/src/generated',
  'apps/web/src/api/generated',
];
const document = JSON.parse(
  execFileSync(
    'uv',
    [
      'run',
      '--package',
      'flatsplit-api',
      'python',
      '-c',
      'from flatsplit_api.handlers.http import app; print(app.get_openapi_schema().model_dump_json(by_alias=True, exclude_none=True))',
    ],
    { cwd: root, encoding: 'utf8' },
  ),
);
// Stable function-based SDK names; this does not change paths or HTTP payloads.
const names = new Set();
for (const operations of Object.values(document.paths)) {
  for (const operation of Object.values(operations)) {
    operation.operationId = operation.operationId
      .split('_groups')[0]
      .split('_health')[0]
      .split('_places')[0]
      .replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
    if (names.has(operation.operationId))
      throw new Error('Duplicate API operation name.');
    names.add(operation.operationId);
  }
}
async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) =>
      entry.isDirectory()
        ? files(join(directory, entry.name))
        : [join(directory, entry.name)],
    ),
  );
  return nested.flat().sort();
}
try {
  await mkdir(join(target, 'packages/contracts'), { recursive: true });
  await writeFile(
    join(target, schemaPath),
    await format(JSON.stringify(document), { ...config, parser: 'json' }),
  );
  for (const [index, path] of outputs.entries()) {
    const directory = join(target, path);
    await createClient({
      input: document,
      output: { path: directory, importFileExtension: '.js' },
      plugins:
        index === 0
          ? ['@hey-api/typescript', 'zod']
          : ['@hey-api/typescript', '@hey-api/client-fetch', '@hey-api/sdk'],
    });
    for (const file of await files(directory)) {
      await writeFile(
        file,
        await format(await readFile(file, 'utf8'), {
          ...config,
          filepath: file,
        }),
      );
    }
  }
  if (check) {
    const artifacts = [
      join(target, schemaPath),
      ...(
        await Promise.all(outputs.map((path) => files(join(target, path))))
      ).flat(),
    ];
    for (const file of artifacts) {
      const relative = file.slice(target.length + 1);
      const expected = await readFile(file, 'utf8');
      const actual = await readFile(join(root, relative), 'utf8').catch(
        () => '',
      );
      if (expected !== actual)
        throw new Error(
          `Generated API artifact is stale: ${relative}. Run pnpm generate:api.`,
        );
    }
    for (const path of outputs) {
      const expected = (await files(join(target, path))).map((file) =>
        file.slice(join(target, path).length),
      );
      const actual = (await files(join(root, path))).map((file) =>
        file.slice(join(root, path).length),
      );
      if (JSON.stringify(expected) !== JSON.stringify(actual))
        throw new Error(`Generated API file list is stale: ${path}.`);
    }
    console.log('Generated API schemas and client match runtime OpenAPI.');
  }
} finally {
  if (check) await rm(target, { recursive: true, force: true });
}
